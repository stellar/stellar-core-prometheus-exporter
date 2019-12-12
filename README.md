# Overview

The Stellar Core Prometheus Exporter reads metrics exposed by the
stellar-core daemon and exposes them in prometheus format.

# Configuration

Optional config can be provided using CLI arguments or environment variables.

Supported configuration options:
* **--stellar-core-address** - address of monitored stellar-core. Defaults to `http://127.0.0.1:11626`. Can also be set using `STELLAR_CORE_ADDRESS` environment variable
* **--port** - listening port. Defaults to `9473`. Can also be set using `PORT` environment variable

# Grafana dashboard

Grafana can be used to visualise data. Example dashboards are shipped with this code.
Latest versions is also available on [grafana.com](https://grafana.com/orgs/stellar/dashboards)

Please refer to the [documentation](https://github.com/stellar/packages/blob/master/docs/monitoring.md)
for details.

# Docker image

Included Dockerfile uses apt package to deploy the exporter. Example build command:
```
docker build -t stellar-core-prometheus-exporter:latest .
```

# Installing from pypi

To download/test package in pypi you can use venv:
```
python3 -m venv venv
. venv/bin/activate
```

Install:
```
python3 -m pip install stellar_core_prometheus_exporter
```

Run:
```
./venv/bin/stellar-core-prometheus-exporter
```

# Releasing new version

* ensure you bumped version number in setup.py. PyPi does not allow version reuse
* build new package:
```
python3 setup.py sdist bdist_wheel
```
* push to testpypi:
```
python3 -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*
```
* test by installing the package (see above). If all good release:
```
python3 -m twine upload dist/*
```
