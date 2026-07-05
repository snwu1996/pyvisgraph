"""Command line entry point for pyvisgraph-viewer.

The heavy optional dependencies (geopandas, PyQt6) are imported lazily so
this module can print a helpful install hint when the 'viewer' extras are
missing.
"""
import argparse
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='pyvisgraph-viewer',
        description='Interactive viewer: load polygons from any '
                    'geopandas-supported file (KML, shapefile, GeoJSON, '
                    'GPKG, ...), build the visibility graph and explore '
                    'shortest paths. Click to set the start point, click '
                    'again to set the end point.')
    parser.add_argument('file', help='path to a geopandas-readable file')
    parser.add_argument('--workers', type=int, default=1,
                        help='number of subprocesses for building the '
                             'visibility graph (default: 1)')
    parser.add_argument('--layer', default=None,
                        help='layer name for multi-layer sources (e.g. GPKG)')
    args = parser.parse_args(argv)

    try:
        import geopandas  # noqa: F401
        from PyQt6.QtWidgets import QApplication
    except ImportError as e:
        print("pyvisgraph-viewer requires the 'viewer' extras "
              "('{}' is missing).\n"
              'Install with: pip install pyvisgraph[viewer]'.format(e.name),
              file=sys.stderr)
        return 1

    if not os.path.isfile(args.file):
        print('File not found: {}'.format(args.file), file=sys.stderr)
        return 1

    from pyvisgraph.viewer.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    try:
        window = MainWindow(args.file, workers=args.workers, layer=args.layer)
    except Exception as e:
        print('Could not load {}: {}'.format(args.file, e), file=sys.stderr)
        return 1
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
