"""Pruebas del registro de modelos (guardado, carga, catálogo y bitácora)."""

import json
from datetime import date, datetime

import numpy as np
import pytest

from contrataciones.models import registry


def test_new_version_format():
    assert registry.new_version("monto_esperado", datetime(2026, 10, 20, 9, 5, 7)) == (
        "monto_esperado_20261020_090507"
    )


def test_save_and_load_round_trip(tmp_path, trained):
    path = registry.save_model(trained.artifact, tmp_path)
    assert path == tmp_path / "trained" / f"{trained.artifact['version']}.joblib"
    loaded = registry.load_model(tmp_path)
    X = trained.X[trained.table["es_poblacion"]].head(20)
    assert np.allclose(loaded["estimator"].predict(X), trained.artifact["estimator"].predict(X))
    assert loaded["oof"].equals(trained.artifact["oof"])
    assert loaded["library_versions"]["scikit-learn"]


def test_load_latest_and_specific_versions(tmp_path, trained):
    older = {**trained.artifact, "version": "monto_esperado_20250101_000000"}
    registry.save_model(older, tmp_path)
    registry.save_model(trained.artifact, tmp_path)
    assert registry.available_versions(tmp_path, "monto_esperado") == [
        "monto_esperado_20250101_000000",
        trained.artifact["version"],
    ]
    assert registry.load_model(tmp_path)["version"] == trained.artifact["version"]
    assert registry.load_model(tmp_path, older["version"])["version"] == older["version"]
    with pytest.raises(FileNotFoundError, match="No existe el modelo"):
        registry.load_model(tmp_path, "monto_esperado_19990101_000000")


def test_load_without_models_explains_how_to_train(tmp_path):
    with pytest.raises(FileNotFoundError, match="contrataciones-ml train"):
        registry.load_model(tmp_path)


def test_catalog_append_and_list(tmp_path):
    entry = {"version": "monto_esperado_20260101_000000", "aceptado": np.bool_(True), "mae": np.nan}
    registry.append_to_catalog(tmp_path, entry)
    registry.append_to_catalog(tmp_path, {**entry, "version": "monto_esperado_20260102_000000"})
    catalog = registry.read_catalog(tmp_path)
    assert [e["version"] for e in catalog] == [
        "monto_esperado_20260101_000000",
        "monto_esperado_20260102_000000",
    ]
    assert catalog[0]["aceptado"] is True
    assert catalog[0]["mae"] is None  # NaN se guarda como nulo
    table = registry.list_models(tmp_path)
    assert not table["en_disco"].any()
    assert registry.list_models(tmp_path / "vacio").empty


def test_experiment_log_is_plain_json(tmp_path):
    payload = {"fecha": date(2026, 1, 1), "valores": [np.float64(1.5), float("inf")]}
    path = registry.write_experiment_log(tmp_path, "monto_esperado_x", payload)
    assert path.name == "experimento_monto_esperado_x.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "fecha": "2026-01-01",
        "valores": [1.5, None],
    }
