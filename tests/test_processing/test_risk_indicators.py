"""Pruebas de los indicadores de riesgo."""

import pandas as pd
import pytest

from contrataciones.processing import risk_indicators as risk
from tests.conftest import SUNAT_RUC


def procesos_frame(**overrides):
    base = {
        "ocid": ["p1", "p2", "p3", "p4", "p5"],
        "estado": ["complete", "complete", "cancelled", "complete", "complete"],
        "es_competitivo": [True, True, True, False, True],
        "es_contratacion_directa": [False, False, False, True, False],
        "metodo_detalle": [
            "Licitación Pública",
            "Adjudicación Simplificada",
            "Licitación Pública",
            "Contratación Directa",
            "Adjudicación Simplificada",
        ],
        "n_postores": pd.array([1, 3, 1, 1, pd.NA], dtype="Int64"),
        "plazo_presentacion_dias": pd.array([20, 8, 5, pd.NA, 16], dtype="Int64"),
        "ratio_adjudicado_referencial": [0.99, 1.05, 0.99, 1.0, 0.80],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_single_bidder_only_competitive(risk_rules):
    flags = risk.flag_single_bidder(procesos_frame(), risk_rules)
    assert sorted(flags["ocid"]) == ["p1", "p3"]  # p4 es directa; p5 sin dato


def test_short_submission_with_method_threshold(risk_rules):
    rules = dict(risk_rules)
    rules["indicators"] = {
        **risk_rules["indicators"],
        "RF02": {"threshold_days": 15, "threshold_by_method": {"Adjudicación Simplificada": 7}},
    }
    flags = risk.flag_short_submission(procesos_frame(), rules)
    assert sorted(flags["ocid"]) == ["p3"]  # p2: 8 días >= umbral de su método (7)
    default = risk.flag_short_submission(procesos_frame(), risk_rules)
    assert sorted(default["ocid"]) == ["p2", "p3"]


def test_short_submission_can_use_enquiry_period(risk_rules):
    frame = procesos_frame(plazo_consultas_dias=pd.array([3, 30, 2, pd.NA, pd.NA], dtype="Int64"))
    indicators = dict(risk_rules["indicators"])
    indicators["RF02"] = {**indicators["RF02"], "period": "consultas", "threshold_days": 5}
    rules = {**risk_rules, "indicators": indicators}
    flags = risk.flag_short_submission(frame, rules)
    assert sorted(flags["ocid"]) == ["p1", "p3"]
    assert flags["detalle"].str.startswith("Plazo de consultas").all()
    indicators["RF02"]["period"] = "otro"
    with pytest.raises(ValueError, match="RF02.period"):
        risk.flag_short_submission(frame, rules)


def test_price_near_and_above_reference(risk_rules):
    near = risk.flag_price_near_reference(procesos_frame(), risk_rules)
    above = risk.flag_award_above_reference(procesos_frame(), risk_rules)
    assert sorted(near["ocid"]) == ["p1", "p3"]  # p4 no es competitivo
    assert above["ocid"].tolist() == ["p2"]


def test_direct_contracting(risk_rules):
    assert risk.flag_direct_contracting(procesos_frame(), risk_rules)["ocid"].tolist() == ["p4"]


def test_eligible_processes_excludes_cancelled(risk_rules):
    assert "p3" not in set(risk.eligible_processes(procesos_frame(), risk_rules)["ocid"])


@pytest.fixture
def awards_and_sanctions():
    adjudicaciones = pd.DataFrame(
        {
            "ocid": ["p1", "p2", "p3", "p4"],
            "ruc": [SUNAT_RUC, SUNAT_RUC, SUNAT_RUC, "20100047218"],
            "ruc_valido": [True, True, True, True],
            "fecha_adjudicacion": pd.to_datetime(
                ["2024-12-31", "2025-03-01", "2026-01-01", "2025-03-01"]
            ),
            "es_valida": [True, True, True, True],
        }
    )
    sanciones = pd.DataFrame(
        {
            "ruc": [SUNAT_RUC, "20100047218"],
            "ruc_valido": [True, True],
            "tipo_sancion": ["INHABILITACIÓN TEMPORAL", "MULTA"],
            "fecha_inicio": pd.to_datetime(["2025-01-01", "2025-01-01"]),
            "fecha_fin": pd.to_datetime(["2025-06-30", None]),
        }
    )
    return adjudicaciones, sanciones


def test_sanctioned_award_mask_respects_period_and_type(awards_and_sanctions):
    adjudicaciones, sanciones = awards_and_sanctions
    mask = risk.sanctioned_award_mask(adjudicaciones, sanciones, ["INHABILIT"])
    assert mask.tolist() == [False, True, False, False]  # p4: multa, no inhabilitación
    any_type = risk.sanctioned_award_mask(adjudicaciones, sanciones, [])
    assert any_type.tolist() == [False, True, False, True]


def test_supplier_concentration_and_hhi(risk_rules):
    adjudicaciones = pd.DataFrame(
        {
            "ocid": [f"p{i}" for i in range(6)],
            "entidad_id": ["E1"] * 6,
            "anio": [2025] * 6,
            "proveedor_id": ["A", "A", "A", "A", "B", "C"],
            "monto_asignado_pen": [100.0, 100.0, 100.0, 100.0, 50.0, 50.0],
            "es_valida": [True] * 6,
        }
    )
    flags = risk.flag_supplier_concentration(adjudicaciones, risk_rules)
    assert sorted(flags["ocid"]) == ["p0", "p1", "p2", "p3"]
    hhi = risk.herfindahl_index(risk.supplier_shares(adjudicaciones))
    # participaciones: 0.8, 0.1, 0.1 -> 6400 + 100 + 100
    assert hhi["hhi"].iloc[0] == pytest.approx(6600.0)


def test_score_levels_and_cap(risk_rules):
    flags = pd.DataFrame(
        {
            "ocid": ["p1", "p1", "p1", "p1", "p2"],
            "codigo": ["RF01", "RF02", "RF06", "RF07", "RF05"],
            "detalle": [""] * 5,
        }
    )
    scores = risk.score_processes(pd.Series(["p1", "p2", "p3"]), flags, risk_rules).set_index(
        "ocid"
    )
    assert scores.loc["p1", "puntaje_riesgo"] == 85 and scores.loc["p1", "nivel_riesgo"] == "Alto"
    assert scores.loc["p2", "nivel_riesgo"] == "Bajo"
    assert scores.loc["p3", "nivel_riesgo"] == "Sin alertas"
    capped = risk.score_processes(
        pd.Series(["x"]),
        pd.DataFrame({"ocid": ["x"] * 7, "codigo": list(risk.CATALOG), "detalle": [""] * 7}),
        risk_rules,
    )
    assert capped["puntaje_riesgo"].item() == 100


def test_disabled_indicator_is_skipped(risk_rules):
    rules = {**risk_rules, "indicators": {**risk_rules["indicators"], "RF05": {"enabled": False}}}
    adjudicaciones = pd.DataFrame(
        columns=[
            "ocid",
            "ruc",
            "ruc_valido",
            "fecha_adjudicacion",
            "es_valida",
            "entidad_id",
            "anio",
            "proveedor_id",
            "monto_asignado_pen",
        ]
    )
    flags = risk.compute_flags(procesos_frame(), adjudicaciones, pd.DataFrame(), rules)
    assert "RF05" not in set(flags["codigo"])
    catalog = risk.indicator_catalog(rules)
    assert len(catalog) == 7 and not catalog.set_index("codigo").loc["RF05", "habilitado"]
