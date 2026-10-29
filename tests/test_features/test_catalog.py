"""Pruebas del catálogo de features y de la guardia contra la fuga de datos."""

import pytest

from contrataciones.features.catalog import (
    FORBIDDEN_COLUMNS,
    FORBIDDEN_TABLES,
    FeatureSpec,
    LeakageError,
    check_source,
    load_feature_specs,
    names_by_kind,
    parse_feature,
    specs_from_dicts,
)
from contrataciones.utils.config_loader import ConfigError


def feature(source="fact_proceso.valor_referencial_pen", available_at="convocatoria", **extra):
    return {"source": source, "available_at": available_at, "kind": "numeric", **extra}


def test_project_config_features_are_valid(model_config):
    specs = load_feature_specs(model_config["features"])
    assert [s.name for s in specs] == [
        "log_valor_referencial",
        "metodo",
        "es_competitivo",
        "categoria",
        "entidad",
        "tipo_entidad",
        "departamento",
        "mes_convocatoria",
        "plazo_consultas_dias",
    ]
    assert all(s.available_at == "convocatoria" for s in specs)
    every = load_feature_specs(model_config["features"], include_disabled=True)
    disabled = [s.name for s in every if not s.enabled]
    assert disabled == ["plazo_presentacion_dias"]


@pytest.mark.parametrize(
    "source",
    [
        "fact_proceso.n_postores",
        "fact_proceso.monto_adjudicado_pen",
        "fact_proceso.ratio_adjudicado_referencial",
        "fact_proceso.puntaje_riesgo",
        "fact_proceso.estado",
        "fact_proceso.ocid",
    ],
)
def test_forbidden_columns_raise_even_if_declared_as_known_at_tender(source):
    with pytest.raises(LeakageError, match=FORBIDDEN_COLUMNS[source].split(" (")[0]):
        parse_feature("pista", feature(source))


@pytest.mark.parametrize("table", sorted(FORBIDDEN_TABLES))
def test_forbidden_tables_raise(table):
    with pytest.raises(LeakageError, match=table):
        parse_feature("pista", feature(f"{table}.cualquier_columna"))


def test_name_fragments_catch_future_result_columns():
    with pytest.raises(LeakageError, match="adjudic"):
        check_source("fact_proceso.fecha_adjudicacion_key", "convocatoria")
    with pytest.raises(LeakageError, match="postor"):
        check_source("dim_entidad.n_postores_historicos", "convocatoria")
    # "contratación directa" es un método, no un contrato: no debe confundirse.
    assert check_source("dim_metodo.es_contratacion_directa", "convocatoria") == (
        "dim_metodo",
        "es_contratacion_directa",
    )


def test_unknown_tables_and_late_availability_raise():
    with pytest.raises(LeakageError, match="no está entre las permitidas"):
        parse_feature("x", feature("pred_monto_esperado.monto_esperado_pen"))
    with pytest.raises(LeakageError, match="se conoce en 'adjudicacion'"):
        parse_feature("x", feature(available_at="adjudicacion"))


def test_disabled_features_are_validated_too():
    leaky = {"pista": {**feature("fact_proceso.n_postores"), "enabled": False}}
    with pytest.raises(LeakageError):
        load_feature_specs({"valor": feature(), **leaky})


@pytest.mark.parametrize(
    ("name", "config", "message"),
    [
        ("Valor", feature(), "snake_case"),
        ("valor", {"source": "fact_proceso.x"}, "le falta"),
        ("valor", feature("valor_referencial_pen"), "tabla.columna"),
        ("valor", {**feature(), "kind": "texto"}, "kind"),
        ("valor", {**feature(), "transform": "sqrt"}, "transform"),
    ],
)
def test_malformed_declarations_raise_config_error(name, config, message):
    with pytest.raises(ConfigError, match=message):
        parse_feature(name, config)


def test_empty_or_all_disabled_config_raises():
    with pytest.raises(ConfigError, match="no declara"):
        load_feature_specs({})
    with pytest.raises(ConfigError, match="deshabilitadas"):
        load_feature_specs({"valor": {**feature(), "enabled": False}})


def test_leakage_error_is_a_config_error():
    assert issubclass(LeakageError, ConfigError)


def test_specs_from_saved_models_are_revalidated():
    good = parse_feature("valor", feature()).to_dict()
    assert specs_from_dicts([good])[0].source == "fact_proceso.valor_referencial_pen"
    tampered = {**good, "column": "n_postores"}
    with pytest.raises(LeakageError):
        specs_from_dicts([tampered])


def test_names_by_kind_groups_features():
    specs = [
        FeatureSpec("a", "fact_proceso", "x", "numeric"),
        FeatureSpec("b", "dim_metodo", "y", "categorical"),
        FeatureSpec("c", "dim_entidad", "z", "high_cardinality"),
    ]
    groups = names_by_kind(specs)
    assert groups == {
        "numeric": ["a"],
        "categorical": ["b"],
        "binary": [],
        "high_cardinality": ["c"],
    }
