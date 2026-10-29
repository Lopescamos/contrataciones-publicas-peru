"""Pruebas del entrenamiento: división temporal, línea base, canario de fuga y calibración."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor

from contrataciones.features.catalog import FeatureSpec
from contrataciones.models import trainer
from contrataciones.utils.config_loader import ConfigError
from tests.conftest import make_gold_tables, model_inputs


# -----------------------------------------------------------------------------
# División temporal
# -----------------------------------------------------------------------------
def test_split_dates_from_latest_award(trained):
    dates = trainer.split_dates(trained.table, trained.config["split"])
    latest = trained.table.loc[trained.table["es_entrenable"], "fecha_adjudicacion"].max()
    assert dates.referencia == latest.date()
    assert dates.corte_madurez.day == 1
    assert (
        dates.inicio_prueba == (pd.Timestamp(dates.corte_madurez) - pd.DateOffset(months=3)).date()
    )
    assert (
        dates.inicio_validacion
        == (pd.Timestamp(dates.inicio_prueba) - pd.DateOffset(months=3)).date()
    )


def test_reference_date_can_be_fixed(trained):
    split = {**trained.config["split"], "reference_date": "2025-06-20"}
    dates = trainer.split_dates(trained.table, split)
    assert dates.to_dict() == {
        "referencia": "2025-06-20",
        "inicio_validacion": "2024-09-01",
        "inicio_prueba": "2024-12-01",
        "corte_madurez": "2025-03-01",
    }


def test_partitions_respect_availability_and_maturity(trained):
    table, partitions, dates = trained.table, trained.result.partitions, trained.result.dates
    validation_start = pd.Timestamp(dates.inicio_validacion)
    train = partitions.eq(trainer.PARTITION_TRAIN)
    # Nada del entrenamiento se convocó ni se adjudicó después del inicio de la validación.
    assert (table.loc[train, "fecha_convocatoria"] < validation_start).all()
    assert (table.loc[train, "fecha_adjudicacion"] < validation_start).all()
    unavailable = partitions.eq(trainer.PARTITION_UNAVAILABLE)
    assert unavailable.any()  # convocados antes, adjudicados después del corte
    assert (table.loc[unavailable, "fecha_adjudicacion"] >= validation_start).all()
    immature = partitions.eq(trainer.PARTITION_IMMATURE)
    assert (table.loc[immature, "fecha_convocatoria"] >= pd.Timestamp(dates.corte_madurez)).all()
    assert (partitions[~table["es_entrenable"]] == trainer.PARTITION_OUT).all()


def test_small_partitions_raise(model_config):
    gold = make_gold_tables(n=200, days=120)
    table, X, specs = model_inputs(gold, model_config)
    with pytest.raises(ConfigError, match="La partición"):
        trainer.train_model(table, X, specs, model_config)


def test_split_parameters_are_validated(trained):
    with pytest.raises(ConfigError, match="test_months"):
        trainer.split_dates(trained.table, {"test_months": 0})


def test_time_blocks():
    dates = pd.Series(pd.to_datetime(["2025-01-15", "2025-08-01", None]))
    assert trainer.time_blocks(dates).tolist()[:2] == ["2025T1", "2025T3"]
    assert pd.isna(trainer.time_blocks(dates).iloc[2])
    assert trainer.time_blocks(dates, "month").tolist()[:2] == ["2025-01", "2025-08"]
    with pytest.raises(ConfigError):
        trainer.time_blocks(dates, "week")


# -----------------------------------------------------------------------------
# Estimadores
# -----------------------------------------------------------------------------
def test_median_ratio_baseline_uses_global_median_for_small_groups():
    X = pd.DataFrame({"metodo": ["A"] * 30 + ["B"] * 3, "categoria": "Bienes"})
    y = np.r_[np.full(30, -0.2), np.full(3, 0.5)]
    baseline = trainer.MedianRatioBaseline(min_group_size=20).fit(X, y)
    predictions = baseline.predict(pd.DataFrame({"metodo": ["A", "B", "Z"], "categoria": "Bienes"}))
    assert predictions[0] == pytest.approx(-0.2)
    assert predictions[1] == pytest.approx(np.median(y))  # grupo B con 3 casos
    assert predictions[2] == pytest.approx(np.median(y))  # grupo nuevo


def test_baseline_requires_enabled_features(model_config, trained):
    models = {**model_config["models"], "baseline": {"group_by": ["no_existe"]}}
    with pytest.raises(ConfigError, match="group_by"):
        trainer.make_estimator(trainer.BASELINE, trained.specs, models)


def test_unknown_model_raises(trained, model_config):
    with pytest.raises(ConfigError, match="Modelo desconocido"):
        trainer.make_estimator("xgboost", trained.specs, model_config["models"])


def test_target_encoder_gives_unseen_entities_the_global_mean(trained, model_config):
    model = trainer.make_estimator("ridge", trained.specs, model_config["models"])
    train = trained.result.partitions.eq(trainer.PARTITION_TRAIN)
    y = trained.table["log_ratio_adjudicado"]
    model.fit(trained.X[train], y[train])
    encoder = model.named_steps["preprocesamiento"].named_transformers_["alta_cardinalidad"]
    target_encoder = encoder.steps[0][1]
    unseen = pd.DataFrame({"entidad": ["ENTIDAD QUE NO EXISTE"]})
    assert target_encoder.transform(unseen)[0, 0] == pytest.approx(target_encoder.target_mean_)


class SpyRegressor(DummyRegressor):
    """Registra con qué filas se entrenó cada modelo."""

    fitted: list[set] = []

    def fit(self, X, y, sample_weight=None):
        SpyRegressor.fitted.append(set(X.index))
        return super().fit(X, y, sample_weight)


def test_out_of_fold_never_predicts_a_row_with_a_model_that_saw_it():
    index = pd.RangeIndex(12)
    X = pd.DataFrame({"x": np.arange(12.0)}, index=index)
    y = pd.Series(np.arange(12.0), index=index)
    blocks = pd.Series(["2025T1"] * 4 + ["2025T2"] * 4 + ["2025T3"] * 4, index=index)
    trainable = pd.Series(True, index=index)
    scored = pd.Series(True, index=index)
    SpyRegressor.fitted = []
    predictions = trainer.out_of_fold_predictions(
        lambda: SpyRegressor(strategy="mean"), X, y, trainable, scored, blocks
    )
    assert len(SpyRegressor.fitted) == 3
    for block, rows in zip(("2025T1", "2025T2", "2025T3"), SpyRegressor.fitted, strict=True):
        assert rows.isdisjoint(set(blocks[blocks == block].index))
    assert predictions.iloc[0] == pytest.approx(np.mean(np.arange(4, 12)))
    with pytest.raises(ConfigError, match="un solo bloque"):
        trainer.out_of_fold_predictions(
            DummyRegressor, X, y, trainable, scored, pd.Series("2025T1", index=index)
        )


# -----------------------------------------------------------------------------
# Entrenamiento completo
# -----------------------------------------------------------------------------
def test_model_learns_planted_signal_beyond_the_baseline(trained):
    result = trained.result
    assert result.selected in trainer.CANDIDATES
    assert result.accepted
    assert result.improvement > 0.3
    importance = result.importance.set_index("variable")["aumento_mae_log"]
    # El tamaño y el tipo de entidad son la señal que la línea base no capta.
    assert importance.idxmax() in {"log_valor_referencial", "tipo_entidad", "entidad", "metodo"}
    population = trained.table["es_poblacion"]
    assert result.oof[population].notna().all()
    assert result.oof[~population].isna().all()
    assert {"__global__", "Bienes", "Servicios", "Obras"} <= set(result.scales)
    assert (
        result.metrics["prueba"][trainer.RATIO_ONE]["mae_log"]
        > result.metrics["prueba"][result.selected]["mae_log"]
    )


def test_canary_pure_noise_is_not_learned(model_config):
    """Canario de fuga: si el objetivo es ruido puro, nadie supera a la mediana global."""
    gold = make_gold_tables(signal=False, seed=21)
    table, X, specs = model_inputs(gold, model_config)
    result = trainer.train_model(table, X, specs, model_config)
    test = result.metrics["prueba"]
    gain = 1 - test[result.selected]["mae_log"] / test[trainer.GLOBAL_MEDIAN]["mae_log"]
    assert gain < 0.05
    assert not result.accepted


def test_canary_detects_a_leaky_feature(model_config):
    """Con una columna derivada del objetivo (como n_postores), el canario se dispara.

    Basta un modelo lineal para que la fuga infle el desempeño.
    """
    model_config["models"]["candidates"] = ["ridge"]
    gold = make_gold_tables(signal=False, seed=21)
    table, X, specs = model_inputs(gold, model_config)
    leak = gold["fact_proceso"]["n_postores"].astype("float64").to_numpy()
    table["fact_proceso.pista"] = leak  # nombre inocente que la guardia no reconoce
    X = X.assign(pista=leak)
    specs = [*specs, FeatureSpec("pista", "fact_proceso", "pista", "numeric")]
    result = trainer.train_model(table, X, specs, model_config)
    test = result.metrics["prueba"]
    gain = 1 - test[result.selected]["mae_log"] / test[trainer.GLOBAL_MEDIAN]["mae_log"]
    assert gain > 0.3


def test_split_dates_object_round_trip():
    dates = trainer.SplitDates(
        date(2026, 1, 18), date(2025, 4, 1), date(2025, 7, 1), date(2025, 10, 1)
    )
    assert dates.to_dict()["corte_madurez"] == "2025-10-01"
