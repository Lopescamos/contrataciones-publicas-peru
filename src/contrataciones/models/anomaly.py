"""Clasificación de las desviaciones entre el monto adjudicado y el monto esperado.

* ``residuo = log(monto real) - log(monto esperado)``.
* La escala de cada segmento se estima con los residuos fuera de muestra:
  ``centro = mediana`` y ``escala = 1.4826 x MAD`` (equivale a la desviación estándar
  si los residuos fueran normales), con un piso (``min_scale``) porque la razón
  exacta 1.0 es tan frecuente en algunos segmentos que la MAD puede ser casi 0.
* ``z = (residuo - centro) / escala``. Un monto es atípico si ``|z|`` supera el umbral
  **y** la desviación relativa supera el mínimo (``min_deviation``).

Una desviación inusual no prueba una irregularidad: señala un proceso que conviene
revisar (puede ser una adjudicación parcial, un error de registro o un precio
realmente inusual).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

MAD_TO_STD = 1.4826
GLOBAL_SEGMENT = "__global__"

LABEL_NORMAL = "Normal"
LABEL_OVERCOST = "Sobrecosto inusual"
LABEL_UNDERCOST = "Subcosto inusual"
LABEL_DATA_ERROR = "Revisar datos"
DEVIATION_LABELS: tuple[str, ...] = (
    LABEL_NORMAL,
    LABEL_OVERCOST,
    LABEL_UNDERCOST,
    LABEL_DATA_ERROR,
)


def _stats(values: pd.Series, min_scale: float) -> dict[str, float]:
    center = float(values.median())
    mad = float((values - center).abs().median())
    return {
        "centro": center,
        "escala": max(MAD_TO_STD * mad, float(min_scale)),
        "n": int(len(values)),
    }


def robust_scales(
    residuals: pd.Series,
    segments: pd.Series,
    *,
    min_segment_size: int = 30,
    min_scale: float = 0.05,
) -> dict[str, dict[str, float]]:
    """Centro y escala robustos de los residuos, global y por segmento.

    Los segmentos con menos de ``min_segment_size`` residuos no tienen entrada propia:
    al puntuar usan la escala global.
    """
    values = pd.Series(residuals, dtype="float64").dropna()
    if values.empty:
        raise ValueError("No hay residuos para estimar la escala de los atípicos.")
    labels = pd.Series(segments).reindex(values.index).astype(str)
    scales = {GLOBAL_SEGMENT: _stats(values, min_scale)}
    for segment, group in values.groupby(labels):
        if len(group) >= int(min_segment_size):
            scales[str(segment)] = _stats(group, min_scale)
    return scales


def score_deviations(
    log_ratio_pred: pd.Series,
    frame: pd.DataFrame,
    segments: pd.Series,
    scales: Mapping[str, Mapping[str, float]],
    anomalies: Mapping[str, Any],
    ratio_bounds: tuple[float, float],
) -> pd.DataFrame:
    """Monto esperado, rango esperado, desviación y tipo de desviación por proceso.

    ``frame`` aporta ``valor_referencial_pen``, ``monto_adjudicado_pen`` y
    ``ratio_adjudicado_referencial`` con el mismo índice que ``log_ratio_pred``.
    """
    z_threshold = float(anomalies.get("z_threshold", 3.0))
    min_deviation = float(anomalies.get("min_deviation", 0.15))
    pred = pd.Series(log_ratio_pred, dtype="float64")
    reference = frame["valor_referencial_pen"].astype("float64")
    actual = frame["monto_adjudicado_pen"].astype("float64")
    ratio = frame["ratio_adjudicado_referencial"].astype("float64")

    labels = pd.Series(segments, index=pred.index).astype(str)
    fallback = scales[GLOBAL_SEGMENT]
    center = labels.map(lambda s: scales.get(s, fallback)["centro"]).astype("float64")
    scale = labels.map(lambda s: scales.get(s, fallback)["escala"]).astype("float64")
    segment_used = labels.where(labels.isin(list(scales)), GLOBAL_SEGMENT)

    residual = np.log(ratio) - pred
    z = (residual - center) / scale
    expected = reference * np.exp(pred)
    deviation = actual / expected - 1

    low, high = ratio_bounds
    data_error = ~ratio.between(low, high)
    over = (z >= z_threshold) & (deviation >= min_deviation) & ~data_error
    under = (z <= -z_threshold) & (deviation <= -min_deviation) & ~data_error
    kind = np.select(
        [data_error.to_numpy(), over.to_numpy(), under.to_numpy()],
        [LABEL_DATA_ERROR, LABEL_OVERCOST, LABEL_UNDERCOST],
        default=LABEL_NORMAL,
    )
    return pd.DataFrame(
        {
            "ratio_esperado": np.exp(pred),
            "monto_esperado_pen": expected,
            "monto_minimo_esperado_pen": reference * np.exp(pred + center - z_threshold * scale),
            "monto_maximo_esperado_pen": reference * np.exp(pred + center + z_threshold * scale),
            "pct_desviacion": deviation,
            "residuo_log": residual,
            "z_robusto": z,
            "tipo_desviacion": pd.Series(kind, index=pred.index).astype(object),
            "es_atipico": over | under,
            # Segmento cuya escala se usó ("Global" si el segmento tenía pocos casos).
            "segmento_escala": segment_used.replace(GLOBAL_SEGMENT, "Global"),
        },
        index=pred.index,
    )
