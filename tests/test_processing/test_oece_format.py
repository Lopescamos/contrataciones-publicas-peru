"""Particularidades de la publicación real del OECE (ver docs/04_fuentes_de_datos.md).

Los casos replican la forma de los records que devuelve la API del OECE:
entidades con código PE-CONSUCODE, RUC en ``additionalIdentifiers``, provincia
en ``address.region``, ``tenderPeriod`` con inicio = fin, estados vacíos y
consorcios con código interno.
"""

import pandas as pd

from contrataciones.processing.cleaner import (
    EMPTY_SANCIONES,
    clean_adjudicaciones,
    clean_contratos,
    clean_partes,
    clean_postores,
    clean_procesos,
    make_party_key,
)
from contrataciones.processing.ocds_flattener import flatten_release
from contrataciones.processing.transformer import build_gold
from contrataciones.processing.validator import run_quality_suite
from tests.conftest import CONSORTIUM_ID, SUNAT_RUC, make_oece_release, ruc_for

PERIOD_RULE = "plazo de presentación no informado (inicio = fin)"


def staging(releases):
    tables: dict[str, list] = {}
    for release in releases:
        for name, rows in flatten_release(release).items():
            tables.setdefault(name, []).extend(rows)
    return {name: pd.DataFrame(rows) for name, rows in tables.items()}


def silver(releases):
    tables = staging(releases)
    partes = clean_partes(tables["partes"])
    postores, _ = clean_postores(tables["postores"], partes)
    return {
        "procesos": clean_procesos(tables["procesos"]),
        "partes": partes,
        "postores": postores,
        "adjudicaciones": clean_adjudicaciones(tables["adjudicaciones"], partes),
        "contratos": clean_contratos(tables["contratos"]),
        "sanciones": EMPTY_SANCIONES.copy(),
    }


def rules_with_rf02(risk_rules, **changes):
    indicators = dict(risk_rules["indicators"])
    indicators["RF02"] = {**indicators["RF02"], **changes}
    return {**risk_rules, "indicators": indicators}


def test_flatten_reads_additional_ruc_department_and_publisher_pen():
    rows = flatten_release(make_oece_release(amount_pen=168_000.0))
    buyer = rows["partes"][0]
    assert buyer["party_id"] == "PE-CONSUCODE-1984"
    assert buyer["additional_ruc"] == SUNAT_RUC
    assert buyer["region"] == "HUANCAVELICA"  # department tiene prioridad sobre region
    proceso = rows["procesos"][0]
    assert proceso["tender_value_amount_pen"] == 168_000.0
    assert proceso["enquiry_period_start"].startswith("2024-04-18")
    # Sin tender.tenderers: los postores se toman de las partes con rol "tenderer".
    assert [p["tenderer_id"] for p in rows["postores"]] == [
        CONSORTIUM_ID,
        f"PE-RUC-{ruc_for(1002)}",
    ]


def test_zero_length_tender_period_is_not_a_zero_day_deadline():
    row = clean_procesos(staging([make_oece_release()])["procesos"]).iloc[0]
    assert pd.isna(row["plazo_presentacion_dias"])
    assert row["plazo_consultas_dias"] == 14
    assert pd.isna(row["estado"])


def test_party_keys_without_ruc_use_source_id_or_name():
    keys = make_party_key(
        pd.Series([SUNAT_RUC, None, None]),
        pd.Series([True, False, False]),
        pd.Series(["PE-CONSUCODE-1984", "pe-ruc-1509611", None]),
        pd.Series(["SUNAT", "CONSORCIO DEMO", "Proveedor   sin id"]),
    )
    assert keys.tolist() == [SUNAT_RUC, "PE-RUC-1509611", "NOM-PROVEEDOR SIN ID"]


def test_entities_and_consortium_suppliers_in_gold(risk_rules):
    with_address = make_oece_release("o-1")
    # El OECE no publica el departamento del proveedor; si una fuente lo hiciera, se usa.
    with_address["parties"][1]["address"] = {"department": "LIMA", "countryName": "PERU"}
    releases = [
        with_address,
        make_oece_release("o-2", entity_code="2407", entity_ruc=None, consortium=False),
    ]
    gold = build_gold(silver(releases), risk_rules)
    entidades = gold["dim_entidad"].set_index("entidad_id")
    assert entidades.loc[SUNAT_RUC, "ruc"] == SUNAT_RUC
    assert entidades.loc[SUNAT_RUC, "departamento"] == "Huancavelica"
    assert pd.isna(entidades.loc["PE-CONSUCODE-2407", "ruc"])
    proveedores = gold["dim_proveedor"].set_index("proveedor_id")
    assert proveedores.loc[CONSORTIUM_ID, "tipo_persona"] == "Consorcio"
    assert proveedores.loc[CONSORTIUM_ID, "departamento"] == "Lima"
    assert proveedores.loc[ruc_for(1001), "tipo_persona"] == "Persona jurídica"
    assert pd.isna(proveedores.loc[ruc_for(1001), "departamento"])
    assert gold["fact_adjudicacion"]["es_valida"].all()  # estado vacío = adjudicación válida
    assert set(gold["fact_contrato"]["estado"]) == {"sin_estado"}
    assert gold["fact_contrato"]["tiene_adjudicacion_vinculada"].all()


def test_award_date_is_compared_by_day():
    release = make_oece_release("o-1")
    release["tender"]["datePublished"] = "2024-04-24T21:16:00-05:00"  # mismo día, con hora
    report = run_quality_suite(silver([release]), {})
    rule = report.set_index("regla").loc["fecha_adjudicacion >= fecha_publicacion"]
    assert rule["filas_con_problema"] == 0 and rule["filas_evaluadas"] == 1


def test_quality_reports_unreported_submission_period():
    report = run_quality_suite(silver([make_oece_release("o-1"), make_oece_release("o-2")]), {})
    rule = report.set_index("regla").loc[PERIOD_RULE]
    assert rule["severidad"] == "INFO" and rule["estado"] == "OK"
    assert rule["filas_evaluadas"] == 2 and rule["filas_con_problema"] == 2


def test_rf02_can_evaluate_the_enquiry_period(risk_rules):
    default = build_gold(silver([make_oece_release("o-1")]), risk_rules)["fact_alerta"]
    assert "RF02" not in set(default["codigo"])  # plazo de presentación no informado
    rules = rules_with_rf02(risk_rules, period="consultas", threshold_days=20)
    alerts = build_gold(silver([make_oece_release("o-1")]), rules)["fact_alerta"]
    detail = alerts.loc[alerts["codigo"] == "RF02", "detalle"].item()
    assert detail == "Plazo de consultas de 14 días (umbral 20)"


def test_publisher_pen_amount_is_used_for_foreign_currency(tmp_project):
    from contrataciones.pipeline import Pipeline, PipelineOptions

    release = make_oece_release("o-usd", value=1_000.0, currency="USD", amount_pen=3_750.0)
    data = silver([release])
    pipeline = Pipeline(PipelineOptions(source="sample", exchange_rate_source="none"))
    pipeline._convert_currency(data, pipeline._exchange_rates(data))
    assert data["procesos"]["valor_referencial_pen"].item() == 3_750.0
    # La adjudicación no trae amount_PEN y no hay tipo de cambio: queda sin convertir.
    assert data["adjudicaciones"]["monto_pen"].isna().all()
