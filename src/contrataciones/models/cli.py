"""Interfaz de línea de comandos del modelo de monto esperado: ``contrataciones-ml``.

Comandos:
    train    Entrena el modelo con la capa gold (data/curated) y lo registra en models/.
    predict  Calcula el monto esperado y marca los montos atípicos (data/predictions,
             base de datos y reporte Excel).
    list     Lista los modelos registrados.

Ejemplos:
    contrataciones run --source sample
    contrataciones-ml train
    contrataciones-ml predict
    contrataciones-ml predict --version monto_esperado_20261020_120000 --no-db
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING

from contrataciones import __version__
from contrataciones.utils.config_loader import ConfigError, load_config, resolve_path
from contrataciones.utils.logger import get_logger, setup_logging

if TYPE_CHECKING:
    from contrataciones.models.workflow import PredictionRun, TrainingRun

logger = get_logger(__name__)

MODEL_LABELS = {
    "linea_base": "línea base",
    "mediana_global": "mediana global",
    "razon_1": "adjudicado = referencial",
}


def _pct(value: float) -> str:
    return f"{value:.1%}" if math.isfinite(value) else "sin dato"


def _print_footer(
    outputs: dict[str, str], warnings: list[str], durations: dict[str, float]
) -> None:
    print("Salidas:")
    for name, path in outputs.items():
        print(f"  {name:<22} {path}")
    if warnings:
        print("Advertencias:")
        for warning in warnings:
            print(f"  - {warning}")
    print(f"Duración total: {sum(durations.values()):.1f} s")


def _print_training(run: TrainingRun) -> None:
    print("\n" + "=" * 72)
    print(
        f"Modelo {run.version}  |  seleccionado: {run.selected}  |  "
        f"aceptado: {'sí' if run.accepted else 'no'}"
    )
    print("=" * 72)
    data = run.data
    synthetic = "  (datos SINTÉTICOS)" if data.get("sinteticos") else ""
    print(
        f"Datos: corrida {data.get('run_id') or '-'}, fuente {data.get('fuente') or '-'}{synthetic}"
    )
    population = run.population
    reasons = ", ".join(f"{k} {v:,}" for k, v in population["motivos_exclusion"].items())
    print(
        f"Población: {population['poblacion']:,} de {population['procesos']:,} procesos "
        f"({population['entrenables']:,} entrenables)"
        + (f"; excluidos: {reasons}" if reasons else "")
    )
    dates = run.split_dates
    parts = run.partitions
    print(
        f"División: entrenamiento {parts.get('entrenamiento', 0):,} "
        f"(< {dates['inicio_validacion']}) | validación {parts.get('validacion', 0):,} | "
        f"prueba {parts.get('prueba', 0):,} (< {dates['corte_madurez']}) | "
        f"no evaluado {parts.get('no_evaluado', 0):,}"
    )
    print(
        "Validación (MAE log): "
        + " | ".join(f"{MODEL_LABELS.get(k, k)} {v:.4f}" for k, v in run.validation.items())
    )
    model, base = run.test[run.selected], run.test["linea_base"]
    print(
        f"Prueba (MAE log): modelo {model:.4f} vs línea base {base:.4f}  ->  mejora "
        f"{_pct(run.improvement)} (criterio >= {run.threshold:.0%})"
    )
    _print_footer(run.outputs, run.warnings, run.durations)


def _print_prediction(run: PredictionRun) -> None:
    print("\n" + "=" * 72)
    print(
        f"Predicción con {run.version}  |  aceptado: {'sí' if run.accepted else 'no'}  |  "
        f"estado: {run.status}"
    )
    print("=" * 72)
    summary = run.summary
    print(f"Procesos evaluados: {summary['procesos']:,}")
    for label, n in summary["por_tipo"].items():
        print(f"  {label:<22} {n:>8,}")
    origins = ", ".join(f"{k} {v:,}" for k, v in summary["por_origen"].items())
    print(f"Origen de la predicción: {origins}")
    if run.database:
        views = ", ".join(run.database["vistas"]) or "ninguna"
        print(f"Base de datos: {run.database['filas']:,} filas cargadas; vistas: {views}")
    _print_footer(run.outputs, run.warnings, run.durations)


# -----------------------------------------------------------------------------
# Comandos
# -----------------------------------------------------------------------------
def cmd_train(args: argparse.Namespace) -> int:
    from contrataciones.models.workflow import run_training

    try:
        run = run_training()
    except (ConfigError, FileNotFoundError, KeyError, ValueError) as exc:
        logger.error("%s", exc)
        return 1
    _print_training(run)
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    from contrataciones.models.workflow import run_prediction

    try:
        run = run_prediction(
            version=args.version,
            load_database=False if args.no_db else None,
            db_profile=args.db_profile,
            export_excel=False if args.no_excel else None,
        )
    except (ConfigError, FileNotFoundError, KeyError, ValueError) as exc:
        logger.error("%s", exc)
        return 1
    _print_prediction(run)
    return 2 if run.status == "parcial" else 0


def cmd_list(args: argparse.Namespace) -> int:
    import pandas as pd

    from contrataciones.models.registry import list_models

    models_dir = resolve_path(load_config("settings")["paths"]["models"])
    catalog = list_models(models_dir)
    if catalog.empty:
        print(
            f"No hay modelos registrados en {models_dir}. Entrena uno con: contrataciones-ml train"
        )
        return 0
    columns = [
        "version",
        "modelo_seleccionado",
        "aceptado",
        "mejora_vs_linea_base",
        "mae_log_prueba",
        "fuente",
        "en_disco",
    ]
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(catalog[[c for c in columns if c in catalog.columns]].to_string(index=False))
    return 0


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contrataciones-ml",
        description=(
            "Modelo de monto esperado (Fase 2): estima cuánto debería costar un proceso y marca "
            "los montos adjudicados atípicos."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING o ERROR")
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="Entrena y registra el modelo con la capa gold")
    train.set_defaults(func=cmd_train)

    predict = sub.add_parser("predict", help="Calcula montos esperados y montos atípicos")
    predict.add_argument("--version", help="Versión del modelo (por defecto, la más reciente)")
    predict.add_argument("--db-profile", help="Perfil de config/db_config.yaml")
    predict.add_argument("--no-db", action="store_true", help="No cargar la base de datos")
    predict.add_argument("--no-excel", action="store_true", help="No generar el reporte Excel")
    predict.set_defaults(func=cmd_predict)

    listing = sub.add_parser("list", help="Lista los modelos registrados")
    listing.set_defaults(func=cmd_list)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_config("settings")
        log_cfg = settings.get("logging", {}) or {}
        setup_logging(
            level=args.log_level or log_cfg.get("level") or "INFO",
            log_file=resolve_path(log_cfg["file"]) if log_cfg.get("file") else None,
            max_bytes=int(log_cfg.get("max_bytes", 5_000_000)),
            backup_count=int(log_cfg.get("backup_count", 3)),
        )
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 1
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        logger.warning("Interrumpido por el usuario")
        return 130
    except ConfigError as exc:
        logger.error("Error de configuración: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
