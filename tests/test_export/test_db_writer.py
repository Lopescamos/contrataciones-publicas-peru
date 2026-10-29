"""Pruebas de carga a base de datos (SQLite siempre; PostgreSQL si hay TEST_POSTGRES_URL)."""

import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from contrataciones.export.db_writer import (
    create_views,
    ensure_tables,
    load_tables,
    prepare_for_sql,
    upsert,
)
from contrataciones.ingestion.db_connector import DatabaseConnector

ROOT = Path(__file__).resolve().parents[2]
DDL = ROOT / "sql" / "ddl"
VIEWS = ROOT / "sql" / "views"


def minimal_gold() -> dict[str, pd.DataFrame]:
    dim_fecha = pd.DataFrame(
        {
            "fecha_key": [20250101],
            "fecha": pd.to_datetime(["2025-01-01"]),
            "anio": [2025],
            "semestre": [1],
            "trimestre": [1],
            "mes": [1],
            "nombre_mes": ["Enero"],
            "anio_mes": ["2025-01"],
            "semana_iso": [1],
            "dia": [1],
            "dia_semana": [3],
            "nombre_dia": ["Miércoles"],
            "es_fin_de_semana": [False],
        }
    )
    return {
        "dim_fecha": dim_fecha,
        "dim_entidad": pd.DataFrame(
            {
                "entidad_key": [1],
                "entidad_id": ["E1"],
                "ruc": [None],
                "nombre": ["ENTIDAD"],
                "departamento": ["Lima"],
                "pais": ["Perú"],
            }
        ),
        "dim_metodo": pd.DataFrame(
            {
                "metodo_key": [1],
                "metodo_detalle": ["Licitación Pública"],
                "metodo_ocds": ["open"],
                "es_competitivo": [True],
                "es_contratacion_directa": [False],
            }
        ),
        "fact_proceso": pd.DataFrame(
            {
                "proceso_key": [1],
                "ocid": ["ocds-x-1"],
                "nomenclatura": ["LP-1"],
                "descripcion": ["X"],
                "entidad_key": pd.array([1], dtype="Int64"),
                "metodo_key": pd.array([1], dtype="Int64"),
                "categoria_key": pd.array([pd.NA], dtype="Int64"),
                "fecha_convocatoria_key": pd.array([20250101], dtype="Int64"),
                "estado": ["complete"],
                "moneda": ["PEN"],
                "valor_referencial": [100.0],
                "valor_referencial_pen": [100.0],
                "n_postores": pd.array([1], dtype="Int64"),
                "plazo_presentacion_dias": pd.array([pd.NA], dtype="Int64"),
                "plazo_consultas_dias": pd.array([5], dtype="Int64"),
                "n_adjudicaciones": [1],
                "monto_adjudicado_pen": [99.0],
                "ratio_adjudicado_referencial": [0.99],
                "n_alertas": [2],
                "puntaje_riesgo": [40],
                "nivel_riesgo": ["Medio"],
                "nivel_riesgo_orden": [2],
                "columna_extra": ["se ignora"],
            }
        ),
    }


def connector_for(url: str) -> DatabaseConnector:
    return DatabaseConnector("t", config={"profiles": {"t": {"url": url, "use_copy": True}}})


@pytest.fixture(params=["sqlite", "postgresql"])
def db(request, tmp_path):
    if request.param == "sqlite":
        connector = connector_for(f"sqlite:///{tmp_path / 'test.db'}")
    else:
        url = os.environ.get("TEST_POSTGRES_URL")
        if not url:
            pytest.skip("Defina TEST_POSTGRES_URL para probar contra PostgreSQL")
        connector = connector_for(url)
    ensure_tables(connector, DDL, drop=True)
    yield connector
    connector.dispose()


def test_prepare_for_sql_converts_dates_and_nullables():
    frame = pd.DataFrame(
        {
            "solo_fecha": pd.to_datetime(["2025-01-01", None]),
            "con_hora": pd.to_datetime(["2025-01-01 10:30", None]),
            "entero": pd.array([1, pd.NA], dtype="Int64"),
        }
    )
    prepared = prepare_for_sql(frame)
    assert prepared["solo_fecha"].tolist() == [date(2025, 1, 1), None]
    assert prepared["con_hora"].iloc[0].hour == 10
    assert prepared["entero"].tolist() == [1, None]


def test_load_tables_full_refresh_is_idempotent(db):
    gold = minimal_gold()
    first = load_tables(db, gold)
    second = load_tables(db, gold)
    assert first == second == {"dim_fecha": 1, "dim_entidad": 1, "dim_metodo": 1, "fact_proceso": 1}
    frame = db.read_query("SELECT ocid, n_postores FROM fact_proceso")
    assert frame.to_dict("records") == [{"ocid": "ocds-x-1", "n_postores": 1}]


def test_views_are_created_and_queryable(db):
    load_tables(db, minimal_gold())
    created = create_views(db, VIEWS)
    assert "vw_procesos" in created
    view = db.read_query("SELECT entidad, procedimiento, anio FROM vw_procesos")
    assert view.iloc[0].to_dict() == {
        "entidad": "ENTIDAD",
        "procedimiento": "Licitación Pública",
        "anio": 2025,
    }


def test_load_requires_existing_tables(tmp_path):
    connector = connector_for(f"sqlite:///{tmp_path / 'vacia.db'}")
    with pytest.raises(RuntimeError, match="setup-db"):
        load_tables(connector, minimal_gold())


def test_upsert_inserts_and_updates(db):
    load_tables(db, minimal_gold())
    changes = pd.DataFrame(
        {
            "entidad_key": [1, 2],
            "entidad_id": ["E1", "E2"],
            "ruc": [None, None],
            "nombre": ["ENTIDAD RENOMBRADA", "OTRA"],
            "departamento": ["Lima", "Ica"],
            "pais": ["Perú", "Perú"],
        }
    )
    assert upsert(db, changes, "dim_entidad", ["entidad_key"]) == 2
    names = db.read_query("SELECT nombre FROM dim_entidad ORDER BY entidad_key")["nombre"].tolist()
    assert names == ["ENTIDAD RENOMBRADA", "OTRA"]
