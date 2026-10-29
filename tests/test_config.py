"""Pruebas de la carga de configuración."""

from pathlib import Path

import pytest

from contrataciones.utils.config_loader import (
    ConfigError,
    get_project_root,
    interpolate_env,
    load_config,
    load_yaml,
    resolve_path,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_interpolate_uses_default_when_variable_missing(monkeypatch):
    monkeypatch.delenv("PG_PORT_TEST", raising=False)
    assert interpolate_env("${PG_PORT_TEST:-5432}") == 5432


def test_interpolate_uses_environment_value(monkeypatch):
    monkeypatch.setenv("MI_HOST", "db.ejemplo.pe")
    assert interpolate_env({"host": "${MI_HOST:-localhost}"}) == {"host": "db.ejemplo.pe"}


def test_interpolate_empty_value_becomes_none(monkeypatch):
    monkeypatch.setenv("VACIA", "")
    assert interpolate_env("${VACIA:-}") is None


def test_interpolate_coerces_types(monkeypatch):
    monkeypatch.setenv("FLAG", "true")
    monkeypatch.setenv("RATIO", "0.98")
    assert interpolate_env(["${FLAG}", "${RATIO}"]) == [True, 0.98]


def test_interpolate_embedded_placeholder_keeps_text(monkeypatch):
    monkeypatch.setenv("USUARIO", "kevin")
    assert interpolate_env("postgresql://${USUARIO}@host/db") == "postgresql://kevin@host/db"


def test_load_yaml_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_yaml(tmp_path / "no_existe.yaml")


def test_project_root_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTRATACIONES_HOME", str(tmp_path))
    assert get_project_root() == tmp_path.resolve()
    assert resolve_path("data/x.csv") == tmp_path.resolve() / "data" / "x.csv"
    # Ruta absoluta propia del sistema operativo: en Windows "/abs" es relativa a la
    # unidad actual, no absoluta, por lo que se construye desde el ancla real.
    absoluta = Path(tmp_path.anchor) / "abs" / "ruta.csv"
    assert resolve_path(absoluta) == absoluta


def test_ml_paths_and_model_config_sections():
    settings = load_config("settings", root=REPO_ROOT)
    assert {"features", "predictions", "models"} <= settings["paths"].keys()
    model_config = load_config("model_config", root=REPO_ROOT)
    expected = ["population", "features", "entity_types", "split", "models", "anomalies", "output"]
    assert set(expected) <= model_config.keys()
