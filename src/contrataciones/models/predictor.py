"""Puntaje de los procesos con un modelo registrado y exportación de las predicciones.

Cada proceso de la población recibe su monto esperado:

* si participó en el entrenamiento, con su predicción **fuera de muestra** guardada en
  el modelo (la del modelo entrenado sin su bloque de convocatoria);
* si es nuevo, con el **modelo final**, que tampoco lo vio.

Así ningún proceso se evalúa con un modelo que haya aprendido de su propio monto.

La tabla resultante (``pred_monto_esperado``) se guarda en ``data/predictions``
(Parquet y CSV) y, opcionalmente, en la base de datos: tabla aparte, sin llaves
foráneas hacia la capa gold, con DDL y vistas en ``sql/ddl_ml`` y ``sql/views_ml``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from contrataciones.export.csv_exporter import export_csv, export_parquet
from contrataciones.export.db_writer import create_views, ensure_tables, load_tables
from contrataciones.features.builder import build_features
from contrataciones.features.catalog import specs_from_dicts
from contrataciones.features.dataset import build_modeling_table
from contrataciones.ingestion.db_connector import DatabaseConnector
from contrataciones.models import anomaly
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

ORIGIN_HISTORICAL = "Histórico (fuera de muestra)"
ORIGIN_NEW = "Nuevo (modelo final)"
# Tablas de la capa gold que usan las vistas de sql/views_ml.
VIEW_DEPENDENCIES: tuple[str, ...] = (
    "fact_proceso",
    "dim_entidad",
    "dim_metodo",
    "dim_categoria",
    "dim_fecha",
)
OUTPUT_COLUMNS: tuple[str, ...] = (
    "proceso_key",
    "ocid",
    "valor_referencial_pen",
    "monto_adjudicado_pen",
    "ratio_adjudicado_referencial",
    "ratio_esperado",
    "monto_esperado_pen",
    "monto_minimo_esperado_pen",
    "monto_maximo_esperado_pen",
    "pct_desviacion",
    "residuo_log",
    "z_robusto",
    "tipo_desviacion",
    "es_atipico",
    "es_adjudicado_igual_referencial",
    "segmento_escala",
    "origen_prediccion",
    "modelo_version",
    "modelo_aceptado",
    "fecha_prediccion",
)
MONEY_COLUMNS: tuple[str, ...] = (
    "valor_referencial_pen",
    "monto_adjudicado_pen",
    "monto_esperado_pen",
    "monto_minimo_esperado_pen",
    "monto_maximo_esperado_pen",
)


def predict_log_ratio(
    artifact: Mapping[str, Any], table: pd.DataFrame, X: pd.DataFrame
) -> tuple[pd.Series, pd.Series]:
    """Predicción de ``log(razón)`` para la población y su origen (histórico o nuevo)."""
    scored = table["es_poblacion"].astype(bool)
    stored = table["ocid"].map(artifact["oof"])
    known = scored & stored.notna()
    new = scored & ~known
    prediction = pd.Series(np.nan, index=table.index, dtype="float64")
    prediction.loc[known] = stored[known].astype("float64")
    if new.any():
        prediction.loc[new] = artifact["estimator"].predict(X[new])
    origin = pd.Series(np.where(known, ORIGIN_HISTORICAL, ORIGIN_NEW), index=table.index)
    return prediction[scored], origin[scored]


def score_processes(
    artifact: Mapping[str, Any], gold: Mapping[str, pd.DataFrame], *, today: date | None = None
) -> pd.DataFrame:
    """Tabla ``pred_monto_esperado``: una fila por proceso de la población."""
    config = artifact["config"]
    population = config.get("population") or {}
    specs = specs_from_dicts(artifact["features"])
    table = build_modeling_table(gold, population)
    X = build_features(table, specs, config.get("entity_types"))
    prediction, origin = predict_log_ratio(artifact, table, X)
    scored = prediction.index
    anomalies_cfg = config.get("anomalies") or {}
    segment_by = str(anomalies_cfg.get("segment_by", "categoria"))
    bounds = (float(population.get("min_ratio", 0.05)), float(population.get("max_ratio", 5.0)))
    deviations = anomaly.score_deviations(
        prediction,
        table.loc[scored],
        X.loc[scored, segment_by],
        artifact["scales"],
        anomalies_cfg,
        bounds,
    )
    base_columns = [
        "proceso_key",
        "ocid",
        "valor_referencial_pen",
        "monto_adjudicado_pen",
        "ratio_adjudicado_referencial",
        "es_adjudicado_igual_referencial",
    ]
    result = pd.concat([table.loc[scored, base_columns], deviations], axis=1)
    result["origen_prediccion"] = origin
    result["modelo_version"] = str(artifact["version"])
    result["modelo_aceptado"] = bool(artifact["accepted"])
    result["fecha_prediccion"] = pd.Timestamp(today or date.today())
    for column in MONEY_COLUMNS:
        result[column] = result[column].round(2)
    for column in ("ratio_adjudicado_referencial", "ratio_esperado", "pct_desviacion"):
        result[column] = result[column].round(6)
    for column in ("residuo_log", "z_robusto"):
        result[column] = result[column].round(4)
    result = result[list(OUTPUT_COLUMNS)].reset_index(drop=True)
    logger.info(
        "Procesos evaluados: %d (%s)",
        len(result),
        ", ".join(f"{k} {v}" for k, v in summarize(result)["por_tipo"].items()),
    )
    return result


def summarize(predictions: pd.DataFrame) -> dict[str, Any]:
    """Conteos por tipo de desviación y por origen de la predicción."""
    by_type = predictions["tipo_desviacion"].value_counts()
    return {
        "procesos": int(len(predictions)),
        "atipicos": int(predictions["es_atipico"].sum()),
        "por_tipo": {label: int(by_type.get(label, 0)) for label in anomaly.DEVIATION_LABELS},
        "por_origen": {
            str(k): int(v) for k, v in predictions["origen_prediccion"].value_counts().items()
        },
    }


def export_predictions(
    predictions: pd.DataFrame,
    directory: str | Path,
    name: str,
    formats: Iterable[str] = ("parquet", "csv"),
    csv_options: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    """Guarda las predicciones en ``data/predictions/<name>.parquet`` y ``.csv``."""
    formats = set(formats)
    written: dict[str, Path] = {}
    if "parquet" in formats:
        written["parquet"] = export_parquet(predictions, Path(directory) / f"{name}.parquet")
    if "csv" in formats:
        written["csv"] = export_csv(
            predictions, Path(directory) / f"{name}.csv", **dict(csv_options or {})
        )
    return written


def load_to_database(
    predictions: pd.DataFrame,
    *,
    table: str,
    sql_dir: str | Path,
    profile: str | None = None,
    db_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Carga las predicciones en su tabla (full refresh) y recrea las vistas de ML.

    Las vistas unen las predicciones con la capa gold, así que solo se crean si la base
    ya tiene esas tablas (``contrataciones run`` con carga a la base de datos).
    """
    sql_dir = Path(sql_dir)
    with DatabaseConnector(profile, config=dict(db_config) if db_config else None) as db:
        ensure_tables(db, sql_dir / "ddl_ml")
        counts = load_tables(db, {table: predictions}, order=(table,))
        views: list[str] = []
        if all(db.table_exists(name) for name in VIEW_DEPENDENCIES):
            views = create_views(db, sql_dir / "views_ml")
        else:
            logger.warning(
                "La base de datos no tiene la capa gold: no se crean las vistas de ML. "
                "Ejecuta 'contrataciones run' con carga a la base de datos y vuelve a predecir."
            )
        return {"filas": int(counts[table]), "vistas": views, "base_de_datos": db.masked_url}
