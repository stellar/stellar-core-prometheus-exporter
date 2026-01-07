FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    gnupg2 wget apt-utils apt-transport-https ca-certificates
RUN wget -qO - https://apt.stellar.org/SDF.asc | apt-key add - && \
    echo "deb https://apt.stellar.org jammy stable" | tee -a /etc/apt/sources.list.d/SDF.list
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends stellar-core-prometheus-exporter

EXPOSE 9473
ENTRYPOINT ["/usr/bin/stellar-core-prometheus-exporter"]
