"""Pruebas de las reglas de calidad de datos."""

import numpy as np
import pandas as pd

from contrataciones.processing.validator import (
    check_allowed_values,
    check_date_order,
    check_not_null,
    check_range,
    check_referential,
    check_unique,
    check_valid_ruc,
    profile_dataframe,
    summarize_quality,
)
from tests.conftest import SUNAT_RUC


def test_check_not_null_and_threshold():
    frame = pd.DataFrame({"a": [1, None, 3, 4]})
    strict = check_not_null(frame, "t", "a")
    tolerant = check_not_null(frame, "t", "a", max_pct=30)
    assert strict.filas_con_problema == 1 and strict.pct_problema == 25.0
    assert strict.estado == "FALLA" and tolerant.estado == "OK"


def test_check_unique_and_referential():
    child = pd.DataFrame({"id": [1, 1, 2, 9]})
    parent = pd.DataFrame({"id": [1, 2]})
    assert check_unique(child, "t", ["id"]).filas_con_problema == 1
    referential = check_referential(child, "id", parent, "id", "t", parent_name="padre")
    assert referential.filas_con_problema == 1
    assert "padre.id" in referential.regla


def test_check_range_counts_only_present_values():
    frame = pd.DataFrame({"monto": [10.0, 0.0, -5.0, np.nan]})
    result = check_range(frame, "t", "monto", min_value=0, inclusive=False)
    assert result.filas_evaluadas == 3 and result.filas_con_problema == 2
    assert result.regla == "monto > 0"


def test_check_allowed_values_ruc_and_dates():
    frame = pd.DataFrame(
        {
            "moneda": ["PEN", "USD", "XYZ", None],
            "ruc": [SUNAT_RUC, "20131312954", None, SUNAT_RUC],
            "inicio": pd.to_datetime(["2025-01-01", "2025-02-01", None, "2025-03-01"]),
            "fin": pd.to_datetime(["2025-01-10", "2025-01-01", "2025-01-01", None]),
        }
    )
    assert check_allowed_values(frame, "t", "moneda", ["PEN", "USD"]).filas_con_problema == 1
    assert check_valid_ruc(frame, "t").filas_con_problema == 1
    order = check_date_order(frame, "t", "inicio", "fin")
    assert order.filas_evaluadas == 2 and order.filas_con_problema == 1


def test_profile_and_summary():
    profile = profile_dataframe(pd.DataFrame({"a": [1, 2, None], "b": ["x", "x", "y"]}), "t")
    assert profile.set_index("columna").loc["a", "nulos"] == 1
    assert profile.set_index("columna").loc["b", "valores_unicos"] == 2
    report = pd.DataFrame(
        {"estado": ["OK", "FALLA", "FALLA"], "severidad": ["ERROR", "ERROR", "ADVERTENCIA"]}
    )
    assert summarize_quality(report) == {
        "reglas": 3,
        "ok": 1,
        "fallas": 2,
        "fallas_error": 1,
        "fallas_advertencia": 1,
    }
