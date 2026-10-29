"""Dataset de modelado: una fila por proceso, armado a partir de la capa gold.

No recalcula nada del pipeline. El objetivo sale de ``fact_proceso``:
``monto_adjudicado_pen`` (suma de las adjudicaciones válidas que calcula
``processing/transformer.py``) y ``ratio_adjudicado_referencial``.

:func:`build_modeling_table` devuelve dos tipos de columnas:

* ``tabla.columna``: las columnas de ``fact_proceso`` y de sus dimensiones (método,
  categoría y entidad) que pueden ser origen de una feature. Las columnas prohibidas
  por :mod:`contrataciones.features.catalog` ni siquiera se copian.
* Columnas de control, sin prefijo: llaves, fechas, montos, objetivo y población.

``fact_adjudicacion`` se lee solo para la fecha de adjudicación, que la división
temporal usa para filtrar filas. Nunca es origen de features.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from contrataciones.features.catalog import forbidden_reason
from contrataciones.processing.cleaner import normalize_key
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

GOLD_TABLES: tuple[str, ...] = (
    "fact_proceso",
    "dim_metodo",
    "dim_categoria",
    "dim_entidad",
    "fact_adjudicacion",
)
# Dimensiones del proceso y su llave en fact_proceso.
PROCESS_DIMENSIONS: dict[str, str] = {
    "dim_metodo": "metodo_key",
    "dim_categoria": "categoria_key",
    "dim_entidad": "entidad_key",
}

TARGET = "log_ratio_adjudicado"
# Diferencia máxima (en soles) para considerar que el adjudicado es igual al referencial.
EQUAL_AMOUNT_TOLERANCE = 0.005

MOTIVO_SIN_FECHA = "Sin fecha de convocatoria"
MOTIVO_SIN_ADJUDICACION = "Sin adjudicación válida"
MOTIVO_SIN_REFERENCIAL = "Sin valor referencial"
MOTIVO_METODO_EXCLUIDO = "Método excluido"
MOTIVO_CATEGORIA_EXCLUIDA = "Categoría excluida"
MOTIVO_RAZON_FUERA_DE_RANGO = "Razón fuera de rango"

CONTROL_COLUMNS: tuple[str, ...] = (
    "proceso_key",
    "ocid",
    "fecha_convocatoria",
    "fecha_adjudicacion",
    "valor_referencial_pen",
    "monto_adjudicado_pen",
    "ratio_adjudicado_referencial",
    TARGET,
    "es_adjudicado_igual_referencial",
    "es_poblacion",
    "es_entrenable",
    "motivo_exclusion",
)


def load_gold(curated_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Lee de ``data/curated`` las tablas gold que necesita el modelo."""
    curated = Path(curated_dir)
    missing = [name for name in GOLD_TABLES if not (curated / f"{name}.parquet").is_file()]
    if missing:
        raise FileNotFoundError(
            f"Faltan tablas de la capa gold en {curated}: {', '.join(missing)}. "
            "Ejecuta primero el pipeline: contrataciones run --source sample"
        )
    return {name: pd.read_parquet(curated / f"{name}.parquet") for name in GOLD_TABLES}


def read_manifest(curated_dir: str | Path) -> dict[str, Any]:
    """Manifiesto de la corrida del pipeline que generó la capa gold (vacío si no existe)."""
    path = Path(curated_dir) / "_manifest.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def date_from_key(keys: pd.Series) -> pd.Series:
    """Llave de fecha AAAAMMDD -> ``datetime64`` (``NaT`` si falta o no es válida)."""
    numeric = pd.to_numeric(keys, errors="coerce").astype("Int64")
    return pd.to_datetime(numeric.astype("string"), format="%Y%m%d", errors="coerce")


def award_dates(adjudicaciones: pd.DataFrame) -> pd.Series:
    """Fecha de la última adjudicación válida de cada proceso (índice ``ocid``)."""
    valid = adjudicaciones[adjudicaciones["es_valida"].fillna(False).astype(bool)]
    dates = date_from_key(valid["fecha_adjudicacion_key"])
    return dates.groupby(valid["ocid"].to_numpy()).max()


def _allowed_columns(frame: pd.DataFrame, table: str) -> pd.DataFrame:
    """Columnas que pueden ser origen de una feature, con el prefijo ``tabla.``."""
    keep = [c for c in frame.columns if forbidden_reason(table, str(c)) is None]
    return frame[keep].add_prefix(f"{table}.")


def _normalized_set(values: Any) -> set[str]:
    return {key for key in (normalize_key(v) for v in values or []) if key}


def build_modeling_table(
    gold: Mapping[str, pd.DataFrame], population: Mapping[str, Any] | None = None
) -> pd.DataFrame:
    """Una fila por proceso de ``fact_proceso`` con columnas de origen y de control.

    Población: procesos con fecha de convocatoria, adjudicación válida (monto > 0) y
    valor referencial > 0, sin métodos ni categorías excluidos. Los de la población cuya
    razón adjudicado/referencial cae fuera de ``[min_ratio, max_ratio]`` no se usan para
    entrenar (probable error de datos), pero sí se evalúan.
    """
    population = population or {}
    procesos = gold["fact_proceso"].reset_index(drop=True)
    monto = pd.to_numeric(procesos["monto_adjudicado_pen"], errors="coerce").astype("float64")
    referencial = pd.to_numeric(procesos["valor_referencial_pen"], errors="coerce").astype(
        "float64"
    )
    ratio = pd.to_numeric(procesos["ratio_adjudicado_referencial"], errors="coerce")
    ratio = ratio.astype("float64").fillna(monto / referencial.where(referencial > 0))

    control = pd.DataFrame(
        {
            "proceso_key": procesos["proceso_key"],
            "ocid": procesos["ocid"].astype(str),
            "fecha_convocatoria": date_from_key(procesos["fecha_convocatoria_key"]),
            "valor_referencial_pen": referencial,
            "monto_adjudicado_pen": monto,
            "ratio_adjudicado_referencial": ratio,
        }
    )
    control["fecha_adjudicacion"] = control["ocid"].map(award_dates(gold["fact_adjudicacion"]))

    sources = [_allowed_columns(procesos, "fact_proceso")]
    for dimension, key in PROCESS_DIMENSIONS.items():
        joined = procesos[[key]].merge(gold[dimension], on=key, how="left", validate="m:1")
        sources.append(_allowed_columns(joined.drop(columns=[key]), dimension))
    table = pd.concat([control, *sources], axis=1)

    no_date = table["fecha_convocatoria"].isna()
    no_award = ~(monto > 0)
    no_reference = ~(referencial > 0)
    excluded_method = (
        table["dim_metodo.metodo_detalle"]
        .map(normalize_key)
        .isin(_normalized_set(population.get("exclude_methods")))
    )
    excluded_category = (
        table["dim_categoria.categoria"]
        .map(normalize_key)
        .isin(_normalized_set(population.get("exclude_categories")))
    )
    in_population = ~(no_date | no_award | no_reference | excluded_method | excluded_category)
    min_ratio = float(population.get("min_ratio", 0.05))
    max_ratio = float(population.get("max_ratio", 5.0))
    out_of_range = in_population & ~ratio.between(min_ratio, max_ratio)

    reasons = [
        (no_date, MOTIVO_SIN_FECHA),
        (no_award, MOTIVO_SIN_ADJUDICACION),
        (no_reference, MOTIVO_SIN_REFERENCIAL),
        (excluded_method, MOTIVO_METODO_EXCLUIDO),
        (excluded_category, MOTIVO_CATEGORIA_EXCLUIDA),
        (out_of_range, MOTIVO_RAZON_FUERA_DE_RANGO),
    ]
    table["motivo_exclusion"] = np.select(
        [mask.to_numpy() for mask, _ in reasons], [label for _, label in reasons], default=""
    )
    table["motivo_exclusion"] = table["motivo_exclusion"].replace("", None)
    table["es_poblacion"] = in_population
    table["es_entrenable"] = in_population & ~out_of_range
    table[TARGET] = np.log(ratio.where(in_population))
    table["es_adjudicado_igual_referencial"] = in_population & (
        (monto - referencial).abs() < EQUAL_AMOUNT_TOLERANCE
    )
    logger.info(
        "Dataset de modelado: %d procesos, %d en la población, %d entrenables",
        len(table),
        int(in_population.sum()),
        int(table["es_entrenable"].sum()),
    )
    return table


def population_summary(table: pd.DataFrame) -> dict[str, Any]:
    """Conteos de la población y de los motivos de exclusión."""
    reasons = table["motivo_exclusion"].dropna().value_counts()
    return {
        "procesos": int(len(table)),
        "poblacion": int(table["es_poblacion"].sum()),
        "entrenables": int(table["es_entrenable"].sum()),
        "adjudicado_igual_referencial": int(table["es_adjudicado_igual_referencial"].sum()),
        "motivos_exclusion": {str(k): int(v) for k, v in reasons.items()},
    }
