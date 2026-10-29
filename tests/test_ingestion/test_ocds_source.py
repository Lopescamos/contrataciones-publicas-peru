"""Pruebas de lectura de datos OCDS."""

import gzip
import json
from datetime import date

import pytest
import responses
from responses import matchers

from contrataciones.ingestion.ocds_source import (
    OCDSApiSource,
    bulk_download_url,
    compile_releases,
    extract_releases,
    filter_releases,
    iter_json_records,
    iter_releases_from_files,
    month_segments,
    recent_segments,
    release_reference_date,
    validate_segment,
)
from tests.conftest import award, make_release

BASE = "https://contratacionesabiertas.oece.gob.pe/api/v1"
API_CONFIG = {
    "base_url": BASE,
    "endpoint": "records",
    "params": {"sourceId": "seace_v3"},
    "segment_param": "dataSegmentationID",
    "months_back": 2,
    "files_endpoint": "files",
    "min_interval_seconds": 0,
    "retries": {"total": 0},
}


def records_page(*ocids, next_url=None):
    return {
        "records": [{"ocid": o, "compiledRelease": make_release(o)} for o in ocids],
        "links": {"next": next_url, "prev": None},
    }


def segment_query(segment, **extra):
    return [
        matchers.query_param_matcher(
            {"sourceId": "seace_v3", "dataSegmentationID": segment, **extra}
        )
    ]


def test_extract_releases_from_all_shapes():
    release = make_release("ocds-test-001")
    assert extract_releases(release) == [release]
    assert extract_releases({"releases": [release]}) == [release]
    assert extract_releases({"records": [{"compiledRelease": release}]}) == [release]
    assert extract_releases({"records": [{"releases": [release]}]}) == [release]
    assert extract_releases([{"releases": [release]}, release]) == [release, release]
    assert extract_releases({"otra": 1}) == []
    # Los "linked releases" de un record (solo url y fecha) no traen datos.
    linked = {"records": [{"ocid": "x", "releases": [{"url": "https://x", "date": "2025"}]}]}
    assert extract_releases(linked) == []


def test_compile_releases_merges_by_id():
    tender_stage = {
        "ocid": "x-1",
        "date": "2025-01-01",
        "tender": {"title": "A", "status": "active"},
        "parties": [{"id": "p1", "name": "Entidad"}],
    }
    award_stage = {
        "ocid": "x-1",
        "date": "2025-02-01",
        "tender": {"status": "complete"},
        "awards": [{"id": "a1", "status": "pending"}],
        "parties": [{"id": "p2", "name": "Proveedor"}],
    }
    update = {"ocid": "x-1", "date": "2025-03-01", "awards": [{"id": "a1", "status": "active"}]}
    other = {"ocid": "x-2", "date": "2025-01-01", "tender": {"title": "B"}}
    compiled = {r["ocid"]: r for r in compile_releases([award_stage, tender_stage, update, other])}
    merged = compiled["x-1"]
    assert merged["tender"] == {"title": "A", "status": "complete"}
    assert merged["awards"] == [{"id": "a1", "status": "active"}]
    assert [p["id"] for p in merged["parties"]] == ["p1", "p2"]
    assert compiled["x-2"]["tender"]["title"] == "B"


def test_iter_json_records_reads_gzip_jsonl_and_skips_invalid(tmp_path):
    path = tmp_path / "2025.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(make_release("ocds-test-001")) + "\n")
        handle.write("{esto no es json}\n\n")
        handle.write(json.dumps(make_release("ocds-test-002")) + "\n")
    releases = list(iter_releases_from_files([path]))
    assert [r["ocid"] for r in releases] == ["ocds-test-001", "ocds-test-002"]


def test_iter_json_records_reads_plain_json_package(tmp_path):
    path = tmp_path / "pagina.json"
    path.write_text(json.dumps({"releases": [make_release("ocds-test-003")]}), encoding="utf-8")
    records = list(iter_json_records(path))
    assert len(records) == 1
    assert extract_releases(records[0])[0]["ocid"] == "ocds-test-003"


def test_release_reference_date_priority():
    release = make_release("ocds-test-004", start="2025-03-01T09:00:00-05:00")
    assert release_reference_date(release) == date(2025, 3, 1)
    release["tender"].pop("tenderPeriod")
    release["tender"]["datePublished"] = "2025-02-15T08:00:00-05:00"
    assert release_reference_date(release) == date(2025, 2, 15)


def test_filter_releases_by_date_and_limit():
    releases = [
        make_release("a-1", start="2024-12-31T09:00:00-05:00", end="2025-01-20T09:00:00-05:00"),
        make_release("a-2", start="2025-01-10T09:00:00-05:00", end="2025-01-30T09:00:00-05:00"),
        make_release("a-3", start="2025-06-10T09:00:00-05:00", end="2025-06-30T09:00:00-05:00"),
        make_release("a-4", start="2025-07-10T09:00:00-05:00", end="2025-07-30T09:00:00-05:00"),
    ]
    selected = filter_releases(releases, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
    assert [r["ocid"] for r in selected] == ["a-2", "a-3", "a-4"]
    limited = filter_releases(releases, limit=2)
    assert [r["ocid"] for r in limited] == ["a-1", "a-2"]


def test_bulk_download_url():
    template = "https://data.open-contracting.org/es/publication/135/download?name={name}"
    assert bulk_download_url(2025, template).endswith("name=2025.jsonl.gz")
    assert bulk_download_url("full.jsonl.gz", template).endswith("name=full.jsonl.gz")


def test_month_segments_and_validation():
    assert month_segments(date(2024, 11, 5), date(2025, 2, 1)) == [
        "2024-11",
        "2024-12",
        "2025-01",
        "2025-02",
    ]
    assert month_segments(date(2025, 3, 9), date(2025, 1, 1)) == ["2025-01", "2025-02", "2025-03"]
    assert recent_segments(2, today=date(2026, 1, 15)) == ["2025-12", "2026-01"]
    assert recent_segments(0, today=date(2026, 5, 1)) == ["2026-05"]
    assert validate_segment(" 2025-09 ") == "2025-09"
    with pytest.raises(ValueError, match="AAAA-MM"):
        validate_segment("2025-13")


@responses.activate
def test_api_source_reads_monthly_segments_and_saves_raw(tmp_path):
    next_url = f"{BASE}/records?dataSegmentationID=2025-01&sourceId=seace_v3&page=2"
    responses.get(
        f"{BASE}/records",
        match=segment_query("2025-01"),
        json=records_page("ocds-test-010", next_url=next_url),
    )
    responses.get(
        f"{BASE}/records",
        match=segment_query("2025-01", page="2"),
        json=records_page("ocds-test-011"),
    )
    responses.get(
        f"{BASE}/records", match=segment_query("2025-02"), status=404, json={"detail": "No"}
    )
    source = OCDSApiSource(API_CONFIG)
    releases = list(source.iter_releases(raw_dir=tmp_path / "raw", segments=["2025-01", "2025-02"]))
    source.close()
    assert [r["ocid"] for r in releases] == ["ocds-test-010", "ocds-test-011"]
    assert sorted(p.name for p in (tmp_path / "raw").iterdir()) == [
        "2025-01_page_00001.json",
        "2025-01_page_00002.json",
    ]
    assert source.truncated == []


@responses.activate
def test_api_source_reports_truncated_segments():
    next_url = f"{BASE}/records?dataSegmentationID=2025-03&sourceId=seace_v3&page=2"
    responses.get(f"{BASE}/records", json=records_page("ocds-test-012", next_url=next_url))
    source = OCDSApiSource({**API_CONFIG, "max_pages": 1})
    releases = list(source.iter_releases(segments=["2025-03"]))
    source.close()
    assert len(releases) == 1
    assert source.truncated == ["2025-03"]


@responses.activate
def test_api_source_without_segments_keeps_plain_pagination(tmp_path):
    page_1 = records_page("ocds-test-013", next_url=f"{BASE}/recordsAfter?page=2")
    responses.get(f"{BASE}/recordsAfter?page=2", json=records_page("ocds-test-014"))
    responses.get(f"{BASE}/recordsAfter", json=page_1)
    config = {**API_CONFIG, "endpoint": "recordsAfter", "segment_param": None}
    source = OCDSApiSource(config)
    assert source.default_segments() == []
    releases = list(source.iter_releases(raw_dir=tmp_path / "raw"))
    source.close()
    assert [r["ocid"] for r in releases] == ["ocds-test-013", "ocds-test-014"]
    assert sorted(p.name for p in (tmp_path / "raw").iterdir()) == [
        "consulta_page_00001.json",
        "consulta_page_00002.json",
    ]


@responses.activate
def test_available_months_and_default_segments():
    responses.get(
        f"{BASE}/files",
        match=[matchers.query_param_matcher({"year": "2025", "source": "seace_v3"})],
        json={"results": [{"month": "02"}, {"month": "01"}, {"month": "x"}]},
    )
    source = OCDSApiSource(API_CONFIG)
    assert source.available_months(2025) == ["2025-01", "2025-02"]
    assert source.default_segments(today=date(2026, 1, 15)) == ["2025-12", "2026-01"]
    source.close()


def test_make_release_helper_award_shape():
    release = make_release("ocds-test-020", awards=[award("a1", 10.0, [("20131312955", "X")])])
    assert release["awards"][0]["suppliers"][0]["id"] == "PE-RUC-20131312955"
