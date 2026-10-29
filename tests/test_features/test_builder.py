"""Pruebas de las transformaciones sin estado de las features."""

import numpy as np
import pandas as pd
import pytest

from contrataciones.features.builder import (
    MISSING_CATEGORY,
    build_features,
    entity_type,
    month_from_key,
)
from contrataciones.features.catalog import FeatureSpec, load_feature_specs
from contrataciones.features.dataset import build_modeling_table
from tests.conftest import make_gold_tables


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("GOBIERNO REGIONAL DE LAMBAYEQUE - HOSPITAL REGIONAL DOCENTE", "Salud"),
        ("EMPRESA MUNICIPAL DE AGUA POTABLE DE ICA S.A.", "Empresa pública"),
        ("CORPORACION FINANCIERA DE DESARROLLO S.A.", "Empresa pública"),
        ("MUNICIPALIDAD PROVINCIAL DE MARAÑÓN", "Gobierno local"),
        ("GOBIERNO REGIONAL DE PIURA - PROYECTO ESPECIAL CHIRA PIURA", "Gobierno regional"),
        ("UNIVERSIDAD NACIONAL DE INGENIERÍA", "Educación"),
        ("REGISTRO NACIONAL DE IDENTIFICACION Y ESTADO CIVIL", "Gobierno nacional"),
        ("CREACION DEL SERVICIO DE CATASTRO", "Otra"),
        # "S A" se busca como palabras completas: no debe coincidir dentro de "SERVICIOS AGUA".
        ("SERVICIOS AGUA DEMO", "Otra"),
    ],
)
def test_entity_type_rules_of_the_project(model_config, name, expected):
    rules = model_config["entity_types"]
    result = entity_type(pd.Series([name]), rules["rules"], rules["default"])
    assert result.iloc[0] == expected


def test_entity_type_missing_names_use_default():
    rules = [{"label": "Salud", "keywords": ["HOSPITAL"]}]
    result = entity_type(pd.Series([None, "HOSPITAL X"]), rules, "Otra")
    assert result.tolist() == ["Otra", "Salud"]


def test_month_from_key():
    keys = pd.Series(pd.array([20250315, pd.NA, 20251399], dtype="Int64"))
    months = month_from_key(keys)
    assert months.iloc[0] == "03"
    assert months.iloc[1:].isna().all()


def test_build_features_types_and_order(model_config):
    gold = make_gold_tables(n=200, seed=5)
    specs = load_feature_specs(model_config["features"])
    table = build_modeling_table(gold, model_config["population"])
    X = build_features(table, specs, model_config["entity_types"])
    assert list(X.columns) == [s.name for s in specs]
    assert X.index.equals(table.index)
    assert X["log_valor_referencial"].dtype == "float64"
    reference = table["valor_referencial_pen"]
    assert np.allclose(X["log_valor_referencial"].dropna(), np.log1p(reference.dropna()))
    assert set(X["es_competitivo"].dropna()) <= {0.0, 1.0}
    assert X["mes_convocatoria"].str.fullmatch(r"\d{2}").all()
    assert X["plazo_consultas_dias"].isna().any()  # los nulos quedan para el modelo


def test_missing_categories_become_their_own_category():
    table = pd.DataFrame({"dim_entidad.departamento": ["Lima", None, " "]})
    spec = FeatureSpec("departamento", "dim_entidad", "departamento", "categorical")
    X = build_features(table, [spec])
    assert X["departamento"].tolist() == ["Lima", MISSING_CATEGORY, MISSING_CATEGORY]


def test_unknown_source_column_raises():
    spec = FeatureSpec("x", "fact_proceso", "no_existe", "numeric")
    with pytest.raises(KeyError, match="no existe en la capa gold"):
        build_features(pd.DataFrame({"a": [1]}), [spec])
