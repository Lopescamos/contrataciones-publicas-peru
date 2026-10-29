"""Orquestación del modelo de monto esperado: entrenar y predecir de punta a punta.

:func:`run_training`
    capa gold -> dataset de modelado -> features -> entrenamiento y evaluación ->
    ``data/features/dataset_modelado.parquet`` + modelo, catálogo y bitácora en ``models/``.

:func:`run_prediction`
    modelo registrado + capa gold -> ``pred_monto_esperado`` (Parquet, CSV, base de
    datos) + ``data/exports/reporte_montos_atipicos.xlsx``.

Ambas devuelven un resultado con las salidas y las advertencias; la impresión en
pantalla es tarea de la CLI (``models/cli.py``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from contrataciones.export.csv_exporter import export_parquet
from contrataciones.export.excel_exporter import ExcelStyle
from contrataciones.features.builder import build_features
from contrataciones.features.catalog import FeatureSpec, load_feature_specs
from contrataciones.features.dataset import (
    CONTROL_COLUMNS,
    MOTIVO_RAZON_FUERA_DE_RANGO,
    build_modeling_table,
    load_gold,
    population_summary,
    read_manifest,
)
from contrataciones.models import predictor, registry, report, trainer
from contrataciones.utils.config_loader import ConfigError, load_config, resolve_path
from contrataciones.utils.helpers import StepTimer
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

DATASET_FILE = "dataset_modelado.parquet"
SYNTHETIC_SOURCE = "sample"


@dataclass
class TrainingRun:
    """Resultado de un entrenamiento."""

    version: str
    selected: str
    accepted: bool
    improvement: float
    threshold: float
    split_dates: dict[str, str]
    partitions: dict[str, int]
    population: dict[str, Any]
    validation: dict[str, float]
    test: dict[str, float]
    data: dict[str, Any]
    outputs: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    durations: dict[str, float] = field(default_factory=dict)


@dataclass
class PredictionRun:
    """Resultado de una predicción."""

    version: str
    accepted: bool
    status: str
    summary: dict[str, Any]
    database: dict[str, Any] | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    durations: dict[str, float] = field(default_factory=dict)


def _paths(settings: dict[str, Any]) -> dict[str, Path]:
    paths = settings.get("paths") or {}
    required = ("curated", "features", "predictions", "models", "exports", "sql")
    missing = [key for key in required if key not in paths]
    if missing:
        raise ConfigError(f"Faltan rutas en settings.yaml: {', '.join(missing)}.")
    return {key: resolve_path(paths[key]) for key in required}


def _dataset(table: pd.DataFrame, X: pd.DataFrame, result: trainer.TrainingResult) -> pd.DataFrame:
    """Dataset de modelado: columnas de control, partición, bloque, predicción y features."""
    clash = set(CONTROL_COLUMNS) & set(X.columns)
    if clash:
        raise ConfigError(f"Hay features con nombre de columna de control: {sorted(clash)}.")
    dataset = table[list(CONTROL_COLUMNS)].copy()
    dataset["particion"] = result.partitions
    dataset["bloque"] = result.blocks
    dataset["prediccion_fuera_de_muestra"] = result.oof
    return pd.concat([dataset, X], axis=1)


def build_artifact(
    *,
    version: str,
    config: dict[str, Any],
    specs: list[FeatureSpec],
    table: pd.DataFrame,
    result: trainer.TrainingResult,
    data: dict[str, Any],
    trained_at: datetime,
) -> dict[str, Any]:
    """Artefacto que se guarda en ``models/trained``: todo lo necesario para predecir.

    Incluye la predicción fuera de muestra de cada proceso del histórico (por ``ocid``)
    para que al predecir ningún proceso se evalúe con un modelo que lo vio.
    """
    scored = table["es_poblacion"]
    return {
        "version": version,
        "model_name": str(config.get("model_name") or "monto_esperado"),
        "trained_at": trained_at.isoformat(timespec="seconds"),
        "selected": result.selected,
        "accepted": result.accepted,
        "improvement": result.improvement,
        "estimator": result.estimator,
        "features": [spec.to_dict() for spec in specs],
        "config": {
            key: config.get(key)
            for key in ("population", "entity_types", "split", "models", "anomalies")
        },
        "scales": result.scales,
        "oof": pd.Series(result.oof[scored].to_numpy(), index=table.loc[scored, "ocid"].to_numpy()),
        "metrics": result.metrics,
        "importance": result.importance.to_dict(orient="records"),
        "split_dates": result.dates.to_dict(),
        "data": data,
        "library_versions": registry.library_versions(),
    }


def run_training(
    *,
    settings: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> TrainingRun:
    """Entrena el modelo con la capa gold actual y lo registra en ``models/``."""
    settings = settings or load_config("settings")
    config = config or load_config("model_config")
    now = now or datetime.now()
    paths = _paths(settings)
    timer = StepTimer()

    with timer.step("ml_1_dataset"):
        manifest = read_manifest(paths["curated"])
        gold = load_gold(paths["curated"])
        specs = load_feature_specs(config.get("features"))
        table = build_modeling_table(gold, config.get("population"))
        X = build_features(table, specs, config.get("entity_types"))
        population = population_summary(table)

    with timer.step("ml_2_entrenamiento"):
        result = trainer.train_model(table, X, specs, config)

    with timer.step("ml_3_registro"):
        version = registry.new_version(str(config.get("model_name") or "monto_esperado"), now)
        source = manifest.get("source")
        data = {
            "run_id": manifest.get("run_id"),
            "fuente": source,
            "sinteticos": source == SYNTHETIC_SOURCE,
            **population,
        }
        artifact = build_artifact(
            version=version,
            config=config,
            specs=specs,
            table=table,
            result=result,
            data=data,
            trained_at=now,
        )
        model_path = registry.save_model(artifact, paths["models"])
        dataset_path = export_parquet(_dataset(table, X, result), paths["features"] / DATASET_FILE)
        partitions = {str(k): int(v) for k, v in result.partitions.value_counts().items()}
        test = result.metrics["prueba"]
        registry.append_to_catalog(
            paths["models"],
            {
                "version": version,
                "fecha": now.isoformat(timespec="seconds"),
                "modelo_seleccionado": result.selected,
                "aceptado": result.accepted,
                "mejora_vs_linea_base": result.improvement,
                "mae_log_prueba": test[result.selected]["mae_log"],
                "mae_log_linea_base": test[trainer.BASELINE]["mae_log"],
                "n_entrenamiento": partitions.get(trainer.PARTITION_TRAIN, 0),
                "n_validacion": partitions.get(trainer.PARTITION_VALIDATION, 0),
                "n_prueba": partitions.get(trainer.PARTITION_TEST, 0),
                "run_id": manifest.get("run_id"),
                "fuente": source,
                "datos_sinteticos": source == SYNTHETIC_SOURCE,
                "features": [spec.name for spec in specs],
            },
        )
        log_path = registry.write_experiment_log(
            paths["models"],
            version,
            {
                "version": version,
                "fecha": now.isoformat(timespec="seconds"),
                "datos": data,
                "division": {**result.dates.to_dict(), "particiones": partitions},
                "metricas": result.metrics,
                "metricas_por_segmento": result.segment_metrics.to_dict(orient="records"),
                "importancia": result.importance.to_dict(orient="records"),
                "escalas_atipicos": result.scales,
                "features": [spec.to_dict() for spec in specs],
                "configuracion": config,
                "versiones_librerias": registry.library_versions(),
            },
        )

    threshold = float((config.get("models") or {}).get("min_improvement_vs_baseline", 0.10))
    warnings = _training_warnings(result, specs, data, population, config, threshold)
    for warning in warnings:
        logger.warning(warning)
    return TrainingRun(
        version=version,
        selected=result.selected,
        accepted=result.accepted,
        improvement=result.improvement,
        threshold=threshold,
        split_dates=result.dates.to_dict(),
        partitions=partitions,
        population=population,
        validation={
            name: values["mae_log"] for name, values in result.metrics["validacion"].items()
        },
        test={name: values["mae_log"] for name, values in result.metrics["prueba"].items()},
        data=data,
        outputs={
            "modelo": str(model_path),
            "dataset": str(dataset_path),
            "experimento": str(log_path),
        },
        warnings=warnings,
        durations=timer.durations,
    )


def _training_warnings(
    result: trainer.TrainingResult,
    specs: list[Any],
    data: dict[str, Any],
    population: dict[str, Any],
    config: dict[str, Any],
    threshold: float,
) -> list[str]:
    warnings = []
    if data.get("sinteticos"):
        warnings.append(
            "Entrenado con datos sintéticos (fuente sample): sirve para probar el flujo, pero "
            "las métricas no dicen nada de la calidad del modelo."
        )
    if not result.accepted:
        gain = result.improvement
        shown = f"{gain:.1%}" if math.isfinite(gain) else "sin dato"
        warnings.append(
            f"El modelo no reduce el error de la línea base en al menos {threshold:.0%} "
            f"(mejora: {shown}): queda registrado como no aceptado."
        )
    conditional = [spec.name for spec in specs if spec.conditional]
    if conditional and not data.get("sinteticos"):
        warnings.append(
            f"Features condicionales ({', '.join(conditional)}): confirma con la auditoría de la "
            "Fase 0 (notebooks/ml/01_auditoria_fuga_de_datos.ipynb) que se publican antes de la "
            "buena pro."
        )
    out_of_range = population["motivos_exclusion"].get(MOTIVO_RAZON_FUERA_DE_RANGO, 0)
    if out_of_range:
        bounds = config.get("population") or {}
        warnings.append(
            f"{out_of_range} procesos con razón adjudicado/referencial fuera de "
            f"[{bounds.get('min_ratio', 0.05)}, {bounds.get('max_ratio', 5.0)}]: no se usan para "
            "entrenar y se reportan como 'Revisar datos'."
        )
    return warnings


def run_prediction(
    *,
    version: str | None = None,
    load_database: bool | None = None,
    db_profile: str | None = None,
    export_excel: bool | None = None,
    settings: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    export_config: dict[str, Any] | None = None,
    today: date | None = None,
) -> PredictionRun:
    """Puntúa la capa gold actual con un modelo registrado y exporta los resultados."""
    settings = settings or load_config("settings")
    config = config or load_config("model_config")
    export_config = export_config or load_config("export_config")
    output = config.get("output") or {}
    paths = _paths(settings)
    timer = StepTimer()
    warnings: list[str] = []
    outputs: dict[str, str] = {}
    database: dict[str, Any] | None = None
    status = "ok"

    with timer.step("ml_4_prediccion"):
        artifact = registry.load_model(
            paths["models"], version, str(config.get("model_name") or "monto_esperado")
        )
        manifest = read_manifest(paths["curated"])
        gold = load_gold(paths["curated"])
        predictions = predictor.score_processes(artifact, gold, today=today)
        summary = predictor.summarize(predictions)

    with timer.step("ml_5_exportacion"):
        table_name = str(output.get("table") or "pred_monto_esperado")
        written = predictor.export_predictions(
            predictions,
            paths["predictions"],
            table_name,
            formats=output.get("formats") or ("parquet", "csv"),
            csv_options=export_config.get("csv") or {},
        )
        outputs.update({f"predicciones_{kind}": str(path) for kind, path in written.items()})
        if export_excel is None or export_excel:
            excel_name = str(output.get("excel_report") or "reporte_montos_atipicos")
            excel_path = report.write_report(
                predictions,
                artifact,
                gold,
                paths["exports"] / f"{excel_name}.xlsx",
                style=ExcelStyle.from_config(export_config.get("excel") or {}),
                max_rows=int(output.get("excel_max_rows", 500)),
            )
            outputs["reporte_excel"] = str(excel_path)

    use_database = (
        bool(output.get("load_database", True)) if load_database is None else load_database
    )
    if use_database:
        with timer.step("ml_6_base_de_datos"):
            try:
                database = predictor.load_to_database(
                    predictions, table=table_name, sql_dir=paths["sql"], profile=db_profile
                )
                outputs["base_de_datos"] = database["base_de_datos"]
            except Exception as exc:  # noqa: BLE001 - se informa y el resto de salidas queda
                status = "parcial"
                warnings.append(f"No se pudo cargar la base de datos: {exc}")

    data = artifact.get("data") or {}
    if not artifact.get("accepted"):
        warnings.append(
            "El modelo no fue aceptado (no supera a la línea base): interpreta los montos "
            "atípicos con cautela."
        )
    if data.get("run_id") and manifest.get("run_id") and data["run_id"] != manifest["run_id"]:
        new = summary["por_origen"].get(predictor.ORIGIN_NEW, 0)
        warnings.append(
            f"El modelo se entrenó con la corrida {data['run_id']} y se aplica a la corrida "
            f"{manifest['run_id']}: {new} procesos nuevos se puntúan con el modelo final."
        )
    if data.get("sinteticos") and manifest.get("source") not in (None, SYNTHETIC_SOURCE):
        warnings.append(
            "Modelo entrenado con datos sintéticos aplicado a datos reales: vuelve a entrenar "
            "con contrataciones-ml train."
        )
    for warning in warnings:
        logger.warning(warning)
    if status == "ok" and warnings:
        status = "ok_con_advertencias"
    return PredictionRun(
        version=str(artifact["version"]),
        accepted=bool(artifact.get("accepted")),
        status=status,
        summary=summary,
        database=database,
        outputs=outputs,
        warnings=warnings,
        durations=timer.durations,
    )
