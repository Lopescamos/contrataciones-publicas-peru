"""Pruebas del dataset de modelado (una fila por proceso desde la capa gold)."""

import json

import numpy as np
import pandas as pd
import pytest

from contrataciones.features import dataset as ds
from tests.conftest import make_gold_tables


@pytest.fixture
def gold():
    return make_gold_tables(n=300, seed=3)


def test_one_row_per_process_with_target_and_population(gold, model_config):
    table = ds.build_modeling_table(gold, model_config["population"])
    procesos = gold["fact_proceso"]
    assert len(table) == len(procesos)
    assert table["ocid"].is_unique
    population = table[table["es_poblacion"]]
    expected = np.log(population["monto_adjudicado_pen"] / population["valor_referencial_pen"])
    assert np.allclose(population[ds.TARGET], expected, atol=1e-5)
    assert table.loc[~table["es_poblacion"], ds.TARGET].isna().all()


def test_exclusion_reasons(gold, model_config):
    table = ds.build_modeling_table(gold, model_config["population"])
    reasons = table["motivo_exclusion"].value_counts().to_dict()
    assert reasons == {
        ds.MOTIVO_SIN_ADJUDICACION: 40,
        ds.MOTIVO_SIN_REFERENCIAL: 30,
        ds.MOTIVO_RAZON_FUERA_DE_RANGO: 5,
    }
    errors = table[table["motivo_exclusion"].eq(ds.MOTIVO_RAZON_FUERA_DE_RANGO)]
    # Los errores de datos se evalúan (población) pero no entrenan.
    assert errors["es_poblacion"].all()
    assert not errors["es_entrenable"].any()


def test_excluded_methods_match_without_accents_or_case(gold, model_config):
    population = {**model_config["population"], "exclude_methods": ["subasta inversa electronica"]}
    table = ds.build_modeling_table(gold, population)
    excluded = table["motivo_exclusion"].eq(ds.MOTIVO_METODO_EXCLUIDO)
    assert excluded.any()
    assert set(table.loc[excluded, "dim_metodo.metodo_detalle"]) == {"Subasta Inversa Electrónica"}
    assert not table.loc[excluded, "es_poblacion"].any()


def test_award_date_ignores_invalid_awards(gold, model_config):
    table = ds.build_modeling_table(gold, model_config["population"])
    adjudicaciones = gold["fact_adjudicacion"]
    ocid = adjudicaciones.loc[~adjudicaciones["es_valida"], "ocid"].iloc[0]
    valid_key = adjudicaciones.loc[
        adjudicaciones["es_valida"] & adjudicaciones["ocid"].eq(ocid), "fecha_adjudicacion_key"
    ].iloc[0]
    row = table.set_index("ocid").loc[ocid]
    assert row["fecha_adjudicacion"] == pd.to_datetime(str(valid_key), format="%Y%m%d")


def test_forbidden_columns_are_never_copied(gold, model_config):
    table = ds.build_modeling_table(gold, model_config["population"])
    sources = [c for c in table.columns if "." in c]
    for column in (
        "fact_proceso.n_postores",
        "fact_proceso.monto_adjudicado_pen",
        "fact_proceso.puntaje_riesgo",
        "fact_proceso.ocid",
    ):
        assert column not in sources
    assert {"dim_metodo.metodo_detalle", "dim_entidad.nombre", "dim_categoria.categoria"} <= set(
        sources
    )
    assert not any(c.startswith("fact_adjudicacion.") for c in sources)


def test_equal_amount_flag_marks_exact_awards(gold, model_config):
    table = ds.build_modeling_table(gold, model_config["population"])
    equal = table[table["es_adjudicado_igual_referencial"]]
    assert not equal.empty
    assert (equal["dim_metodo.metodo_detalle"] == "Convenio").all()


def test_population_summary(gold, model_config):
    summary = ds.population_summary(ds.build_modeling_table(gold, model_config["population"]))
    assert summary["procesos"] == 300
    assert summary["poblacion"] == 300 - 70
    assert summary["entrenables"] == 300 - 75
    assert summary["motivos_exclusion"][ds.MOTIVO_RAZON_FUERA_DE_RANGO] == 5


def test_date_from_key_handles_missing_and_invalid():
    keys = pd.Series(pd.array([20250315, pd.NA, 20251399], dtype="Int64"))
    dates = ds.date_from_key(keys)
    assert dates.iloc[0] == pd.Timestamp("2025-03-15")
    assert dates.iloc[1:].isna().all()


def test_load_gold_and_manifest(tmp_path, gold):
    with pytest.raises(FileNotFoundError, match="contrataciones run"):
        ds.load_gold(tmp_path)
    for name, frame in gold.items():
        frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
    loaded = ds.load_gold(tmp_path)
    assert set(loaded) == set(ds.GOLD_TABLES)
    assert ds.read_manifest(tmp_path) == {}
    (tmp_path / "_manifest.json").write_text(json.dumps({"run_id": "x"}), encoding="utf-8")
    assert ds.read_manifest(tmp_path)["run_id"] == "x"
