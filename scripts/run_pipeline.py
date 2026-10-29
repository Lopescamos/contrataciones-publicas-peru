"""Ejecuta el pipeline completo.

Equivale a ``contrataciones run``. Ejemplos:
    python scripts/run_pipeline.py --source sample
    python scripts/run_pipeline.py --source bulk --year 2025 --limit 20000
    python scripts/run_pipeline.py --source api --api-max-pages 5 --no-db
"""

import sys

import _bootstrap  # noqa: F401

from contrataciones.cli import main

if __name__ == "__main__":
    sys.exit(main(["run", *sys.argv[1:]]))
