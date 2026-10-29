"""Entrenamiento del modelo de monto esperado.

* **División temporal** por fecha de convocatoria (entrenamiento -> validación ->
  prueba). Un proceso entra al entrenamiento solo si también se adjudicó antes del
  inicio de la validación, y las convocatorias de los últimos meses no se evalúan
  (ventana de madurez: a esa altura solo se adjudicaron los procesos rápidos).
* **Línea base B1**: mediana de ``log(razón)`` del entrenamiento por método y categoría.
* **Candidatos** de scikit-learn (Ridge e HistGradientBoosting) dentro de un
  ``Pipeline``: toda transformación que aprende de los datos (codificación de
  categorías, ``TargetEncoder``, imputación) se ajusta solo con el entrenamiento.
* El candidato se elige en validación y se evalúa una sola vez en prueba.
* **Predicción fuera de muestra** por bloques (trimestres de convocatoria): cada
  proceso lo puntúa un modelo entrenado sin su bloque. Con esos residuos se calibran
  los umbrales de atípicos y se reporta el histórico sin el sesgo de puntuar con el
  mismo modelo que vio el dato.

Este módulo no lee ni escribe archivos: recibe DataFrames y devuelve resultados.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler, TargetEncoder

from contrataciones.features.catalog import FeatureSpec, names_by_kind
from contrataciones.features.dataset import TARGET
from contrataciones.models import anomaly, evaluator
from contrataciones.utils.config_loader import ConfigError
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

PARTITION_TRAIN = "entrenamiento"
PARTITION_VALIDATION = "validacion"
PARTITION_TEST = "prueba"
PARTITION_IMMATURE = "no_evaluado"
PARTITION_UNAVAILABLE = "no_disponible"
PARTITION_OUT = "no_entrenable"

BASELINE = "linea_base"
GLOBAL_MEDIAN = "mediana_global"
RATIO_ONE = "razon_1"
CANDIDATES: tuple[str, ...] = ("ridge", "hist_gradient_boosting")
LOWER_IS_BETTER = frozenset({"mae_log", "rmse_log", "mdape", "wape"})
MIN_PARTITION_ROWS = 10
DEFAULT_RANDOM_STATE = 2026
# HistGradientBoosting admite como máximo 255 categorías por variable.
MAX_CATEGORIES = 250
HGB_PARAMETERS: tuple[str, ...] = (
    "loss",
    "learning_rate",
    "max_iter",
    "max_leaf_nodes",
    "max_depth",
    "min_samples_leaf",
    "l2_regularization",
    "early_stopping",
    "random_state",
)


# -----------------------------------------------------------------------------
# División temporal
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class SplitDates:
    """Fechas de corte de la división temporal."""

    referencia: date
    inicio_validacion: date
    inicio_prueba: date
    corte_madurez: date

    def to_dict(self) -> dict[str, str]:
        return {name: value.isoformat() for name, value in asdict(self).items()}


def _months(split: Mapping[str, Any], key: str, default: int, minimum: int) -> int:
    value = int(split.get(key, default))
    if value < minimum:
        raise ConfigError(f"split.{key} debe ser >= {minimum} (model_config.yaml).")
    return value


def split_dates(table: pd.DataFrame, split: Mapping[str, Any]) -> SplitDates:
    """Calcula los cortes a partir de la fecha de referencia de los datos.

    Sin ``reference_date``, la referencia es la adjudicación más reciente de los
    procesos entrenables. Los cortes caen el primer día de un mes.
    """
    if split.get("reference_date"):
        reference = pd.Timestamp(str(split["reference_date"]))
    else:
        awarded = table.loc[table["es_entrenable"], "fecha_adjudicacion"].dropna()
        if awarded.empty:
            raise ConfigError(
                "No hay adjudicaciones con fecha para fijar la referencia temporal: "
                "define split.reference_date en model_config.yaml."
            )
        reference = pd.Timestamp(awarded.max())
    maturity = _months(split, "maturity_months", 3, 0)
    test = _months(split, "test_months", 3, 1)
    validation = _months(split, "validation_months", 3, 1)
    cut = (reference - pd.DateOffset(months=maturity)).to_period("M").to_timestamp()
    test_start = cut - pd.DateOffset(months=test)
    validation_start = test_start - pd.DateOffset(months=validation)
    return SplitDates(
        referencia=reference.date(),
        inicio_validacion=validation_start.date(),
        inicio_prueba=test_start.date(),
        corte_madurez=cut.date(),
    )


def assign_partitions(table: pd.DataFrame, dates: SplitDates) -> pd.Series:
    """Partición de cada proceso.

    * ``entrenamiento``: convocado y adjudicado antes del inicio de la validación.
    * ``no_disponible``: convocado antes de la validación pero adjudicado después (su
      monto no se conocía a esa fecha): no entrena ni se evalúa.
    * ``validacion`` y ``prueba``: por fecha de convocatoria.
    * ``no_evaluado``: convocado después del corte de madurez.
    * ``no_entrenable``: fuera de la población o con razón fuera de rango.
    """
    convened = table["fecha_convocatoria"]
    awarded = table["fecha_adjudicacion"]
    validation_start = pd.Timestamp(dates.inicio_validacion)
    test_start = pd.Timestamp(dates.inicio_prueba)
    cut = pd.Timestamp(dates.corte_madurez)
    trainable = table["es_entrenable"].astype(bool)
    early = trainable & (convened < validation_start)
    train = early & awarded.notna() & (awarded < validation_start)

    partition = pd.Series(PARTITION_OUT, index=table.index, dtype=object)
    partition.loc[early & ~train] = PARTITION_UNAVAILABLE
    partition.loc[train] = PARTITION_TRAIN
    partition.loc[trainable & (convened >= validation_start) & (convened < test_start)] = (
        PARTITION_VALIDATION
    )
    partition.loc[trainable & (convened >= test_start) & (convened < cut)] = PARTITION_TEST
    partition.loc[trainable & (convened >= cut)] = PARTITION_IMMATURE
    return partition


def time_blocks(dates: pd.Series, block: str = "quarter") -> pd.Series:
    """Bloque de cada fecha para la predicción fuera de muestra (``2025T3`` o ``2025-07``)."""
    if block not in {"quarter", "month"}:
        raise ConfigError("split.out_of_fold_block debe ser 'quarter' o 'month'.")
    periods = dates.dt.to_period("Q" if block == "quarter" else "M")
    labels = periods.astype(str).str.replace("Q", "T", regex=False)
    return labels.where(dates.notna()).astype(object)


# -----------------------------------------------------------------------------
# Estimadores
# -----------------------------------------------------------------------------
class MedianRatioBaseline(RegressorMixin, BaseEstimator):
    """Línea base B1: mediana de ``log(razón)`` del entrenamiento por grupo.

    Los grupos con menos de ``min_group_size`` procesos usan la mediana global.
    """

    def __init__(
        self, group_by: Sequence[str] = ("metodo", "categoria"), min_group_size: int = 20
    ) -> None:
        self.group_by = group_by
        self.min_group_size = min_group_size

    def _keys(self, X: pd.DataFrame) -> pd.Series:
        columns = list(self.group_by)
        missing = [c for c in columns if c not in X.columns]
        if missing:
            raise ValueError(f"La línea base necesita las variables {missing}.")
        return X[columns].astype(str).agg(" | ".join, axis=1)

    def fit(self, X: pd.DataFrame, y: Any) -> MedianRatioBaseline:
        target = pd.Series(np.asarray(y, dtype="float64"), index=X.index)
        self.global_median_ = float(target.median())
        stats = target.groupby(self._keys(X)).agg(["median", "size"])
        large = stats[stats["size"] >= int(self.min_group_size)]
        self.group_medians_ = {str(k): float(v) for k, v in large["median"].items()}
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        medians = self._keys(X).map(self.group_medians_)
        return medians.fillna(self.global_median_).to_numpy(dtype="float64")


def _random_state(models: Mapping[str, Any]) -> int:
    return int(models.get("random_state", DEFAULT_RANDOM_STATE))


def _preprocessor(
    specs: Sequence[FeatureSpec], params: Mapping[str, Any], *, linear: bool, random_state: int
) -> ColumnTransformer:
    groups = names_by_kind(specs)
    steps: list[tuple[str, Any, list[str]]] = []
    if linear:
        if groups["numeric"]:
            numeric = make_pipeline(
                SimpleImputer(strategy="median", add_indicator=True), StandardScaler()
            )
            steps.append(("numericas", numeric, groups["numeric"]))
        if groups["binary"]:
            steps.append(("binarias", SimpleImputer(strategy="most_frequent"), groups["binary"]))
        if groups["categorical"]:
            encoder = OneHotEncoder(
                handle_unknown="infrequent_if_exist",
                min_frequency=int(params.get("min_frequency", 10)),
                sparse_output=False,
            )
            steps.append(("categoricas", encoder, groups["categorical"]))
    else:
        numeric = groups["numeric"] + groups["binary"]
        if numeric:
            steps.append(("numericas", "passthrough", numeric))
        if groups["categorical"]:
            encoder = OrdinalEncoder(
                handle_unknown="use_encoded_value",
                unknown_value=np.nan,
                encoded_missing_value=np.nan,
                max_categories=MAX_CATEGORIES,
            )
            steps.append(("categoricas", encoder, groups["categorical"]))
    if groups["high_cardinality"]:
        # Validación cruzada interna barajada y reproducible (API de scikit-learn >= 1.9).
        folds = KFold(n_splits=5, shuffle=True, random_state=random_state)
        target_encoder = TargetEncoder(target_type="continuous", cv=folds)
        step = make_pipeline(target_encoder, StandardScaler()) if linear else target_encoder
        steps.append(("alta_cardinalidad", step, groups["high_cardinality"]))
    return ColumnTransformer(steps, remainder="drop", verbose_feature_names_out=False)


def make_estimator(
    name: str, specs: Sequence[FeatureSpec], models: Mapping[str, Any]
) -> BaseEstimator:
    """Estimador sin entrenar: ``linea_base``, ``mediana_global``, ``ridge`` o
    ``hist_gradient_boosting``."""
    random_state = _random_state(models)
    if name == BASELINE:
        cfg = models.get("baseline") or {}
        group_by = [str(c) for c in cfg.get("group_by") or ("metodo", "categoria")]
        missing = sorted(set(group_by) - {spec.name for spec in specs})
        if missing:
            raise ConfigError(f"models.baseline.group_by usa variables no habilitadas: {missing}.")
        return MedianRatioBaseline(tuple(group_by), int(cfg.get("min_group_size", 20)))
    if name == GLOBAL_MEDIAN:
        return DummyRegressor(strategy="median")
    if name == "ridge":
        params = models.get("ridge") or {}
        return Pipeline(
            [
                (
                    "preprocesamiento",
                    _preprocessor(specs, params, linear=True, random_state=random_state),
                ),
                ("modelo", Ridge(alpha=float(params.get("alpha", 1.0)))),
            ]
        )
    if name == "hist_gradient_boosting":
        params = dict(models.get("hist_gradient_boosting") or {})
        params.setdefault("random_state", random_state)
        hgb = {key: params[key] for key in HGB_PARAMETERS if key in params}
        categorical = names_by_kind(specs)["categorical"]
        preprocessor = _preprocessor(specs, params, linear=False, random_state=random_state)
        model = HistGradientBoostingRegressor(categorical_features=categorical or None, **hgb)
        return Pipeline(
            [
                ("preprocesamiento", preprocessor.set_output(transform="pandas")),
                ("modelo", model),
            ]
        )
    raise ConfigError(
        f"Modelo desconocido '{name}': usa {', '.join(CANDIDATES)} en models.candidates."
    )


def out_of_fold_predictions(
    factory: Callable[[], BaseEstimator],
    X: pd.DataFrame,
    y: pd.Series,
    trainable: pd.Series,
    scored: pd.Series,
    blocks: pd.Series,
) -> pd.Series:
    """Predicción de las filas ``scored`` con modelos entrenados sin su bloque."""
    predictions = pd.Series(np.nan, index=X.index, dtype="float64")
    block_names = sorted(blocks[scored].dropna().unique())
    if len(block_names) < 2:
        raise ConfigError(
            "Los datos abarcan un solo bloque de convocatoria: no se puede predecir fuera "
            "de muestra. Usa un periodo más largo o split.out_of_fold_block: month."
        )
    for block in block_names:
        in_block = blocks.eq(block)
        fit_rows = trainable & ~in_block
        target_rows = scored & in_block
        model = factory().fit(X[fit_rows], y[fit_rows])
        predictions.loc[target_rows] = model.predict(X[target_rows])
    return predictions


# -----------------------------------------------------------------------------
# Entrenamiento completo
# -----------------------------------------------------------------------------
@dataclass
class TrainingResult:
    """Modelo final, particiones, métricas y calibración de atípicos."""

    selected: str
    estimator: BaseEstimator
    dates: SplitDates
    partitions: pd.Series
    blocks: pd.Series
    oof: pd.Series
    metrics: dict[str, Any]
    segment_metrics: pd.DataFrame
    importance: pd.DataFrame
    scales: dict[str, dict[str, float]]
    improvement: float
    accepted: bool


def _select(
    candidates: Sequence[str], validation: Mapping[str, Mapping[str, float]], metric: str
) -> str:
    if metric not in evaluator.METRIC_NAMES:
        raise ConfigError(
            f"models.selection_metric '{metric}' no es una de {', '.join(evaluator.METRIC_NAMES)}."
        )
    sign = 1.0 if metric in LOWER_IS_BETTER else -1.0

    def score(name: str) -> float:
        value = validation[name][metric]
        return sign * value if math.isfinite(value) else math.inf

    return min(candidates, key=score)


def train_model(
    table: pd.DataFrame,
    X: pd.DataFrame,
    specs: Sequence[FeatureSpec],
    config: Mapping[str, Any],
) -> TrainingResult:
    """Entrena, selecciona, evalúa y calibra el modelo de monto esperado."""
    models = config.get("models") or {}
    split = config.get("split") or {}
    anomalies = config.get("anomalies") or {}
    y = table[TARGET].astype("float64")
    trainable = table["es_entrenable"].astype(bool)
    scored = table["es_poblacion"].astype(bool)
    log_reference = np.log(table["valor_referencial_pen"].where(scored))

    dates = split_dates(table, split)
    partitions = assign_partitions(table, dates)
    counts = partitions.value_counts()
    for part in (PARTITION_TRAIN, PARTITION_VALIDATION, PARTITION_TEST):
        if counts.get(part, 0) < MIN_PARTITION_ROWS:
            raise ConfigError(
                f"La partición '{part}' tiene {int(counts.get(part, 0))} procesos (mínimo "
                f"{MIN_PARTITION_ROWS}). Usa un periodo de datos más largo o ajusta split en "
                "model_config.yaml."
            )
    train = partitions.eq(PARTITION_TRAIN)
    validation_rows = partitions.eq(PARTITION_VALIDATION)
    test_rows = partitions.eq(PARTITION_TEST)
    logger.info(
        "Particiones: %s (inicio validación %s, inicio prueba %s, corte de madurez %s)",
        {k: int(v) for k, v in counts.items()},
        dates.inicio_validacion,
        dates.inicio_prueba,
        dates.corte_madurez,
    )

    candidates = [str(c) for c in models.get("candidates") or CANDIDATES]
    fitted = {
        name: make_estimator(name, specs, models).fit(X[train], y[train])
        for name in (BASELINE, GLOBAL_MEDIAN, *candidates)
    }

    def evaluate(rows: pd.Series, names: Sequence[str]) -> dict[str, dict[str, float]]:
        results = {
            name: evaluator.regression_metrics(
                y[rows], fitted[name].predict(X[rows]), log_reference[rows]
            )
            for name in names
        }
        results[RATIO_ONE] = evaluator.regression_metrics(
            y[rows], np.zeros(int(rows.sum())), log_reference[rows]
        )
        return results

    validation = evaluate(validation_rows, list(fitted))
    metric = str(models.get("selection_metric", "mae_log"))
    selected = _select(candidates, validation, metric)
    test = evaluate(test_rows, [selected, BASELINE, GLOBAL_MEDIAN])
    gain = evaluator.improvement(test[selected]["mae_log"], test[BASELINE]["mae_log"])
    threshold = float(models.get("min_improvement_vs_baseline", 0.10))
    accepted = bool(math.isfinite(gain) and gain >= threshold)
    logger.info(
        "Seleccionado %s; prueba MAE log %.4f vs línea base %.4f (mejora %.1f %%)",
        selected,
        test[selected]["mae_log"],
        test[BASELINE]["mae_log"],
        100 * gain if math.isfinite(gain) else float("nan"),
    )

    blocks = time_blocks(
        table["fecha_convocatoria"], str(split.get("out_of_fold_block", "quarter"))
    )
    segment_frame = pd.DataFrame(
        {
            "y_real": y[test_rows],
            "y_modelo": fitted[selected].predict(X[test_rows]),
            "y_linea_base": fitted[BASELINE].predict(X[test_rows]),
            "categoria": X.loc[test_rows, "categoria"] if "categoria" in X else "Todas",
            "metodo": X.loc[test_rows, "metodo"] if "metodo" in X else "Todos",
            "quintil_valor_referencial": evaluator.value_quintiles(
                table.loc[test_rows, "valor_referencial_pen"]
            ),
            "trimestre": blocks[test_rows],
            "adjudicado_igual_referencial": table.loc[
                test_rows, "es_adjudicado_igual_referencial"
            ].map({True: "Sí", False: "No"}),
        }
    )
    segments = evaluator.segment_metrics(
        segment_frame,
        [
            "categoria",
            "metodo",
            "quintil_valor_referencial",
            "trimestre",
            "adjudicado_igual_referencial",
        ],
    )
    importance = evaluator.permutation_importance_table(
        fitted[selected],
        X[test_rows],
        y[test_rows],
        n_repeats=int(models.get("permutation_repeats", 5)),
        random_state=_random_state(models),
    )

    oof = out_of_fold_predictions(
        lambda: make_estimator(selected, specs, models), X, y, trainable, scored, blocks
    )
    segment_by = str(anomalies.get("segment_by", "categoria"))
    if segment_by not in X.columns:
        raise ConfigError(f"anomalies.segment_by '{segment_by}' no es una feature habilitada.")
    scales = anomaly.robust_scales(
        (y - oof)[trainable],
        X.loc[trainable, segment_by],
        min_segment_size=int(anomalies.get("min_segment_size", 30)),
        min_scale=float(anomalies.get("min_scale", 0.05)),
    )
    final = make_estimator(selected, specs, models).fit(X[trainable], y[trainable])

    metrics = {
        "seleccion": {"metrica": metric, "modelo": selected, "candidatos": candidates},
        "validacion": validation,
        "prueba": test,
        "mejora_vs_linea_base": gain,
        "criterio_aceptacion": threshold,
        "aceptado": accepted,
        "fuera_de_muestra": evaluator.regression_metrics(
            y[trainable], oof[trainable], log_reference[trainable]
        ),
    }
    return TrainingResult(
        selected=selected,
        estimator=final,
        dates=dates,
        partitions=partitions,
        blocks=blocks,
        oof=oof,
        metrics=metrics,
        segment_metrics=segments,
        importance=importance,
        scales=scales,
        improvement=gain,
        accepted=accepted,
    )
