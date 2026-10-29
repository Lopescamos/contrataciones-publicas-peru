"""Conversión de montos a soles (PEN) con tipo de cambio diario.

Orden de preferencia para cada monto en moneda extranjera:

1. El monto en soles publicado por la fuente (el OECE incluye ``value.amount_PEN``
   en el valor referencial), si es positivo.
2. El monto x el último tipo de cambio disponible en la fecha de la operación o
   en los ``max_gap_days`` días previos (fines de semana y feriados no tienen
   cotización).

Si no hay ninguno de los dos, el monto en soles queda vacío y se reporta en la
calidad de datos.
"""

from __future__ import annotations

import pandas as pd

from contrataciones.utils.constants import BASE_CURRENCY

RATE_COLUMNS = ["fecha", "moneda", "tipo_cambio", "fuente"]
EMPTY_RATES = pd.DataFrame(
    {
        "fecha": pd.Series(dtype="datetime64[ns]"),
        "moneda": pd.Series(dtype=object),
        "tipo_cambio": pd.Series(dtype="float64"),
        "fuente": pd.Series(dtype=object),
    }
)


def prepare_rates(rates: pd.DataFrame | None) -> pd.DataFrame:
    """Normaliza y ordena la tabla de tipos de cambio."""
    if rates is None or rates.empty:
        return EMPTY_RATES.copy()
    frame = rates.copy()
    frame["fecha"] = pd.to_datetime(frame["fecha"], errors="coerce").astype("datetime64[ns]")
    frame["moneda"] = frame["moneda"].astype(str).str.upper().str.strip()
    frame["tipo_cambio"] = pd.to_numeric(frame["tipo_cambio"], errors="coerce")
    if "fuente" not in frame.columns:
        frame["fuente"] = None
    frame = frame.dropna(subset=["fecha", "tipo_cambio"])
    frame = frame[frame["tipo_cambio"] > 0]
    return frame.sort_values(["fecha", "moneda"]).reset_index(drop=True)[RATE_COLUMNS]


def convert_to_pen(
    df: pd.DataFrame,
    amount_col: str,
    currency_col: str,
    date_col: str,
    rates: pd.DataFrame | None,
    out_col: str,
    max_gap_days: int = 10,
    base_currency: str = BASE_CURRENCY,
    source_pen_col: str | None = None,
) -> pd.DataFrame:
    """Agrega ``out_col`` con el monto expresado en soles.

    * Moneda PEN o vacía: se copia el monto (los datos del OECE están en soles
      salvo indicación contraria).
    * Otra moneda: monto en soles publicado por la fuente (``source_pen_col``)
      o, si no existe, monto x tipo de cambio de la fecha (o el último previo).
    """
    result = df.copy()
    amounts = pd.to_numeric(result[amount_col], errors="coerce")
    currency = result[currency_col].astype(object).where(result[currency_col].notna(), None)
    currency = currency.map(lambda v: str(v).upper().strip() if v is not None else None)
    is_base = currency.isna() | currency.eq(base_currency)
    converted = pd.Series(float("nan"), index=result.index, dtype="float64")
    converted[is_base] = amounts[is_base]

    published = foreign_with_source_pen(result, currency_col, source_pen_col, base_currency)
    if published.any():
        converted[published] = pd.to_numeric(result.loc[published, source_pen_col])

    table = prepare_rates(rates)
    pending = ~is_base & ~published & amounts.notna() & result[date_col].notna()
    if pending.any() and not table.empty:
        left = pd.DataFrame(
            {
                "_row": result.index[pending],
                "fecha": pd.to_datetime(result.loc[pending, date_col])
                .astype("datetime64[ns]")
                .dt.normalize(),
                "moneda": currency[pending].to_numpy(),
            }
        ).sort_values("fecha")
        merged = pd.merge_asof(
            left,
            table[["fecha", "moneda", "tipo_cambio"]],
            on="fecha",
            by="moneda",
            direction="backward",
            tolerance=pd.Timedelta(days=max_gap_days),
        ).set_index("_row")
        rate = merged["tipo_cambio"].reindex(result.index[pending])
        converted.loc[pending] = amounts[pending].to_numpy() * rate.to_numpy()
    result[out_col] = converted
    return result


def foreign_with_source_pen(
    df: pd.DataFrame,
    currency_col: str,
    source_pen_col: str | None,
    base_currency: str = BASE_CURRENCY,
) -> pd.Series:
    """True en montos en moneda extranjera que ya traen su equivalente en soles."""
    if not source_pen_col or source_pen_col not in df.columns:
        return pd.Series(False, index=df.index)
    currency = df[currency_col].astype(object).where(df[currency_col].notna(), None)
    foreign = currency.map(lambda v: v is not None and str(v).upper().strip() != base_currency)
    published = pd.to_numeric(df[source_pen_col], errors="coerce")
    return (foreign.astype(bool) & published.gt(0)).fillna(False).astype(bool)


def missing_rate_mask(
    df: pd.DataFrame, amount_col: str, currency_col: str, pen_col: str
) -> pd.Series:
    """True donde hay monto en moneda extranjera pero no se pudo convertir."""
    foreign = df[currency_col].notna() & df[currency_col].astype(str).str.upper().ne(BASE_CURRENCY)
    return foreign & df[amount_col].notna() & df[pen_col].isna()
