"""Construcción de la matriz de features a partir del dataset de modelado.

Aquí solo hay transformaciones sin estado, que no aprenden de los datos: logaritmo,
mes de una llave de fecha y tipo de entidad por palabras clave. Las que sí aprenden
(codificación de categorías, ``TargetEncoder``, imputación) viven dentro del
``Pipeline`` de scikit-learn (``models/trainer.py``) para ajustarse solo con la
partición de entrenamiento y aplicarse igual al predecir.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from contrataciones.features.catalog import FeatureSpec
from contrataciones.processing.cleaner import normalize_key

MISSING_CATEGORY = "Sin dato"
DEFAULT_ENTITY_TYPE = "Otra"


def entity_type(
    names: pd.Series,
    rules: Sequence[Mapping[str, Any]],
    default: str = DEFAULT_ENTITY_TYPE,
) -> pd.Series:
    """Tipo de entidad según su nombre.

    Las reglas se evalúan en orden y gana la primera cuya palabra clave aparezca
    como palabra completa en el nombre normalizado (mayúsculas, sin tildes ni signos).
    """
    compiled = [
        (str(rule["label"]), [f" {key} " for key in map(normalize_key, rule.get("keywords") or [])])
        for rule in rules
    ]

    def classify(name: Any) -> str:
        key = normalize_key(name)
        if not key:
            return default
        padded = f" {key} "
        for label, keywords in compiled:
            if any(keyword in padded for keyword in keywords if keyword.strip()):
                return label
        return default

    labels = {name: classify(name) for name in names.dropna().unique()}
    return names.map(labels).fillna(default).astype(object)


def month_from_key(keys: pd.Series) -> pd.Series:
    """Mes (``"01"`` a ``"12"``) de una llave de fecha AAAAMMDD; nulo si falta."""
    numeric = pd.to_numeric(keys, errors="coerce")
    month = (numeric // 100) % 100
    month = month.where(month.between(1, 12))
    return month.map(lambda m: f"{int(m):02d}" if pd.notna(m) else None).astype(object)


def _transform(series: pd.Series, spec: FeatureSpec, entity_types: Mapping[str, Any]) -> pd.Series:
    if spec.transform == "log1p":
        numeric = pd.to_numeric(series, errors="coerce").astype("float64")
        return np.log1p(numeric.where(numeric >= 0))
    if spec.transform == "month":
        return month_from_key(series)
    if spec.transform == "entity_type":
        return entity_type(
            series,
            entity_types.get("rules") or [],
            str(entity_types.get("default") or DEFAULT_ENTITY_TYPE),
        )
    return series


def _cast(series: pd.Series, kind: str) -> pd.Series:
    if kind == "numeric":
        return pd.to_numeric(series, errors="coerce").astype("float64")
    if kind == "binary":
        return series.map(lambda v: np.nan if pd.isna(v) else float(bool(v))).astype("float64")
    # categorical y high_cardinality: texto, con los vacíos como categoría propia.
    return series.map(
        lambda v: MISSING_CATEGORY if pd.isna(v) or not str(v).strip() else str(v)
    ).astype(object)


def build_features(
    table: pd.DataFrame,
    specs: Sequence[FeatureSpec],
    entity_types: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Matriz de features: una columna por feature habilitada, con el índice de ``table``."""
    columns: dict[str, pd.Series] = {}
    for spec in specs:
        if spec.source not in table.columns:
            raise KeyError(
                f"La feature '{spec.name}' usa {spec.source}, que no existe en la capa gold."
            )
        values = _transform(table[spec.source], spec, entity_types or {})
        columns[spec.name] = _cast(values, spec.kind)
    return pd.DataFrame(columns, index=table.index)
