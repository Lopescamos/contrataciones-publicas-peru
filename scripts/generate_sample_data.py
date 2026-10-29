"""Regenera los datos sintéticos de demostración en data/sample.

Equivale a ``contrataciones sample``. Ejemplo:
    python scripts/generate_sample_data.py --n 1200 --seed 2026
"""

import sys

import _bootstrap  # noqa: F401

from contrataciones.cli import main

if __name__ == "__main__":
    sys.exit(main(["sample", *sys.argv[1:]]))
