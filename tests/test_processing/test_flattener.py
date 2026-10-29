"""Pruebas del aplanado OCDS a tablas de staging."""

from contrataciones.processing.ocds_flattener import (
    STAGING_TABLES,
    flatten_release,
    read_staging,
    stage_releases,
)
from tests.conftest import SUNAT_RUC, award, make_release, ruc_for


def test_flatten_release_produces_one_row_per_entity():
    release = make_release(
        "ocds-t-001",
        tenderers=[(ruc_for(1001), "A"), (ruc_for(1002), "B")],
        awards=[award("aw1", 90_000, [(ruc_for(1001), "A"), (SUNAT_RUC, "SOCIO")])],
        contracts=[
            {
                "id": "c1",
                "awardID": "aw1",
                "status": "active",
                "dateSigned": "2025-04-10T10:00:00-05:00",
                "value": {"amount": 90_000},
            }
        ],
    )
    rows = flatten_release(release)
    assert set(rows) == set(STAGING_TABLES)
    proceso = rows["procesos"][0]
    assert proceso["ocid"] == "ocds-t-001"
    assert proceso["tender_value_amount"] == 100_000.0
    assert proceso["procurement_method_details"] == "Licitación Pública"
    assert proceso["n_awards"] == 1 and proceso["n_contracts"] == 1
    assert len(rows["partes"]) == 3
    assert rows["partes"][0]["roles"] == "buyer|procuringEntity"
    assert rows["partes"][0]["region"] == "LIMA"
    assert len(rows["postores"]) == 2
    assert len(rows["adjudicaciones"]) == 2  # un registro por proveedor
    assert {r["n_suppliers"] for r in rows["adjudicaciones"]} == {2}
    assert rows["contratos"][0]["award_id"] == "aw1"


def test_flatten_release_tolerates_missing_sections():
    rows = flatten_release({"ocid": "ocds-t-002"})
    assert rows["procesos"][0]["ocid"] == "ocds-t-002"
    assert rows["procesos"][0]["tender_value_amount"] is None
    assert rows["partes"] == [] and rows["adjudicaciones"] == []


def test_award_without_suppliers_keeps_one_row():
    release = make_release("ocds-t-003", awards=[{"id": "a", "status": "active"}])
    rows = flatten_release(release)
    assert len(rows["adjudicaciones"]) == 1
    assert rows["adjudicaciones"][0]["supplier_id"] is None
    assert rows["adjudicaciones"][0]["n_suppliers"] == 0


def test_numeric_values_as_text_are_parsed():
    release = make_release("ocds-t-004")
    release["tender"]["value"]["amount"] = "1,234.50"
    assert flatten_release(release)["procesos"][0]["tender_value_amount"] == 1234.5


def test_stage_releases_in_chunks_and_read_back(tmp_path):
    releases = [make_release(f"ocds-t-{i:03d}") for i in range(7)]
    counts = stage_releases(releases, tmp_path / "staging", chunk_size=3)
    assert counts["procesos"] == 7
    assert len(list((tmp_path / "staging" / "procesos").glob("*.parquet"))) == 3
    procesos = read_staging(tmp_path / "staging", "procesos")
    assert sorted(procesos["ocid"]) == [f"ocds-t-{i:03d}" for i in range(7)]
    # Las tablas sin filas también se pueden leer (archivo vacío con esquema).
    contratos = read_staging(tmp_path / "staging", "contratos")
    assert contratos.empty and "contract_id" in contratos.columns


def test_stage_releases_overwrites_previous_run(tmp_path):
    stage_releases([make_release("a-1"), make_release("a-2")], tmp_path / "s", chunk_size=10)
    stage_releases([make_release("b-1")], tmp_path / "s", chunk_size=10)
    assert read_staging(tmp_path / "s", "procesos")["ocid"].tolist() == ["b-1"]
