#!/usr/bin/python
# vim: tabstop=4 expandtab shiftwidth=4

import argparse
import requests
import re
import time
import threading
from datetime import datetime
from os import environ
from . import lib


try:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn
except ImportError:
    # Python 3
    unicode = str
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn


parser = argparse.ArgumentParser(description='simple stellar-core Prometheus exporter/scraper')
parser.add_argument('--stellar-core-address', type=str,
                    help='Stellar core address. Defaults to STELLAR_CORE_ADDRESS environment '
                         'variable or if not set to http://127.0.0.1:11626',
                    default=environ.get('STELLAR_CORE_ADDRESS', 'http://127.0.0.1:11626'))
parser.add_argument('--port', type=int,
                    help='HTTP bind port. Defaults to PORT environment variable '
                         'or if not set to 9473',
                    default=int(environ.get('PORT', '9473')))
args = parser.parse_args()


class _ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    """Thread per request HTTP server."""
    # Copied from prometheus client_python
    daemon_threads = True


class StellarCoreHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def get_labels(self):
        try:
            response = requests.get(self.info_url)
            json = response.json()
            build = json['info']['build']
            network = json['info']['network']
        except Exception:
            return ['unknown', 'unknown', 'unknown', 'unknown', 'unknown']
        match = self.build_regex.match(build)
        build = re.sub('\s', '_', build).lower()
        build = re.sub('\(|\)', '', build)

        if not match:
            return ['unknown', 'unknown', 'unknown', build, network]

        labels = [
            match.group(2),
            match.group(3),
            match.group(4),
            build,
            network,
        ]
        return labels

    def buckets_to_metrics(self, metric_name, buckets):
        # Converts raw bucket metric into sorted list of buckets
        unit = buckets['boundary_unit']
        description = 'libmedida metric type: ' + buckets['type']

        measurements = []
        for bucket in buckets['buckets']:
            measurements.append({
                'boundary': lib.duration_to_seconds(bucket['boundary'], unit),
                'count': bucket['count'],
                'sum': bucket['sum']
                }
            )
        count_value = 0
        sum_value = 0
        for m in sorted(measurements, key=lambda i: i['boundary']):
            # Buckets from core contain only values from their respective ranges.
            # Prometheus expects "le" buckets to be cummulative so we need some extra math
            count_value += m['count']
            sum_value += lib.duration_to_seconds(m['sum'], unit)

            # Treat buckets larger than 30d as infinity
            if float(m['boundary']) > 30 * 86400:
                bucket = '+Inf'
            else:
                bucket = m['boundary']

            self.registry.Histogram(metric_name, description,
                                    bucket=bucket,
                                    value=count_value,
                                    )
        self.registry.Summary(metric_name, description,
                              count_value=count_value,
                              sum_value=sum_value,
                              )

    def set_vars(self):
        self.info_url = args.stellar_core_address + '/info'
        self.metrics_url = args.stellar_core_address + '/metrics'
        self.cursors_url = args.stellar_core_address + '/getcursor'
        self.info_keys = ['ledger', 'network', 'peers', 'protocol_version', 'quorum', 'startedOn', 'state']
        self.state_metrics = ['booting', 'joining scp', 'connected', 'catching up', 'synced', 'stopping']
        self.ledger_metrics = {'age': 'age', 'baseFee': 'base_fee', 'baseReserve': 'base_reserve',
                               'closeTime': 'close_time', 'maxTxSetSize': 'max_tx_set_size',
                               'num': 'num', 'version': 'version'}
        self.quorum_metrics = ['agree', 'delayed', 'disagree', 'fail_at', 'missing']
        self.quorum_phase_metrics = ['unknown', 'prepare', 'confirm', 'externalize']
        # Examples:
        #   "stellar-core 11.1.0-unstablerc2 (324c1bd61b0e9bada63e0d696d799421b00a7950)"
        #   "stellar-core 11.1.0 (324c1bd61b0e9bada63e0d696d799421b00a7950)"
        #   "v11.1.0"
        self.build_regex = re.compile('(stellar-core|v) ?(\d+)\.(\d+)\.(\d+).*$')

        self.label_names = ["ver_major", "ver_minor", "ver_patch", "build", "network"]
        self.labels = self.get_labels()
        self.registry = lib.Registry(default_labels=tuple(zip(self.label_names, self.labels)))
        self.content_type = str('text/plain; version=0.0.4; charset=utf-8')

    def error(self, code, msg):
        self.send_response(code)
        self.send_header('Content-Type', self.content_type)
        self.end_headers()
        self.wfile.write('{}\n'.format(msg).encode('utf-8'))

    def do_GET(self):
        self.set_vars()
        ###########################################
        # Export metrics from the /metrics endpoint
        ###########################################
        try:
            response = requests.get(self.metrics_url)
        except requests.ConnectionError:
            self.error(504, 'Error retrieving data from {}'.format(self.metrics_url))
            return
        if not response.ok:
            self.error(504, 'Error retrieving data from {}'.format(self.metrics_url))
            return
        try:
            metrics = response.json()['metrics']
        except ValueError:
            self.error(500, 'Error parsing metrics JSON data')
            return
        # iterate over all metrics
        for k in metrics:
            metric_name = re.sub('\.|-|\s', '_', k).lower()
            metric_name = 'stellar_core_' + metric_name

            if metrics[k]['type'] == 'timer':
                # we have a timer, expose as a Prometheus Summary
                # we convert stellar-core time units to seconds, as per Prometheus best practices
                metric_name = metric_name + '_seconds'
                if 'sum' in metrics[k]:
                    # use libmedida sum value
                    total_duration = metrics[k]['sum']
                else:
                    # compute sum value
                    total_duration = (metrics[k]['mean'] * metrics[k]['count'])

                self.registry.Summary(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                      count_value=metrics[k]['count'],
                                      sum_value=lib.duration_to_seconds(total_duration, metrics[k]['duration_unit']),
                                      )
                # add stellar-core calculated quantiles to our summary
                self.registry.Gauge(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                    labels=tuple(zip(self.label_names+['quantile'], self.labels+[0.75])),
                                    value=lib.duration_to_seconds(metrics[k]['75%'], metrics[k]['duration_unit']),
                                    )
                self.registry.Gauge(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                    labels=tuple(zip(self.label_names+['quantile'], self.labels+[0.99])),
                                    value=lib.duration_to_seconds(metrics[k]['99%'], metrics[k]['duration_unit']),
                                    )
                # Newer versions of core report a '100%' quantile which is the max
                # sample over the recent sampling period (not all-time).
                if '100%' in metrics[k]:
                    self.registry.Gauge(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                        labels=tuple(zip(self.label_names+['quantile'], self.labels+[1.0])),
                                        value=lib.duration_to_seconds(metrics[k]['100%'], metrics[k]['duration_unit']),
                                        )

            elif metrics[k]['type'] == 'histogram':
                if 'count' not in metrics[k]:
                    # Stellar-core version too old, we don't have required data
                    continue

                self.registry.Summary(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                      count_value=metrics[k]['count'],
                                      sum_value=metrics[k]['sum'],
                                      )
                # add stellar-core calculated quantiles to our summary
                self.registry.Gauge(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                    labels=tuple(zip(self.label_names+['quantile'], self.labels+[0.75])),
                                    value=metrics[k]['75%'],
                                    )
                self.registry.Gauge(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                    labels=tuple(zip(self.label_names+['quantile'], self.labels+[0.99])),
                                    value=metrics[k]['99%'],
                                    )
                # Newer versions of core report a '100%' quantile which is the max
                # sample over the recent sampling period (not all-time).
                if '100%' in metrics[k]:
                    self.registry.Gauge(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                        labels=tuple(zip(self.label_names+['quantile'], self.labels+[1.0])),
                                        value=metrics[k]['100%'],
                                        )

            elif metrics[k]['type'] == 'counter':
                # we have a counter, this is a Prometheus Gauge
                self.registry.Gauge(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                    value=metrics[k]['count']
                                    )
            elif metrics[k]['type'] == 'meter':
                # we have a meter, this is a Prometheus Counter
                self.registry.Counter(metric_name, 'libmedida metric type: ' + metrics[k]['type'],
                                      value=metrics[k]['count']
                                      )
            elif metrics[k]['type'] == 'buckets':
                # We have a bucket, this is a Prometheus Histogram
                self.buckets_to_metrics(metric_name, metrics[k])

        #######################################
        # Export metrics from the info endpoint
        #######################################
        try:
            response = requests.get(self.info_url)
        except requests.ConnectionError:
            self.error(504, 'Error retrieving data from {}'.format(self.info_url))
            return
        if not response.ok:
            self.error(504, 'Error retrieving data from {}'.format(self.info_url))
            return
        try:
            info = response.json()['info']
        except ValueError:
            self.error(500, 'Error parsing info JSON data')
            return
        if not all([i in info for i in self.info_keys]):
            self.error(500, 'Error - info endpoint did not return all required fields')
            return

        # Ledger metrics
        for core_name, prom_name in self.ledger_metrics.items():
            self.registry.Gauge('stellar_core_ledger_{}'.format(prom_name),
                                'Stellar core ledger metric name: {}'.format(core_name),
                                value=info['ledger'][core_name],
                                )
        # Version 11.2.0 and later report quorum metrics in the following format:
        # "quorum" : {
        #    "qset" : {
        #      "agree": 3
        #
        # Older versions use this format:
        # "quorum" : {
        #   "758110" : {
        #     "agree" : 3,
        if 'qset' in info['quorum']:
            tmp = info['quorum']['qset']
        else:
            tmp = info['quorum'].values()[0]
        if not tmp:
            self.error(500, 'Error - missing quorum data')
            return

        for metric in self.quorum_metrics:
            try:

                self.registry.Gauge('stellar_core_quorum_{}'.format(metric),
                                    'Stellar core quorum metric: {}'.format(metric),
                                    tmp[metric]
                                    )
            except KeyError as e:
                self.log_message('Unable to find metric in quorum qset: {}. This is probably fine and will fix itself as stellar-core joins the quorum, or core is running cli catchup'.format(metric))

        try:

            for metric in self.quorum_phase_metrics:
                if tmp['phase'].lower() == metric:
                    value = 1
                else:
                    value = 0
                self.registry.Gauge('stellar_core_quorum_phase_{}'.format(metric),
                                    'Stellar core quorum phase {}'.format(metric),
                                    value=value,
                                    )
        except KeyError as e:
                self.log_message('Unable to find phase in quorum qset. This is probably fine and will fix itself as stellar-core joins the quorum, or core is running cli catchup')

        # Versions >=11.2.0 expose more info about quorum
        if 'transitive' in info['quorum']:
            if info['quorum']['transitive']['intersection']:
                value = 1
            else:
                value = 0
            self.registry.Gauge('stellar_core_quorum_transitive_intersection',
                                'Stellar core quorum transitive intersection',
                                value=value,
                                )
            self.registry.Gauge('stellar_core_quorum_transitive_last_check_ledger',
                                'Stellar core quorum transitive last_check_ledger',
                                value=info['quorum']['transitive']['last_check_ledger'],
                                )
            self.registry.Gauge('stellar_core_quorum_transitive_node_count',
                                'Stellar core quorum transitive node_count',
                                value=info['quorum']['transitive']['node_count'],
                                )
            # Versions >=11.3.0 expose "critical" key
            if 'critical' in info['quorum']['transitive']:
                if info['quorum']['transitive']['critical']:
                    for peer_list in info['quorum']['transitive']['critical']:
                        critical_peers = ','.join(sorted(peer_list))  # label value is comma separated listof peers
                        self.registry.Gauge('stellar_core_quorum_transitive_critical',
                                            'Stellar core quorum transitive critical',
                                            labels=tuple(zip(self.label_names+['critical_validators'],
                                                             self.labels+[critical_peers])),
                                            value=1,
                                            )
                else:
                    self.registry.Gauge('stellar_core_quorum_transitive_critical',
                                        'Stellar core quorum transitive critical',
                                        labels=tuple(zip(self.label_names+['critical_validators'], self.labels+['null'])),
                                        value=0,
                                        )
        # Peers metrics
        self.registry.Gauge('stellar_core_peers_authenticated_count',
                            'Stellar core authenticated_count count',
                            value=info['peers']['authenticated_count'],
                            )

        self.registry.Gauge('stellar_core_peers_pending_count',
                            'Stellar core pending_count count',
                            value=info['peers']['pending_count'],
                            )
        self.registry.Gauge('stellar_core_protocol_version',
                            'Stellar core protocol_version',
                            value=info['protocol_version'],
                            )
        for metric in self.state_metrics:
            name = re.sub('\s', '_', metric)
            if info['state'].lower().startswith(metric):  # Use startswith to work around "!"
                value = 1
            else:
                value = 0
            self.registry.Gauge('stellar_core_{}'.format(name),
                                'Stellar core state {}'.format(metric),
                                value=value,
                                )
        date = datetime.strptime(info['startedOn'], "%Y-%m-%dT%H:%M:%SZ")
        self.registry.Gauge('stellar_core_started_on', 'Stellar core start time in epoch',
                            value=int(date.strftime('%s')),
                            )
        #######################################
        # Export cursor metrics
        #######################################
        try:
            response = requests.get(self.cursors_url)
        except requests.ConnectionError:
            self.error(504, 'Error retrieving data from {}'.format(self.cursors_url))
            return

        # Some server modes we want to scrape do not support 'getcursors' command at all.
        # These just respond with a 404 and the non-json informative unknown-commands output.
        if not response.ok and response.status_code != 404:
            self.error(504, 'Error retrieving data from {}'.format(self.cursors_url))
            return

        if "Supported HTTP commands" not in str(response.content):
            try:
                cursors = response.json()['cursors']
            except ValueError:
                self.error(500, 'Error parsing cursor JSON data')
                return

            for cursor in cursors:
                if not cursor:
                    continue
                cursor_name = cursor.get('id').strip()
                self.registry.Gauge('stellar_core_active_cursors',
                                    'Stellar core active cursors',
                                    labels=tuple(zip(self.label_names+['cursor_name'], self.labels+[cursor_name])),
                                    value=cursor['cursor'],
                                    )

        #######################################
        # Render output
        #######################################
        output = self.registry.render()
        if not output:
            self.error(500, 'Error - no metrics were genereated')
            return
        self.send_response(200)
        self.send_header('Content-Type', self.content_type)
        self.end_headers()
        self.wfile.write(output)


def main():
    httpd = _ThreadingSimpleServer(("", args.port), StellarCoreHandler)
    t = threading.Thread(target=httpd.serve_forever)
    t.daemon = True
    t.start()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
