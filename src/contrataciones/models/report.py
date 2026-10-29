"""Reporte Excel de montos atípicos (``data/exports/reporte_montos_atipicos.xlsx``).

Hojas: resumen, procesos atípicos con su contexto, conteos por categoría, métricas del
modelo, importancia de las variables y notas de uso responsable. Usa el mismo formato
que el reporte ejecutivo del pipeline (:func:`export_multi_sheet`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from contrataciones.export.excel_exporter import ExcelStyle, export_multi_sheet
from contrataciones.features.dataset import date_from_key
from contrataciones.models import anomaly
from contrataciones.models.predictor import summarize
from contrataciones.models.trainer import BASELINE, GLOBAL_MEDIAN, RATIO_ONE

MODEL_LABELS: dict[str, str] = {
    BASELINE: "Línea base B1 (mediana por método y categoría)",
    GLOBAL_MEDIAN: "Mediana global",
    RATIO_ONE: "Adjudicado = referencial",
    "ridge": "Ridge",
    "hist_gradient_boosting": "HistGradientBoosting",
}
PARTITION_LABELS: dict[str, str] = {
    "validacion": "Validación",
    "prueba": "Prueba",
    "fuera_de_muestra": "Histórico fuera de muestra",
}
NOTES: tuple[str, ...] = (
    "El monto esperado estima cuánto debería costar el proceso según su perfil al convocarse "
    "(valor referencial, método, categoría, entidad, mes y plazo de consultas).",
    "Un monto atípico NO prueba una irregularidad: señala un proceso que conviene revisar. "
    "Verifica cada caso en la fuente oficial (SEACE).",
    "Causas frecuentes de un subcosto inusual: adjudicación parcial (solo algunos ítems), "
    "error de registro o una oferta realmente baja.",
    "El modelo mide la desviación respecto de lo esperado dado el valor referencial: no "
    "detecta un valor referencial inflado.",
    "Revisar datos: la razón adjudicado/referencial está fuera del rango plausible "
    "(probable error de registro); no se usa para entrenar.",
    "Si el modelo no fue aceptado (no supera a la línea base), interpreta los atípicos con "
    "cautela: el rango esperado se apoya sobre todo en la mediana de cada segmento.",
)


def describe_processes(predictions: pd.DataFrame, gold: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Agrega a las predicciones el contexto del proceso (entidad, método, categoría...)."""
    procesos = gold["fact_proceso"][
        ["proceso_key", "nomenclatura", "fecha_convocatoria_key", "entidad_key", "metodo_key"]
        + ["categoria_key"]
    ]
    entidades = gold["dim_entidad"][["entidad_key", "nombre", "departamento"]].rename(
        columns={"nombre": "entidad"}
    )
    metodos = gold["dim_metodo"][["metodo_key", "metodo_detalle"]]
    categorias = gold["dim_categoria"][["categoria_key", "categoria"]]
    merged = (
        predictions.merge(procesos, on="proceso_key", how="left")
        .merge(entidades, on="entidad_key", how="left")
        .merge(metodos, on="metodo_key", how="left")
        .merge(categorias, on="categoria_key", how="left")
    )
    merged["fecha_convocatoria"] = date_from_key(merged["fecha_convocatoria_key"])
    return merged


def _summary(predictions: pd.DataFrame, artifact: Mapping[str, Any]) -> pd.DataFrame:
    counts = summarize(predictions)
    metrics = artifact.get("metrics") or {}
    test = (metrics.get("prueba") or {}).get(artifact["selected"], {})
    data = artifact.get("data") or {}
    gain = artifact.get("improvement", float("nan"))
    rows = [
        ("Versión del modelo", artifact["version"]),
        ("Modelo seleccionado", MODEL_LABELS.get(artifact["selected"], artifact["selected"])),
        ("Modelo aceptado", "Sí" if artifact.get("accepted") else "No"),
        (
            "Mejora frente a la línea base (prueba)",
            f"{gain:.1%}" if isinstance(gain, float) and math.isfinite(gain) else "-",
        ),
        ("Criterio de aceptación", f"{metrics.get('criterio_aceptacion', 0.10):.0%}"),
        ("MAE log en prueba", round(float(test.get("mae_log", float("nan"))), 4)),
        ("Datos de entrenamiento (corrida)", data.get("run_id") or "-"),
        ("Fuente de los datos de entrenamiento", data.get("fuente") or "-"),
        ("Entrenado con datos sintéticos", "Sí" if data.get("sinteticos") else "No"),
        ("Procesos evaluados", counts["procesos"]),
    ]
    rows += [(f"Procesos: {label}", n) for label, n in counts["por_tipo"].items()]
    share = counts["atipicos"] / counts["procesos"] if counts["procesos"] else 0.0
    rows.append(("Porcentaje de atípicos", f"{share:.1%}"))
    return pd.DataFrame(rows, columns=["indicador", "valor"])


def _outliers(described: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    flagged = described[described["tipo_desviacion"] != anomaly.LABEL_NORMAL].copy()
    order = {anomaly.LABEL_OVERCOST: 0, anomaly.LABEL_UNDERCOST: 1, anomaly.LABEL_DATA_ERROR: 2}
    flagged["_orden"] = flagged["tipo_desviacion"].map(order)
    flagged["_z"] = flagged["z_robusto"].abs()
    flagged = flagged.sort_values(["_orden", "_z"], ascending=[True, False]).head(max_rows)
    flagged["es_adjudicado_igual_referencial"] = flagged["es_adjudicado_igual_referencial"].map(
        {True: "Sí", False: "No"}
    )
    flagged["z_robusto"] = flagged["z_robusto"].round(2)
    columns = [
        "ocid",
        "nomenclatura",
        "entidad",
        "departamento",
        "metodo_detalle",
        "categoria",
        "fecha_convocatoria",
        "valor_referencial_pen",
        "monto_adjudicado_pen",
        "monto_esperado_pen",
        "monto_minimo_esperado_pen",
        "monto_maximo_esperado_pen",
        "pct_desviacion",
        "z_robusto",
        "tipo_desviacion",
        "es_adjudicado_igual_referencial",
        "origen_prediccion",
    ]
    return flagged[columns].reset_index(drop=True)


def _by_category(described: pd.DataFrame) -> pd.DataFrame:
    frame = described.assign(
        n_sobrecosto=described["tipo_desviacion"].eq(anomaly.LABEL_OVERCOST),
        n_subcosto=described["tipo_desviacion"].eq(anomaly.LABEL_UNDERCOST),
        n_revisar_datos=described["tipo_desviacion"].eq(anomaly.LABEL_DATA_ERROR),
    )
    grouped = frame.groupby(frame["categoria"].fillna("Sin dato"))
    table = grouped.agg(
        n_procesos=("ocid", "size"),
        n_sobrecosto=("n_sobrecosto", "sum"),
        n_subcosto=("n_subcosto", "sum"),
        n_revisar_datos=("n_revisar_datos", "sum"),
    ).reset_index()
    table["pct_atipicos"] = (table["n_sobrecosto"] + table["n_subcosto"]) / table["n_procesos"]
    return table.sort_values("n_procesos", ascending=False, ignore_index=True)


def _metrics(artifact: Mapping[str, Any]) -> pd.DataFrame:
    metrics = artifact.get("metrics") or {}
    rows = []
    for partition in ("validacion", "prueba"):
        for name, values in (metrics.get(partition) or {}).items():
            rows.append({"particion": PARTITION_LABELS[partition], "modelo": name, **values})
    oof = metrics.get("fuera_de_muestra")
    if oof:
        rows.append(
            {
                "particion": PARTITION_LABELS["fuera_de_muestra"],
                "modelo": artifact["selected"],
                **oof,
            }
        )
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["modelo"] = table["modelo"].map(lambda n: MODEL_LABELS.get(n, n))
    table = table.rename(columns={"n": "n_procesos", "mdape": "pct_mdape", "wape": "pct_wape"})
    for column in ("mae_log", "rmse_log", "r2_log_ratio", "r2_log_monto"):
        table[column] = table[column].round(4)
    return table


def report_tables(
    predictions: pd.DataFrame,
    artifact: Mapping[str, Any],
    gold: Mapping[str, pd.DataFrame],
    *,
    max_rows: int = 500,
) -> dict[str, pd.DataFrame]:
    """Hojas del reporte (nombre de hoja -> DataFrame)."""
    described = describe_processes(predictions, gold)
    importance = pd.DataFrame(artifact.get("importance") or [])
    if not importance.empty:
        importance = importance.round({"aumento_mae_log": 5, "desviacion": 5})
    return {
        "Resumen": _summary(predictions, artifact),
        "Atípicos": _outliers(described, max_rows),
        "Por categoría": _by_category(described),
        "Métricas": _metrics(artifact),
        "Importancia": importance,
        "Notas": pd.DataFrame({"nota": list(NOTES)}),
    }


def write_report(
    predictions: pd.DataFrame,
    artifact: Mapping[str, Any],
    gold: Mapping[str, pd.DataFrame],
    path: str | Path,
    *,
    style: ExcelStyle | None = None,
    max_rows: int = 500,
) -> Path:
    """Escribe el reporte Excel de montos atípicos."""
    sheets = report_tables(predictions, artifact, gold, max_rows=max_rows)
    version = artifact["version"]
    titles = {
        "Resumen": ("Montos atípicos: resumen", f"Modelo {version}"),
        "Atípicos": (
            "Procesos con monto adjudicado inusual",
            f"Hasta {max_rows} casos, ordenados por tipo y por |z|. Una desviación no prueba "
            "una irregularidad.",
        ),
        "Por categoría": ("Atípicos por categoría", None),
        "Métricas": (
            "Métricas del modelo",
            "Escala log: exp(MAE) - 1 es el error relativo típico. El R² de log(monto) es alto "
            "solo porque el valor referencial explica la escala.",
        ),
        "Importancia": (
            "Importancia de las variables",
            "Aumento del MAE (log) al desordenar cada variable en la partición de prueba.",
        ),
        "Notas": ("Uso responsable", None),
    }
    return export_multi_sheet(sheets, path, style=style, titles=titles)
