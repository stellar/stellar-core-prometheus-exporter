import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="stellar-core-prometheus-exporter",
    version="0.9.5",
    author="Stellar Development Foundation",
    author_email="ops@stellar.org",
    description="Export stellar core metrics in prometheus format",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/stellar/stellar-core-prometheus-exporter",
    include_package_data=True,
    keywords=["prometheus", "exporter", "stellar"],
    license="Apache Software License 2.0",
    entry_points={
        'console_scripts': [
            'stellar-core-prometheus-exporter=stellar_core_prometheus_exporter:run',
        ],
    },
    packages=setuptools.find_packages(),
    install_requires=["prometheus_client", "requests"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "Intended Audience :: Information Technology",
        "Topic :: System :: Monitoring",
        "License :: OSI Approved :: Apache Software License",
    ],
)
