"""Tipo de cambio desde la API de series estadísticas del BCRP (BCRPData).

Formato de la API (pública, sin clave):
    {base_url}/{series}/json/{periodo_inicial}/{periodo_final}/{idioma}

Respuesta JSON (resumen):
    {"config": {"series": [{"name": "..."}]},
     "periods": [{"name": "02.Ene.24", "values": ["3.7120"]}, ...]}

Los valores no disponibles llegan como ``"n.d."``. La serie por defecto es
PD04638PD: tipo de cambio interbancario, venta (S/ por US$), frecuencia diaria.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from contrataciones.ingestion.api_client import APIClient
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
USD_SELL_SERIES = "PD04638PD"

_MONTHS = {
    # español
    "ENE": 1,
    "FEB": 2,
    "MAR": 3,
    "ABR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SEP": 9,
    "SET": 9,
    "OCT": 10,
    "NOV": 11,
    "DIC": 12,
    # inglés
    "JAN": 1,
    "APR": 4,
    "AUG": 8,
    "DEC": 12,
}
_DAILY = re.compile(r"^(\d{1,2})\.([A-Za-z]{3})\.(\d{2,4})$")
_MONTHLY = re.compile(r"^([A-Za-z]{3})\.(\d{4})$")


def parse_bcrp_period(name: str) -> date | None:
    """Convierte el nombre de periodo del BCRP en fecha.

    >>> parse_bcrp_period("02.Ene.24")
    datetime.date(2024, 1, 2)
    >>> parse_bcrp_period("Set.2023")
    datetime.date(2023, 9, 1)
    """
    text = (name or "").strip()
    daily = _DAILY.match(text)
    if daily:
        day, month_txt, year_txt = daily.groups()
        month = _MONTHS.get(month_txt.upper())
        year = int(year_txt) + (2000 if len(year_txt) == 2 else 0)
        return date(year, month, int(day)) if month else None
    monthly = _MONTHLY.match(text)
    if monthly:
        month = _MONTHS.get(monthly.group(1).upper())
        return date(int(monthly.group(2)), month, 1) if month else None
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_bcrp_payload(payload: dict[str, Any], series_codes: list[str]) -> pd.DataFrame:
    """Convierte la respuesta JSON en filas ``(fecha, serie, valor)``."""
    rows: list[dict[str, Any]] = []
    for period in payload.get("periods", []) or []:
        period_date = parse_bcrp_period(str(period.get("name", "")))
        if period_date is None:
            continue
        for code, raw in zip(series_codes, period.get("values", []) or [], strict=False):
            value = _to_float(raw)
            if value is not None:
                rows.append({"fecha": pd.Timestamp(period_date), "serie": code, "valor": value})
    return pd.DataFrame(rows, columns=["fecha", "serie", "valor"])


class BCRPClient:
    """Cliente mínimo para la API de series del BCRP."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        language: str = "esp",
        timeout: float = 60,
        client: APIClient | None = None,
    ) -> None:
        self.language = language
        self.client = client or APIClient(base_url, timeout=timeout, max_retries=3)

    def get_series(
        self, series_codes: list[str], start: date | str, end: date | str
    ) -> pd.DataFrame:
        codes = "-".join(series_codes)
        endpoint = f"{codes}/json/{start}/{end}/{self.language}"
        payload = self.client.get_json(endpoint)
        if not isinstance(payload, dict):
            raise ValueError("Respuesta inesperada del BCRP (no es un objeto JSON)")
        return parse_bcrp_payload(payload, series_codes)

    def get_usd_pen(
        self, start: date | str, end: date | str, series: str = USD_SELL_SERIES
    ) -> pd.DataFrame:
        """Tipo de cambio diario S/ por US$ en el formato estándar del proyecto."""
        data = self.get_series([series], start, end)
        return pd.DataFrame(
            {
                "fecha": data["fecha"],
                "moneda": "USD",
                "tipo_cambio": data["valor"],
                "fuente": f"BCRP {series}",
            }
        )

    def close(self) -> None:
        self.client.close()


def load_rates_file(path: str | Path) -> pd.DataFrame:
    """Lee un CSV de tipo de cambio con columnas ``fecha, moneda, tipo_cambio[, fuente]``."""
    frame = pd.read_csv(path, dtype={"moneda": str})
    missing = {"fecha", "moneda", "tipo_cambio"} - set(frame.columns)
    if missing:
        raise ValueError(f"El archivo {path} no tiene las columnas {sorted(missing)}")
    frame["fecha"] = pd.to_datetime(frame["fecha"], errors="coerce")
    frame["moneda"] = frame["moneda"].str.upper().str.strip()
    frame["tipo_cambio"] = pd.to_numeric(frame["tipo_cambio"], errors="coerce")
    if "fuente" not in frame.columns:
        frame["fuente"] = Path(path).name
    return frame.dropna(subset=["fecha", "moneda", "tipo_cambio"])[
        ["fecha", "moneda", "tipo_cambio", "fuente"]
    ]


def update_rates_cache(new_rates: pd.DataFrame, cache_file: str | Path) -> pd.DataFrame:
    """Combina tipos de cambio nuevos con la caché local y la guarda."""
    cache_file = Path(cache_file)
    frames = [new_rates]
    if cache_file.is_file():
        frames.insert(0, load_rates_file(cache_file))
    combined = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["fecha", "moneda"], keep="last")
        .sort_values(["moneda", "fecha"])
        .reset_index(drop=True)
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    combined.assign(fecha=combined["fecha"].dt.strftime("%Y-%m-%d")).to_csv(cache_file, index=False)
    logger.info("Caché de tipo de cambio actualizada: %s (%d filas)", cache_file, len(combined))
    return combined
