"""Evaluación del modelo de monto esperado.

El modelo predice ``log(monto adjudicado / valor referencial)``. Como
``log(monto) = log(referencial) + log(razón)``, el error en escala log es el mismo para
la razón y para el monto. Métricas:

* ``mae_log`` y ``rmse_log``: principales; ``exp(mae_log) - 1`` es el error relativo típico.
* ``r2_log_ratio``: el R² honesto (qué parte de la variación del descuento se explica).
* ``r2_log_monto``: sale cercano a 1 solo porque el referencial explica la escala; se
  informa con esa advertencia.
* ``mdape`` y ``wape``: lectura en soles (el WAPE pondera por gasto).

El criterio decisivo es la mejora frente a la línea base B1 (mediana de la razón por
método y categoría): ``mejora = 1 - mae_modelo / mae_linea_base``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

METRIC_NAMES: tuple[str, ...] = (
    "mae_log",
    "rmse_log",
    "r2_log_ratio",
    "r2_log_monto",
    "mdape",
    "wape",
)


def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) < 2:
        return float("nan")
    total = float(((y_true - y_true.mean()) ** 2).sum())
    if total == 0:
        return float("nan")
    return 1.0 - float(((y_true - y_pred) ** 2).sum()) / total


def regression_metrics(y_true: Any, y_pred: Any, log_reference: Any) -> dict[str, float]:
    """Métricas de una predicción de ``log(razón)``.

    ``log_reference`` es ``log(valor referencial)`` de cada proceso (para pasar a soles).
    """
    actual = np.asarray(y_true, dtype="float64")
    predicted = np.asarray(y_pred, dtype="float64")
    reference = np.asarray(log_reference, dtype="float64")
    if actual.size == 0:
        return {"n": 0, **{name: float("nan") for name in METRIC_NAMES}}
    error = predicted - actual
    amount_true = np.exp(reference + actual)
    amount_pred = np.exp(reference + predicted)
    absolute = np.abs(amount_pred - amount_true)
    return {
        "n": int(actual.size),
        "mae_log": float(np.mean(np.abs(error))),
        "rmse_log": float(np.sqrt(np.mean(error**2))),
        "r2_log_ratio": _r2(actual, predicted),
        "r2_log_monto": _r2(reference + actual, reference + predicted),
        "mdape": float(np.median(absolute / amount_true)),
        "wape": float(absolute.sum() / amount_true.sum()),
    }


def improvement(model_value: float, baseline_value: float) -> float:
    """Reducción relativa de una métrica de error frente a la línea base."""
    if not baseline_value or not math.isfinite(baseline_value) or not math.isfinite(model_value):
        return float("nan")
    return 1.0 - float(model_value) / float(baseline_value)


def value_quintiles(values: pd.Series) -> pd.Series:
    """Quintil del valor referencial (``Q1 (menor)`` ... ``Q5 (mayor)``)."""
    ranks = values.rank(method="first")
    buckets = pd.qcut(ranks, q=min(5, max(1, int(ranks.notna().sum()))), labels=False)
    labels = {0: "Q1 (menor)", 1: "Q2", 2: "Q3", 3: "Q4", 4: "Q5 (mayor)"}
    return buckets.map(labels).astype(object)


def segment_metrics(frame: pd.DataFrame, dimensions: Sequence[str]) -> pd.DataFrame:
    """MAE (log) del modelo y de la línea base por segmento.

    ``frame`` trae ``y_real``, ``y_modelo``, ``y_linea_base`` y una columna por dimensión.
    """
    error_model = (frame["y_modelo"] - frame["y_real"]).abs()
    error_base = (frame["y_linea_base"] - frame["y_real"]).abs()
    tables = []
    for dimension in dimensions:
        grouped = pd.DataFrame(
            {
                "segmento": frame[dimension].astype(str),
                "modelo": error_model,
                "base": error_base,
            }
        ).groupby("segmento", sort=True)
        stats = grouped.agg(
            n_procesos=("modelo", "size"),
            mae_log_modelo=("modelo", "mean"),
            mae_log_linea_base=("base", "mean"),
        ).reset_index()
        stats.insert(0, "dimension", dimension)
        tables.append(stats)
    result = pd.concat(tables, ignore_index=True)
    base = result["mae_log_linea_base"].where(result["mae_log_linea_base"] > 0)
    result["pct_mejora"] = 1 - result["mae_log_modelo"] / base
    return result


def permutation_importance_table(
    estimator: Any,
    X: pd.DataFrame,
    y: Any,
    *,
    n_repeats: int = 5,
    random_state: int = 2026,
) -> pd.DataFrame:
    """Cuánto empeora el MAE (log) al desordenar cada variable en los datos de prueba."""
    result = permutation_importance(
        estimator,
        X,
        y,
        scoring="neg_mean_absolute_error",
        n_repeats=int(n_repeats),
        random_state=int(random_state),
    )
    table = pd.DataFrame(
        {
            "variable": list(X.columns),
            "aumento_mae_log": result.importances_mean,
            "desviacion": result.importances_std,
        }
    )
    return table.sort_values("aumento_mae_log", ascending=False, ignore_index=True)
