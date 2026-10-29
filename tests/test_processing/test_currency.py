"""Pruebas de conversión de moneda."""

import pandas as pd

from contrataciones.processing.currency import (
    convert_to_pen,
    foreign_with_source_pen,
    missing_rate_mask,
    prepare_rates,
)

RATES = pd.DataFrame(
    {
        "fecha": ["2025-01-02", "2025-01-03", "2025-01-06"],
        "moneda": ["USD", "USD", "USD"],
        "tipo_cambio": [3.70, 3.75, 3.80],
    }
)


def test_convert_to_pen_uses_last_available_rate():
    frame = pd.DataFrame(
        {
            "monto": [100.0, 100.0, 100.0, 100.0, None],
            "moneda": ["PEN", "USD", "USD", "USD", "USD"],
            "fecha": pd.to_datetime(
                ["2025-01-05", "2025-01-03", "2025-01-05", "2025-03-01", "2025-01-03"]
            ),
        }
    )
    result = convert_to_pen(frame, "monto", "moneda", "fecha", RATES, "monto_pen", max_gap_days=10)
    assert result["monto_pen"].iloc[0] == 100.0  # soles: se copia
    assert result["monto_pen"].iloc[1] == 375.0  # mismo día
    assert result["monto_pen"].iloc[2] == 375.0  # domingo -> último día hábil previo
    assert pd.isna(result["monto_pen"].iloc[3])  # sin tipo de cambio dentro de la ventana
    assert pd.isna(result["monto_pen"].iloc[4])  # sin monto


def test_missing_rate_mask_and_empty_rates():
    frame = pd.DataFrame(
        {
            "monto": [10.0, 10.0],
            "moneda": ["USD", "PEN"],
            "fecha": pd.to_datetime(["2025-01-03", "2025-01-03"]),
        }
    )
    result = convert_to_pen(frame, "monto", "moneda", "fecha", None, "monto_pen")
    assert missing_rate_mask(result, "monto", "moneda", "monto_pen").tolist() == [True, False]
    assert prepare_rates(None).empty


def test_convert_to_pen_prefers_amount_published_in_soles():
    frame = pd.DataFrame(
        {
            "monto": [100.0, 100.0, 100.0, 100.0],
            "moneda": ["USD", "USD", "USD", "PEN"],
            "monto_pen_fuente": [372.5, None, 0.0, 100.0],
            "fecha": pd.to_datetime(["2025-01-03"] * 4),
        }
    )
    assert foreign_with_source_pen(frame, "moneda", "monto_pen_fuente").tolist() == [
        True,
        False,
        False,  # 0 = no informado
        False,  # ya está en soles
    ]
    result = convert_to_pen(
        frame, "monto", "moneda", "fecha", RATES, "monto_pen", source_pen_col="monto_pen_fuente"
    )
    assert result["monto_pen"].tolist() == [372.5, 375.0, 375.0, 100.0]
