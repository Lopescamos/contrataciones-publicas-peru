"""Pruebas de la auditoría de disponibilidad de los datos (Fase 0)."""

import json

import pandas as pd
import pytest
import responses

from contrataciones.features import audit
from contrataciones.features.dataset import build_modeling_table
from contrataciones.ingestion.api_client import APIClient
from tests.conftest import make_gold_tables

BASE = "https://api.prueba.pe/api/v1/release"


def record(ocid, *, protected, value, awards, releases):
    tender = {
        "procurementMethodDetails": "Licitación Pública Abreviada",
        "mainProcurementCategory": "works",
        "hasTenderInformationProtectedByLaw": protected,
        "value": {"amount": value},
        "tenderers": [{"id": f"t{i}"} for i in range(3)] if awards else [],
    }
    compiled = {"ocid": ocid, "tender": tender}
    if awards:
        compiled["awards"] = [{"value": {"amount": amount}} for amount in awards]
    return {"ocid": ocid, "compiledRelease": compiled, "releases": releases}


def version(ocid, day, tags):
    return {"date": f"2026-10-{day:02d}T10:00:00-05:00", "tag": tags, "url": f"{BASE}/{ocid}-{day}"}


def release_payload(value, n_tenderers=0):
    return {
        "releases": [
            {
                "tender": {
                    "value": {"amount": value},
                    "tenderers": [{"id": f"t{i}"} for i in range(n_tenderers)],
                }
            }
        ]
    }


@pytest.fixture
def records():
    tender, awarded = ["planning", "tender"], ["planning", "tender", "award"]
    return [
        # Valor en 0 antes de la buena pro; se revela igual al adjudicado.
        record(
            "rev",
            protected=False,
            value=2_705_753.38,
            awards=[2_705_753.38],
            releases=[version("rev", 15, tender), version("rev", 17, awarded)],
        ),
        # Valor publicado desde antes de la buena pro.
        record(
            "est",
            protected=False,
            value=163_425.02,
            awards=[120_781.0],
            releases=[version("est", 9, tender), version("est", 10, awarded)],
        ),
        # La historia de la API empieza ya adjudicada.
        record(
            "sin",
            protected=False,
            value=97_075.65,
            awards=[97_075.65],
            releases=[version("sin", 16, awarded)],
        ),
        # En selección: información protegida y sin adjudicación.
        record("sel", protected=True, value=0.0, awards=[], releases=[version("sel", 9, tender)]),
    ]


def test_raw_record_flags(records):
    flags = audit.raw_record_flags(records).set_index("ocid")
    assert flags.loc["sel", "informacion_protegida"]
    assert not flags.loc["rev", "informacion_protegida"]
    assert not flags.loc["sel", "tiene_valor_referencial"]
    assert flags["tiene_adjudicacion"].sum() == 3
    assert flags["adjudicado_igual_referencial"].sum() == 2
    assert flags.loc["est", "n_postores"] == 3


def test_iter_raw_records_reads_api_pages(tmp_path, records):
    run = tmp_path / "20261020_000000_abc"
    run.mkdir()
    (run / "2026-09_page_00001.json").write_text(
        json.dumps({"records": records, "links": {}}), encoding="utf-8"
    )
    (run / "roto.json").write_text("{no es json", encoding="utf-8")
    assert [r["ocid"] for r in audit.iter_raw_records(tmp_path)] == ["rev", "est", "sin", "sel"]


@responses.activate
def test_release_history_check_diagnoses_each_case(records):
    responses.get(f"{BASE}/rev-15", json=release_payload(0.0))
    responses.get(f"{BASE}/est-9", json=release_payload(163_425.02))
    client = APIClient(max_retries=0)
    result = audit.release_history_check(records, client).set_index("ocid")
    assert result.loc["rev", "diagnostico"] == audit.DIAGNOSIS_REVEALED
    assert result.loc["rev", "final_igual_adjudicado"]
    assert result.loc["est", "diagnostico"] == audit.DIAGNOSIS_STABLE
    assert result.loc["sin", "diagnostico"] == audit.DIAGNOSIS_NO_HISTORY
    assert "sel" not in result.index  # solo procesos adjudicados
    assert result.loc["est", "postores_previos"] == 0
    assert len(responses.calls) == 2  # "sin" no necesita consultar la API


@responses.activate
def test_release_history_check_reports_api_errors_and_respects_limit(records):
    responses.get(f"{BASE}/rev-15", status=500)
    client = APIClient(max_retries=0)
    result = audit.release_history_check(records, client, limit=1).set_index("ocid")
    assert result.loc["rev", "diagnostico"] == audit.DIAGNOSIS_ERROR
    assert "est" not in result.index  # se alcanzó el límite de consultas
    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (0.0, 100.0, audit.DIAGNOSIS_REVEALED),
        (None, 100.0, audit.DIAGNOSIS_REVEALED),
        (100.0, 100.0, audit.DIAGNOSIS_STABLE),
        (100.0, 120.0, audit.DIAGNOSIS_CHANGED),
    ],
)
def test_diagnose(before, after, expected):
    assert audit.diagnose(before, after) == expected


def test_client_from_config_uses_project_settings():
    client = audit.client_from_config(
        {"headers": {"User-Agent": "prueba"}, "timeout_seconds": 5, "min_interval_seconds": 0.2}
    )
    assert client.timeout == 5
    assert client.min_interval == 0.2
    assert client.session.headers["User-Agent"] == "prueba"


def test_gold_audits(model_config):
    gold = make_gold_tables(n=300, seed=11)
    table = build_modeling_table(gold, model_config["population"])
    equality = audit.equality_by_segment(table)
    is_convenio = equality["metodo_detalle"] == "Convenio"
    # Los convenios se adjudican al referencial (salvo los errores de datos plantados).
    assert (equality.loc[is_convenio, "pct_igual_referencial"] > 0.9).all()
    assert (equality.loc[~is_convenio, "n_igual_referencial"] == 0).all()
    bidders = audit.bidders_by_outcome(gold["fact_proceso"])
    assert bidders.loc["All", "All"] == 300
    missing = audit.missing_shares(gold["fact_proceso"]).set_index("columna")
    assert missing.loc["plazo_presentacion_dias", "pct_vacios"] == 1.0
    assert missing.loc["valor_referencial_pen", "pct_vacios"] == pytest.approx(30 / 300)
    assert isinstance(missing, pd.DataFrame)
