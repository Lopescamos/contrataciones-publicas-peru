"""Calcula el monto esperado y marca los montos atípicos con el último modelo.

Equivale a ``contrataciones-ml predict``. Ejemplo:
    python scripts/predict.py --no-db
"""

import sys

import _bootstrap  # noqa: F401

from contrataciones.models.cli import main

if __name__ == "__main__":
    sys.exit(main(["predict", *sys.argv[1:]]))
