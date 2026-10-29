"""Pruebas del cliente HTTP genérico."""

import pytest
import responses

from contrataciones.ingestion.api_client import APIClient, APIError, default_next_link

BASE = "https://api.ejemplo.pe/v1"


def test_build_url():
    client = APIClient(BASE + "/")
    assert client.build_url("items") == f"{BASE}/items"
    assert client.build_url("/items") == f"{BASE}/items"
    assert client.build_url("https://otro.pe/x") == "https://otro.pe/x"
    assert client.build_url() == BASE


def test_default_next_link():
    assert default_next_link({"links": {"next": "https://x/2"}}) == "https://x/2"
    assert default_next_link({"next": "https://x/3"}) == "https://x/3"
    assert default_next_link({"links": {}}) is None
    assert default_next_link([1, 2]) is None


@responses.activate
def test_iter_pages_follows_next_links():
    responses.get(f"{BASE}/items", json={"data": [1], "links": {"next": f"{BASE}/items?page=2"}})
    responses.get(
        f"{BASE}/items?page=2", json={"data": [2], "links": {"next": f"{BASE}/items?page=3"}}
    )
    responses.get(f"{BASE}/items?page=3", json={"data": [3], "links": {}})
    with APIClient(BASE) as client:
        pages = list(client.iter_pages("items"))
    assert [number for number, _ in pages] == [1, 2, 3]
    assert [payload["data"][0] for _, payload in pages] == [1, 2, 3]


@responses.activate
def test_iter_pages_respects_max_pages():
    responses.get(f"{BASE}/items", json={"links": {"next": f"{BASE}/items?page=2"}})
    responses.get(f"{BASE}/items?page=2", json={"links": {"next": f"{BASE}/items?page=3"}})
    with APIClient(BASE) as client:
        assert len(list(client.iter_pages("items", max_pages=2))) == 2


@responses.activate
def test_iter_pages_stops_on_repeated_link():
    responses.get(f"{BASE}/items", json={"links": {"next": f"{BASE}/items"}})
    with APIClient(BASE) as client:
        assert len(list(client.iter_pages("items"))) == 1


@responses.activate
def test_http_error_raises_api_error():
    responses.get(f"{BASE}/x", status=404, body="no encontrado")
    with APIClient(BASE, max_retries=0) as client, pytest.raises(APIError) as error:
        client.get_json("x")
    assert error.value.status_code == 404


@responses.activate
def test_invalid_json_raises_api_error():
    responses.get(f"{BASE}/x", body="<html>bloqueado</html>", content_type="text/html")
    with APIClient(BASE) as client, pytest.raises(APIError, match="no es JSON"):
        client.get_json("x")


@responses.activate
def test_download_writes_file(tmp_path):
    responses.get("https://archivos.pe/2025.jsonl.gz", body=b"contenido-binario")
    with APIClient() as client:
        path = client.download("https://archivos.pe/2025.jsonl.gz", tmp_path / "f.gz")
    assert path.read_bytes() == b"contenido-binario"
    assert not (tmp_path / "f.gz.part").exists()
