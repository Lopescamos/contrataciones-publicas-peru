"""Crea las tablas (sql/ddl) y vistas (sql/views) en la base de datos configurada.

Equivale a ``contrataciones setup-db``. Ejemplos:
    python scripts/setup_db.py                          # perfil de DB_PROFILE (.env)
    python scripts/setup_db.py --db-profile local_postgres
    python scripts/setup_db.py --db-profile cloud_postgres --drop
"""

import sys

import _bootstrap  # noqa: F401

from contrataciones.cli import main

if __name__ == "__main__":
    sys.exit(main(["setup-db", *sys.argv[1:]]))
