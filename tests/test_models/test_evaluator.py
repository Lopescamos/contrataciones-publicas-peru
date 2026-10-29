"""Pruebas de las métricas de evaluación."""

import math

import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor

from contrataciones.models import evaluator


def test_regression_metrics_known_values():
    y_true = np.array([0.0, 0.1])
    y_pred = np.array([0.1, 0.1])
    log_reference = np.zeros(2)  # referencial de S/ 1: monto = exp(log razón)
    metrics = evaluator.regression_metrics(y_true, y_pred, log_reference)
    assert metrics["n"] == 2
    assert metrics["mae_log"] == pytest.approx(0.05)
    assert metrics["rmse_log"] == pytest.approx(math.sqrt(0.005))
    error = math.exp(0.1) - 1.0
    assert metrics["mdape"] == pytest.approx(error / 2)  # mediana de [error, 0]
    assert metrics["wape"] == pytest.approx(error / (1 + math.exp(0.1)))
    assert metrics["r2_log_ratio"] == pytest.approx(-1.0)


def test_r2_of_log_amount_is_inflated_by_the_reference_value():
    rng = np.random.default_rng(1)
    y_true = rng.normal(-0.1, 0.05, 200)
    y_pred = np.full(200, -0.1)  # no explica nada del descuento
    log_reference = rng.normal(12, 1.5, 200)
    metrics = evaluator.regression_metrics(y_true, y_pred, log_reference)
    assert metrics["r2_log_ratio"] < 0.05
    assert metrics["r2_log_monto"] > 0.99


def test_empty_metrics_are_nan():
    metrics = evaluator.regression_metrics([], [], [])
    assert metrics["n"] == 0
    assert math.isnan(metrics["mae_log"])


def test_improvement():
    assert evaluator.improvement(0.08, 0.10) == pytest.approx(0.2)
    assert evaluator.improvement(0.12, 0.10) == pytest.approx(-0.2)
    assert math.isnan(evaluator.improvement(0.1, 0.0))


def test_value_quintiles():
    labels = evaluator.value_quintiles(pd.Series(range(10), dtype="float64"))
    assert labels.iloc[0] == "Q1 (menor)"
    assert labels.iloc[-1] == "Q5 (mayor)"
    assert labels.value_counts().tolist() == [2] * 5


def test_segment_metrics():
    frame = pd.DataFrame(
        {
            "y_real": [0.0, 0.0, 0.0, 0.0],
            "y_modelo": [0.1, 0.1, 0.0, 0.0],
            "y_linea_base": [0.2, 0.2, 0.0, 0.0],
            "categoria": ["Obras", "Obras", "Bienes", "Bienes"],
        }
    )
    result = evaluator.segment_metrics(frame, ["categoria"]).set_index("segmento")
    assert result.loc["Obras", "mae_log_modelo"] == pytest.approx(0.1)
    assert result.loc["Obras", "pct_mejora"] == pytest.approx(0.5)
    assert math.isnan(result.loc["Bienes", "pct_mejora"])  # línea base sin error
    assert (result["dimension"] == "categoria").all()


def test_permutation_importance_table():
    X = pd.DataFrame({"a": np.arange(20.0), "b": np.zeros(20)})
    y = X["a"] * 2
    model = DummyRegressor().fit(X, y)
    table = evaluator.permutation_importance_table(model, X, y, n_repeats=2)
    assert list(table.columns) == ["variable", "aumento_mae_log", "desviacion"]
    assert set(table["variable"]) == {"a", "b"}
