"""Prueba de punta a punta del pipeline y de la CLI (sobre datos sintéticos)."""

import json
import re
from pathlib import Path

import pandas as pd
import pytest
import responses

from contrataciones.cli import main
from contrataciones.ingestion.db_connector import DatabaseConnector
from contrataciones.pipeline import Pipeline, PipelineError, PipelineOptions
from contrataciones.utils.config_loader import load_config

QUERY_PARAMS = {
    "02_top_entidades_por_monto.sql": {"anio": 2025, "limite": 5},
    "03_top_proveedores_por_monto.sql": {"anio": 2025, "limite": 5},
    "06_concentracion_hhi_por_entidad.sql": {"anio": 2025},
    "07_procesos_riesgo_alto.sql": {"limite": 10},
}


@pytest.fixture
def result(tmp_project):
    options = PipelineOptions(source="sample", limit=400)
    return Pipeline(options).run()


def test_pipeline_produces_all_layers(result, tmp_project):
    assert result.status in {"ok", "ok_con_advertencias"}
    assert result.staging_counts["procesos"] == 400
    assert result.gold_counts["fact_proceso"] == 400
    curated = tmp_project / "data" / "curated"
    for table in ("dim_entidad", "fact_proceso", "fact_alerta", "agg_entidad_anio"):
        assert (curated / f"{table}.parquet").is_file()
        assert (tmp_project / "data" / "exports" / "powerbi" / f"{table}.csv").is_file()
    assert (tmp_project / "data" / "processed" / "reporte_calidad.csv").is_file()
    assert (tmp_project / "data" / "exports" / "reporte_contrataciones.xlsx").is_file()
    manifest = json.loads((curated / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == result.run_id
    assert result.quality["fallas_error"] == 0


def test_pipeline_loads_database_and_queries_run(result, tmp_project):
    assert result.db_counts["fact_proceso"] == 400
    with DatabaseConnector("local_sqlite", config=load_config("db_config")) as db:
        assert db.read_query("SELECT COUNT(*) AS n FROM vw_procesos")["n"].item() == 400
        for sql_file in sorted((tmp_project / "sql" / "queries").glob("*.sql")):
            frame = db.read_sql_file(sql_file, params=QUERY_PARAMS.get(sql_file.name))
            assert isinstance(frame, pd.DataFrame), sql_file.name


def test_pipeline_flags_are_consistent(result, tmp_project):
    curated = tmp_project / "data" / "curated"
    procesos = pd.read_parquet(curated / "fact_proceso.parquet")
    alertas = pd.read_parquet(curated / "fact_alerta.parquet")
    per_process = alertas.groupby("ocid")["codigo"].nunique()
    merged = procesos.set_index("ocid")["n_alertas"]
    assert (merged.reindex(per_process.index) == per_process).all()
    assert set(procesos["nivel_riesgo"]) <= {"Sin alertas", "Bajo", "Medio", "Alto"}
    assert procesos["puntaje_riesgo"].between(0, 100).all()


def test_bulk_without_files_fails_cleanly(tmp_project):
    with pytest.raises(PipelineError, match="contrataciones download"):
        Pipeline(PipelineOptions(source="bulk")).run()


def test_cli_run_and_query(tmp_project, capsys):
    assert main(["run", "--source", "sample", "--limit", "150", "--no-excel"]) == 0
    output = capsys.readouterr().out
    assert "estado: ok" in output
    query = tmp_project / "sql" / "queries" / "08_alertas_por_indicador.sql"
    export = tmp_project / "resultado.xlsx"
    assert main(["query", str(query), "--output", str(export)]) == 0
    assert Path(export).is_file()


def test_cli_rejects_unknown_source(tmp_project):
    with pytest.raises(SystemExit):
        main(["run", "--source", "ftp"])


def _fake_api(monkeypatch, calls, truncated=()):
    """Reemplaza la lectura de la API por releases controlados (sin red)."""
    from contrataciones.ingestion import ocds_source
    from tests.conftest import award, make_release

    tender_stage = make_release("ocds-api-001")
    award_stage = {
        "ocid": "ocds-api-001",
        "date": "2025-05-01T10:00:00-05:00",
        "awards": [award("w1", 90_000.0, [("20999010017", "PROVEEDOR DEMO 001")])],
    }

    def fake_iter_releases(self, max_pages=None, raw_dir=None, segments=None):
        calls.append({"max_pages": max_pages, "segments": segments})
        self.truncated = list(truncated)
        raw = Path(raw_dir)
        raw.mkdir(parents=True, exist_ok=True)
        (raw / "2025-03_page_00001.json").write_text("{}", encoding="utf-8")
        yield from [tender_stage, award_stage, make_release("ocds-api-002")]

    monkeypatch.setattr(ocds_source.OCDSApiSource, "iter_releases", fake_iter_releases)


def test_pipeline_api_source_compiles_and_saves_raw(tmp_project, monkeypatch):
    """La rama API compila releases por ocid y guarda la capa bronze (API simulada)."""
    calls: list[dict] = []
    _fake_api(monkeypatch, calls)
    options = PipelineOptions(source="api", load_database=False, export_excel=False)
    result = Pipeline(options).run()
    assert not any("límite de páginas" in w for w in result.warnings)
    assert result.gold_counts["fact_proceso"] == 2
    assert result.gold_counts["fact_adjudicacion"] == 1
    assert Path(result.outputs["raw_api"], "2025-03_page_00001.json").is_file()
    assert calls == [{"max_pages": None, "segments": None}]  # por defecto: últimos meses


def test_pipeline_api_segments_from_dates_and_truncation_warning(tmp_project, monkeypatch):
    from datetime import date

    calls: list[dict] = []
    _fake_api(monkeypatch, calls, truncated=["2025-03"])
    options = PipelineOptions(
        source="api",
        date_from=date(2025, 3, 1),
        date_to=date(2025, 4, 30),
        api_max_pages=3,
        load_database=False,
        export_excel=False,
    )
    result = Pipeline(options).run()
    assert calls == [{"max_pages": 3, "segments": ["2025-03", "2025-04"]}]
    assert result.status == "ok_con_advertencias"
    assert any("límite de páginas" in w for w in result.warnings)

    explicit = PipelineOptions(
        source="api", api_segments=["2025-03"], load_database=False, export_excel=False
    )
    Pipeline(explicit).run()
    assert calls[-1]["segments"] == ["2025-03"]


@responses.activate
def test_cli_check_api_with_mocked_services(tmp_project, capsys):
    from tests.conftest import make_release

    base = "https://contratacionesabiertas.oece.gob.pe/api/v1"
    responses.get(f"{base}/files", json={"results": [{"month": "01"}]})
    responses.get(
        f"{base}/records",
        json={"records": [{"compiledRelease": make_release("ocds-api-777")}], "links": {}},
    )
    responses.get(
        re.compile(r"https://estadisticas\.bcrp\.gob\.pe/.*"),
        json={"periods": [{"name": "06.Ene.25", "values": ["3.75"]}]},
    )
    assert main(["check-api", "--month", "2025-01"]) == 0
    output = capsys.readouterr().out
    assert "Paquetes mensuales de 2025 (endpoint files): 01" in output
    assert "2025-01, página 1: 1 procesos" in output
    assert "ocds-api-777" in output
    assert "último tipo de cambio: 3.7500" in output
