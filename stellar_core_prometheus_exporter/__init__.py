def run():
    from . import exporter
    try:
        exporter.main()
    except KeyboardInterrupt:
        print("Interrupted")
