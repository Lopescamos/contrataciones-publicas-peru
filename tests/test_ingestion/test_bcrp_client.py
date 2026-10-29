"""Pruebas del cliente del BCRP (tipo de cambio)."""

from datetime import date

import pandas as pd
import responses

from contrataciones.ingestion.bcrp_client import (
    BCRPClient,
    load_rates_file,
    parse_bcrp_payload,
    parse_bcrp_period,
    update_rates_cache,
)

BASE = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"


def test_parse_bcrp_period_variants():
    assert parse_bcrp_period("02.Ene.24") == date(2024, 1, 2)
    assert parse_bcrp_period("15.Set.25") == date(2025, 9, 15)
    assert parse_bcrp_period("15.Sep.2025") == date(2025, 9, 15)
    assert parse_bcrp_period("31.Dec.24") == date(2024, 12, 31)
    assert parse_bcrp_period("Ago.2024") == date(2024, 8, 1)
    assert parse_bcrp_period("texto") is None


def test_parse_payload_ignores_not_available_values():
    payload = {
        "periods": [
            {"name": "02.Ene.24", "values": ["3.7120"]},
            {"name": "03.Ene.24", "values": ["n.d."]},
        ]
    }
    frame = parse_bcrp_payload(payload, ["PD04638PD"])
    assert len(frame) == 1
    assert frame.iloc[0]["valor"] == 3.712


@responses.activate
def test_get_usd_pen_builds_expected_url():
    url = f"{BASE}/PD04638PD/json/2025-01-01/2025-01-10/esp"
    responses.get(url, json={"config": {}, "periods": [{"name": "06.Ene.25", "values": ["3.75"]}]})
    client = BCRPClient(BASE)
    rates = client.get_usd_pen(date(2025, 1, 1), date(2025, 1, 10))
    client.close()
    assert list(rates.columns) == ["fecha", "moneda", "tipo_cambio", "fuente"]
    assert rates.iloc[0]["moneda"] == "USD"
    assert rates.iloc[0]["tipo_cambio"] == 3.75


def test_update_rates_cache_merges_and_deduplicates(tmp_path):
    cache = tmp_path / "tc.csv"
    first = pd.DataFrame(
        {
            "fecha": pd.to_datetime(["2025-01-02", "2025-01-03"]),
            "moneda": "USD",
            "tipo_cambio": [3.70, 3.71],
            "fuente": "BCRP",
        }
    )
    second = pd.DataFrame(
        {
            "fecha": pd.to_datetime(["2025-01-03", "2025-01-06"]),
            "moneda": "USD",
            "tipo_cambio": [3.72, 3.73],
            "fuente": "BCRP",
        }
    )
    update_rates_cache(first, cache)
    combined = update_rates_cache(second, cache)
    assert len(combined) == 3
    reloaded = load_rates_file(cache)
    assert reloaded.loc[reloaded["fecha"] == "2025-01-03", "tipo_cambio"].item() == 3.72
