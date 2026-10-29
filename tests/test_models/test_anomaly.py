"""Pruebas de la escala robusta y de la clasificación de las desviaciones."""

import numpy as np
import pandas as pd
import pytest

from contrataciones.models import anomaly

CONFIG = {"z_threshold": 3.0, "min_deviation": 0.15}
BOUNDS = (0.05, 5.0)


def test_scale_floor_when_residuals_are_identical():
    residuals = pd.Series(np.zeros(50))
    scales = anomaly.robust_scales(residuals, pd.Series(["Obras"] * 50), min_scale=0.05)
    assert scales["Obras"]["escala"] == 0.05  # MAD = 0: sin piso todo sería atípico
    assert scales[anomaly.GLOBAL_SEGMENT]["centro"] == 0.0


def test_small_segments_fall_back_to_global_scale():
    rng = np.random.default_rng(0)
    residuals = pd.Series(rng.normal(0, 0.1, 100))
    segments = pd.Series(["Bienes"] * 90 + ["Obras"] * 10)
    scales = anomaly.robust_scales(residuals, segments, min_segment_size=30)
    assert set(scales) == {anomaly.GLOBAL_SEGMENT, "Bienes"}
    expected = 1.4826 * np.median(np.abs(residuals[:90] - np.median(residuals[:90])))
    assert scales["Bienes"]["escala"] == pytest.approx(max(expected, 0.05))


def test_robust_scales_requires_residuals():
    with pytest.raises(ValueError, match="No hay residuos"):
        anomaly.robust_scales(pd.Series([np.nan]), pd.Series(["Obras"]))


def score(ratios, predicted_log_ratio=0.0, segment="Bienes"):
    frame = pd.DataFrame(
        {
            "valor_referencial_pen": 100_000.0,
            "monto_adjudicado_pen": [100_000.0 * r for r in ratios],
            "ratio_adjudicado_referencial": ratios,
        }
    )
    scales = {
        anomaly.GLOBAL_SEGMENT: {"centro": 0.0, "escala": 0.1, "n": 100},
        "Bienes": {"centro": 0.0, "escala": 0.05, "n": 60},
    }
    prediction = pd.Series(predicted_log_ratio, index=frame.index, dtype="float64")
    segments = pd.Series(segment, index=frame.index)
    return anomaly.score_deviations(prediction, frame, segments, scales, CONFIG, BOUNDS)


def test_deviation_types():
    result = score([1.0, 1.25, 0.8, 1.10, 0.01, 6.0])
    assert result["tipo_desviacion"].tolist() == [
        anomaly.LABEL_NORMAL,
        anomaly.LABEL_OVERCOST,  # log(1.25) = 0.22 -> z = 4.5 y desviación +25 %
        anomaly.LABEL_UNDERCOST,  # log(0.8) = -0.22 -> z = -4.5 y desviación -20 %
        anomaly.LABEL_NORMAL,  # z = 1.9: dentro del rango esperado
        anomaly.LABEL_DATA_ERROR,  # razón 0.01 < 0.05
        anomaly.LABEL_DATA_ERROR,  # razón 6 > 5
    ]
    assert result["es_atipico"].tolist() == [False, True, True, False, False, False]


def test_minimum_deviation_is_required_even_with_large_z():
    # Con escala 0.02, una desviación de +12 % da z = 5.7, pero no llega al 15 % mínimo.
    frame = pd.DataFrame(
        {
            "valor_referencial_pen": [100.0],
            "monto_adjudicado_pen": [112.0],
            "ratio_adjudicado_referencial": [1.12],
        }
    )
    scales = {anomaly.GLOBAL_SEGMENT: {"centro": 0.0, "escala": 0.02, "n": 100}}
    result = anomaly.score_deviations(
        pd.Series([0.0]), frame, pd.Series(["X"]), scales, CONFIG, BOUNDS
    )
    assert result["z_robusto"].iloc[0] > 3
    assert result["tipo_desviacion"].iloc[0] == anomaly.LABEL_NORMAL


def test_expected_amount_and_range_are_consistent_with_z():
    result = score([1.0, 1.25], predicted_log_ratio=np.log(0.9))
    first = result.iloc[0]
    assert first["monto_esperado_pen"] == pytest.approx(90_000.0)
    assert first["ratio_esperado"] == pytest.approx(0.9)
    assert first["pct_desviacion"] == pytest.approx(100_000 / 90_000 - 1)
    # El rango esperado es [esperado x exp(-3 x escala), esperado x exp(+3 x escala)].
    assert first["monto_minimo_esperado_pen"] == pytest.approx(90_000 * np.exp(-0.15))
    assert first["monto_maximo_esperado_pen"] == pytest.approx(90_000 * np.exp(0.15))
    over = result.iloc[1]
    assert over["monto_maximo_esperado_pen"] < 125_000  # monto real fuera del rango esperado
    assert over["tipo_desviacion"] == anomaly.LABEL_OVERCOST


def test_segment_without_own_scale_reports_global():
    result = score([1.0], segment="Consultoría")
    assert result["segmento_escala"].iloc[0] == "Global"
    assert score([1.0])["segmento_escala"].iloc[0] == "Bienes"
