"""Pruebas de limpieza genérica y de dominio."""

import numpy as np
import pandas as pd
import pytest

from contrataciones.processing.cleaner import (
    clean_adjudicaciones,
    clean_contratos,
    clean_name,
    clean_partes,
    clean_postores,
    clean_procesos,
    clean_sanciones,
    extract_ruc,
    fix_dtypes,
    flag_outliers_iqr,
    handle_nulls,
    is_valid_ruc,
    normalize_departamento,
    parse_date_flexible,
    parse_datetime,
    remove_duplicates,
    ruc_person_type,
)
from contrataciones.processing.ocds_flattener import flatten_release
from tests.conftest import SUNAT_RUC, award, make_release, ruc_for


def staging(releases):
    tables = {}
    for release in releases:
        for name, rows in flatten_release(release).items():
            tables.setdefault(name, []).extend(rows)
    return {name: pd.DataFrame(rows) for name, rows in tables.items()}


# --------------------------------------------------------------------------- RUC
@pytest.mark.parametrize(
    "ruc,expected",
    [
        (SUNAT_RUC, True),
        ("20100047218", True),
        ("20131312954", False),  # dígito verificador incorrecto
        ("30131312955", False),  # prefijo inválido
        ("2013131295", False),  # 10 dígitos
        (None, False),
    ],
)
def test_is_valid_ruc(ruc, expected):
    assert is_valid_ruc(ruc) is expected


def test_extract_ruc_from_ocds_identifiers():
    series = pd.Series([f"PE-RUC-{SUNAT_RUC}", SUNAT_RUC, "sin ruc", None, "123"])
    assert extract_ruc(series).tolist()[:2] == [SUNAT_RUC, SUNAT_RUC]
    assert extract_ruc(series).isna().tolist()[2:] == [True, True, True]


def test_ruc_person_type():
    types = ruc_person_type(pd.Series(["10456789012", SUNAT_RUC, "15123456789", None]))
    assert types.tolist()[:3] == ["Persona natural", "Persona jurídica", "Otro"]


# ----------------------------------------------------------------------- textos
def test_clean_name_and_departamento():
    names = clean_name(pd.Series(['  "Empresa   Uno s.a.c." ', "  ", None]))
    assert names.iloc[0] == "EMPRESA UNO S.A.C."
    assert names.iloc[1:].isna().all()
    deps = normalize_departamento(
        pd.Series(["LIMA METROPOLITANA", "cuzco", "ANCASH", "Prov. Const. del Callao", None])
    )
    assert deps.tolist()[:4] == ["Lima", "Cusco", "Áncash", "Callao"]
    assert deps.tolist()[4] is None


# ----------------------------------------------------------------------- fechas
def test_parse_datetime_converts_to_lima_time():
    parsed = parse_datetime(
        pd.Series(["2024-08-03T23:30:00Z", "2024-08-03T18:00:00-05:00", "2024-08-03", None])
    )
    assert parsed.iloc[0] == pd.Timestamp("2024-08-03 18:30")
    assert parsed.iloc[1] == pd.Timestamp("2024-08-03 18:00")
    assert parsed.iloc[2] == pd.Timestamp("2024-08-03 00:00")  # sin zona: se asume hora local
    assert pd.isna(parsed.iloc[3])


def test_parse_date_flexible_formats():
    parsed = parse_date_flexible(pd.Series(["15/03/2025", "2025-03-16", "45736", "", None]))
    assert parsed.iloc[0] == pd.Timestamp("2025-03-15")
    assert parsed.iloc[1] == pd.Timestamp("2025-03-16")
    assert parsed.iloc[2] == pd.Timestamp("2025-03-20")  # número de serie de Excel
    assert parsed.iloc[3:].isna().all()


# -------------------------------------------------------------------- genéricas
def test_remove_duplicates_reports_count():
    frame = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    cleaned, removed = remove_duplicates(frame)
    assert removed == 1 and len(cleaned) == 2


def test_handle_nulls_strategies():
    frame = pd.DataFrame({"x": [1.0, np.nan, 3.0], "y": ["a", None, "a"]})
    assert handle_nulls(frame, "fill_mean", ["x"])["x"].tolist() == [1.0, 2.0, 3.0]
    assert handle_nulls(frame, "fill_mode", ["y"])["y"].tolist() == ["a", "a", "a"]
    assert len(handle_nulls(frame, "drop")) == 2
    with pytest.raises(ValueError):
        handle_nulls(frame, "magia")


def test_fix_dtypes_and_outliers():
    frame = fix_dtypes(
        pd.DataFrame({"n": ["1", "2", None], "m": ["10.5", "x", "3"]}), {"n": "int", "m": "float"}
    )
    assert str(frame["n"].dtype) == "Int64"
    assert frame["m"].isna().tolist() == [False, True, False]
    flags = flag_outliers_iqr(pd.Series([10, 11, 12, 10, 11, 1000]))
    assert flags.tolist() == [False, False, False, False, False, True]


# ------------------------------------------------------------------ dominio
def test_clean_procesos_flags_and_derived_fields():
    releases = [
        make_release("p-1", start="2025-03-01T09:00:00-05:00", end="2025-03-11T18:00:00-05:00"),
        make_release("p-2", method="direct", details="Contratación Directa", value=0),
        make_release("p-3", method="selective", details="Comparación de Precios", category="works"),
    ]
    procesos = clean_procesos(staging(releases)["procesos"]).set_index("ocid")
    assert procesos.loc["p-1", "plazo_presentacion_dias"] == 10
    assert bool(procesos.loc["p-1", "es_competitivo"]) is True
    assert bool(procesos.loc["p-2", "es_contratacion_directa"]) is True
    assert bool(procesos.loc["p-2", "es_competitivo"]) is False
    assert pd.isna(procesos.loc["p-2", "valor_referencial"])  # 0 se trata como desconocido
    assert procesos.loc["p-3", "categoria"] == "Obras"
    assert procesos.loc["p-1", "anio"] == 2025


def test_clean_procesos_keeps_latest_release_per_ocid():
    old = make_release("p-9")
    new = make_release("p-9", value=555.0)
    new["date"] = "2025-12-01T00:00:00-05:00"
    procesos = clean_procesos(staging([new, old])["procesos"])
    assert len(procesos) == 1 and procesos.iloc[0]["valor_referencial"] == 555.0


def test_clean_postores_removes_duplicates_and_resolves_ruc():
    duplicated = [(ruc_for(1001), "A"), (ruc_for(1001), "A"), (ruc_for(1002), "B")]
    tables = staging([make_release("p-1", tenderers=duplicated)])
    partes = clean_partes(tables["partes"])
    postores, removed = clean_postores(tables["postores"], partes)
    assert removed == 1
    assert postores["proveedor_id"].tolist() == [ruc_for(1001), ruc_for(1002)]
    assert postores["ruc_valido"].all()


def test_clean_adjudicaciones_prorates_consortium_amount():
    release = make_release(
        "p-1",
        awards=[
            award("a1", 100.0, [(ruc_for(1001), "A"), (ruc_for(1002), "B")]),
            award("a2", 50.0, [(ruc_for(1003), "C")], status="cancelled"),
        ],
    )
    tables = staging([release])
    adjudicaciones = clean_adjudicaciones(tables["adjudicaciones"], clean_partes(tables["partes"]))
    first = adjudicaciones[adjudicaciones["award_id"] == "a1"]
    assert first["monto_asignado"].tolist() == [50.0, 50.0]
    assert adjudicaciones.loc[adjudicaciones["award_id"] == "a2", "es_valida"].item() is False


def test_clean_contratos_marks_missing_status():
    release = make_release(
        "p-1",
        contracts=[
            {
                "id": "c1",
                "awardID": "a1",
                "period": {
                    "startDate": "2025-01-01T00:00:00-05:00",
                    "endDate": "2025-03-02T00:00:00-05:00",
                },
            },
        ],
    )
    contratos = clean_contratos(staging([release])["contratos"])
    assert contratos.iloc[0]["estado"] == "sin_estado"
    assert contratos.iloc[0]["duracion_dias"] == 60


def test_clean_sanciones_definitive_and_invalid_ruc():
    mapped = pd.DataFrame(
        {
            "ruc": [SUNAT_RUC, "20131312954"],
            "nombre": ["X", "Y"],
            "tipo_sancion": ["Inhabilitación definitiva", "Inhabilitación temporal"],
            "fecha_inicio": ["01/01/2024", "01/02/2024"],
            "fecha_fin": [None, "01/08/2024"],
            "resolucion": ["R1", "R2"],
            "motivo": ["m", "n"],
        }
    )
    sanciones = clean_sanciones(mapped)
    assert sanciones["es_definitiva"].tolist() == [True, False]
    assert sanciones["ruc_valido"].tolist() == [True, False]
    assert sanciones["proveedor_id"].isna().tolist() == [False, True]
