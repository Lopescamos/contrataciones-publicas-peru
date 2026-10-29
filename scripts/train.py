"""Entrena el modelo de monto esperado (Fase 2, machine learning).

Equivale a ``contrataciones-ml train``. Ejemplo:
    python scripts/train.py
"""

import sys

import _bootstrap  # noqa: F401

from contrataciones.models.cli import main

if __name__ == "__main__":
    sys.exit(main(["train", *sys.argv[1:]]))
