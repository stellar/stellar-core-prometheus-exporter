#!/usr/bin/python
# vim: tabstop=4 expandtab shiftwidth=4


def duration_to_seconds(duration, duration_unit):
    # given duration and duration_unit, returns duration in seconds
    time_units_to_seconds = {
        'd':  'duration * 86400.0',
        'h':  'duration * 3600.0',
        'm':  'duration * 60.0',
        's':  'duration / 1.0',
        'ms': 'duration / 1000.0',
        'us': 'duration / 1000000.0',
        'ns': 'duration / 1000000000.0',
    }
    return eval(time_units_to_seconds[duration_unit])


class Registry(object):
    def __init__(self, default_labels):
        self.metrics = []
        self.default_labels = default_labels

    def list(self):
        print(self.metrics)

    def render(self):
        fmt = '# HELP {name} {description}\n# TYPE {name} {prom_type}\n{name}{{{labels}}} {value}\n'
        txt = ''
        for m in self.metrics:
            name, description, labels, prom_type, value = m
            label_text = ','.join(['{}="{}"'.format(k, v) for k, v in labels])
            txt += fmt.format(description=description,
                              name=name,
                              labels=label_text,
                              prom_type=prom_type,
                              value=value,
                              )
        return txt.encode('utf-8')

    def Summary(self, name, description, count_value, sum_value, labels=None):
        self.metrics.append((name+'_count', description, labels or self.default_labels, 'summary', count_value))
        self.metrics.append((name+'_sum', description, labels or self.default_labels, 'summary', sum_value))

    def Histogram(self, name, description, bucket, value, labels=None):
        if labels:
            new_labels = tuple(list(labels) + [("le", bucket)])
        else:
            new_labels = tuple(list(self.default_labels) + [("le", bucket)])
        self.metrics.append((name+'_bucket', description, new_labels, 'histogram', value))

    def Counter(self, name, description, value, labels=None):
        self.metrics.append((name, description, labels or self.default_labels, 'counter', value))

    def Gauge(self, name, description, value, labels=None):
        self.metrics.append((name, description, labels or self.default_labels, 'gauge', value))
