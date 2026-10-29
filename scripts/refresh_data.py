"""Actualización periódica: descarga el archivo del año en curso y reprocesa.

Pensado para programarse (Programador de tareas de Windows o cron):
    python scripts/refresh_data.py                # año actual
    python scripts/refresh_data.py --year 2025    # un año específico

Pasos:
    1. Descarga (reemplazando) <año>.jsonl.gz desde el Registro de Datos de OCP.
    2. Ejecuta el pipeline con la fuente "bulk" filtrando ese año.
"""

import argparse
import sys
from datetime import date

import _bootstrap  # noqa: F401

from contrataciones.cli import main
from contrataciones.utils.config_loader import load_config, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--limit", type=int, help="Máximo de procesos (pruebas)")
    parser.add_argument("--no-db", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    code = main(["download", "--year", str(args.year), "--overwrite"])
    if code != 0:
        sys.exit(code)
    bulk_dir = resolve_path(load_config("sources")["ocds"]["bulk_dir"])
    run_args = [
        "run",
        "--source",
        "bulk",
        "--year",
        str(args.year),
        "--input",
        str(bulk_dir / f"oece_{args.year}.jsonl.gz"),
    ]
    if args.limit:
        run_args += ["--limit", str(args.limit)]
    if args.no_db:
        run_args.append("--no-db")
    sys.exit(main(run_args))
