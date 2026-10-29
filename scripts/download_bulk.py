"""Descarga los archivos OCDS anuales del OECE desde el Registro de Datos de OCP.

Equivale a ``contrataciones download``. Ejemplos:
    python scripts/download_bulk.py --year 2025
    python scripts/download_bulk.py --year 2023-2025
"""

import sys

import _bootstrap  # noqa: F401

from contrataciones.cli import main

if __name__ == "__main__":
    sys.exit(main(["download", *sys.argv[1:]]))
