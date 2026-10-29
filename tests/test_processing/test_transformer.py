"""Pruebas del modelo dimensional (capa gold)."""

import pandas as pd
import pytest

from contrataciones.processing.cleaner import (
    EMPTY_SANCIONES,
    clean_adjudicaciones,
    clean_contratos,
    clean_partes,
    clean_postores,
    clean_procesos,
)
from contrataciones.processing.ocds_flattener import flatten_release
from contrataciones.processing.transformer import build_dim_fecha, build_gold, date_key
from tests.conftest import award, make_release, ruc_for


def silver_from(releases):
    tables = {}
    for release in releases:
        for name, rows in flatten_release(release).items():
            tables.setdefault(name, []).extend(rows)
    staging = {name: pd.DataFrame(rows) for name, rows in tables.items()}
    partes = clean_partes(staging["partes"])
    postores, _ = clean_postores(staging["postores"], partes)
    return {
        "procesos": clean_procesos(staging["procesos"]),
        "partes": partes,
        "postores": postores,
        "adjudicaciones": clean_adjudicaciones(staging["adjudicaciones"], partes),
        "contratos": clean_contratos(
            staging.get(
                "contratos",
                pd.DataFrame(
                    columns=[
                        "ocid",
                        "contract_id",
                        "award_id",
                        "contract_status",
                        "date_signed",
                        "contract_value_amount",
                        "contract_value_currency",
                        "period_start",
                        "period_end",
                    ]
                ),
            )
        ),
        "sanciones": EMPTY_SANCIONES.copy(),
    }


@pytest.fixture
def gold(risk_rules):
    a, b = (ruc_for(1001), "PROVEEDOR A"), (ruc_for(1002), "PROVEEDOR B")
    releases = [
        make_release("p-001", tenderers=[a], awards=[award("w1", 99_000, [a])]),
        make_release(
            "p-002",
            tenderers=[a, b],
            awards=[award("w2", 80_000, [b])],
            contracts=[
                {
                    "id": "c2",
                    "awardID": "w2",
                    "dateSigned": "2025-04-20T10:00:00-05:00",
                    "value": {"amount": 80_000},
                }
            ],
        ),
        make_release(
            "p-003",
            buyer_ruc=ruc_for(2),
            buyer_name="HOSPITAL DEMO 02",
            region="CUSCO",
            method="direct",
            details="Contratación Directa",
            tenderers=[b],
            awards=[award("w3", 120_000, [b])],
        ),
        make_release("p-004", status="cancelled", tenderers=[a, b]),
    ]
    return build_gold(silver_from(releases), risk_rules)


def test_date_key_and_calendar():
    assert date_key(pd.Series(pd.to_datetime(["2025-03-07", None]))).tolist()[0] == 20250307
    calendar = build_dim_fecha([pd.Series(pd.to_datetime(["2024-05-01", "2025-02-01"]))])
    assert len(calendar) == 366 + 365  # 2024 es bisiesto
    assert calendar["fecha_key"].is_unique
    assert calendar.iloc[0]["nombre_dia"] == "Lunes"  # 1 de enero de 2024


def test_gold_tables_and_keys(gold):
    expected = {
        "dim_fecha",
        "dim_entidad",
        "dim_proveedor",
        "dim_metodo",
        "dim_categoria",
        "dim_indicador",
        "fact_proceso",
        "fact_adjudicacion",
        "fact_contrato",
        "fact_postor",
        "fact_sancion",
        "fact_alerta",
        "agg_entidad_anio",
    }
    assert set(gold) == expected
    for name, frame in gold.items():
        key = f"{name.split('_', 1)[1]}_key" if name.startswith(("dim_", "fact_")) else None
        if key and key in frame.columns:
            assert frame[key].is_unique, f"llave duplicada en {name}"


def test_foreign_keys_exist_in_dimensions(gold):
    fp, fa = gold["fact_proceso"], gold["fact_adjudicacion"]
    assert set(fp["entidad_key"].dropna()) <= set(gold["dim_entidad"]["entidad_key"])
    assert set(fp["metodo_key"].dropna()) <= set(gold["dim_metodo"]["metodo_key"])
    assert set(fp["fecha_convocatoria_key"].dropna()) <= set(gold["dim_fecha"]["fecha_key"])
    assert set(fa["proveedor_key"].dropna()) <= set(gold["dim_proveedor"]["proveedor_key"])
    assert set(fa["proceso_key"]) <= set(fp["proceso_key"])
    assert set(gold["fact_alerta"]["proceso_key"]) <= set(fp["proceso_key"])


def test_business_rules_in_gold(gold):
    fp = gold["fact_proceso"].set_index("ocid")
    assert fp.loc["p-001", "ratio_adjudicado_referencial"] == pytest.approx(0.99)
    assert fp.loc["p-001", "n_postores"] == 1
    alerts = gold["fact_alerta"]
    codes = set(alerts.loc[alerts["ocid"] == "p-001", "codigo"])
    assert {"RF01", "RF03"} <= codes  # postor único y precio cercano
    assert "RF05" in set(alerts.loc[alerts["ocid"] == "p-003", "codigo"])
    assert "p-004" not in set(alerts["ocid"])  # cancelado: excluido
    assert fp.loc["p-001", "n_alertas"] == alerts[alerts["ocid"] == "p-001"]["codigo"].nunique()
    winners = gold["fact_postor"].groupby("ocid")["es_ganador"].sum()
    assert winners["p-002"] == 1 and winners["p-004"] == 0
    assert set(gold["dim_entidad"]["departamento"]) == {"Lima", "Cusco"}
    contract = gold["fact_contrato"].iloc[0]
    assert bool(contract["tiene_adjudicacion_vinculada"]) is True


def test_entity_year_aggregate(gold):
    agg = gold["agg_entidad_anio"]
    assert agg["n_procesos"].sum() == 4
    assert agg["hhi"].between(0, 10_000).all()
