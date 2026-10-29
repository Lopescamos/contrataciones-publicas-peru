"""Catálogo de features y guardia contra la fuga de datos (*data leakage*).

Una feature solo es válida si se conoce al publicar la convocatoria. Las features se
declaran en ``config/model_config.yaml`` con su columna de origen en la capa gold
(``tabla.columna``) y el momento en que se conocen (``available_at``).

Este módulo rechaza, aunque se declaren en el YAML:

* features con ``available_at`` distinto de ``convocatoria``;
* columnas de tablas que describen el resultado del proceso (adjudicaciones,
  contratos, postores, alertas, proveedores, sanciones y el agregado anual);
* columnas de ``fact_proceso`` que son el objetivo, posteriores a la convocatoria o
  identificadores;
* columnas cuyo nombre delata información del resultado (``adjudic``, ``postor``...),
  como defensa ante columnas que se agreguen en el futuro a la capa gold.

Las listas viven en el código a propósito: no se pueden desactivar desde la
configuración. Ampliarlas exige un cambio revisado y su prueba.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from contrataciones.utils.config_loader import ConfigError

AVAILABLE_AT = "convocatoria"
KINDS: tuple[str, ...] = ("numeric", "categorical", "binary", "high_cardinality")
TRANSFORMS: tuple[str, ...] = ("none", "log1p", "month", "entity_type")

# Tablas de la capa gold que describen el proceso tal como se convoca.
ALLOWED_TABLES: tuple[str, ...] = ("fact_proceso", "dim_metodo", "dim_categoria", "dim_entidad")

FORBIDDEN_TABLES: dict[str, str] = {
    "fact_adjudicacion": "describe el resultado (ganador, montos y fechas de adjudicación)",
    "fact_contrato": "es posterior a la adjudicación (contrato firmado)",
    "fact_postor": "el OECE publica los postores junto con la buena pro o el desierto",
    "fact_alerta": "las alertas se calculan con el monto adjudicado y los postores",
    "fact_sancion": "se cruza con el proveedor adjudicado",
    "dim_proveedor": "identifica al proveedor ganador",
    "dim_indicador": "es el catálogo de alertas, que se calculan después de adjudicar",
    "agg_entidad_anio": "resume el año completo, incluidos el propio proceso y los posteriores",
    "dim_fecha": (
        "se une por varias fechas (convocatoria, adjudicación, firma); deriva la fecha de "
        "fact_proceso.fecha_convocatoria_key con transform: month"
    ),
}

_RISK = "se calcula con el monto adjudicado y los postores (RF01, RF03, RF04)"
FORBIDDEN_COLUMNS: dict[str, str] = {
    "fact_proceso.monto_adjudicado_pen": "es el objetivo del modelo",
    "fact_proceso.ratio_adjudicado_referencial": "es el objetivo dividido por el valor referencial",
    "fact_proceso.n_postores": "el OECE publica los postores junto con la buena pro o el desierto",
    "fact_proceso.n_adjudicaciones": "se conoce al adjudicar",
    "fact_proceso.estado": "es el estado final del proceso, posterior a la convocatoria",
    "fact_proceso.n_alertas": _RISK,
    "fact_proceso.puntaje_riesgo": _RISK,
    "fact_proceso.nivel_riesgo": _RISK,
    "fact_proceso.nivel_riesgo_orden": _RISK,
    "fact_proceso.proceso_key": "es un identificador: el modelo lo memorizaría",
    "fact_proceso.ocid": "es un identificador: el modelo lo memorizaría",
    "fact_proceso.nomenclatura": "es un identificador (repite siglas de método, año y entidad)",
}

# Fragmentos de nombre que delatan información del resultado del proceso.
FORBIDDEN_NAME_FRAGMENTS: tuple[str, ...] = (
    "adjudic",
    "postor",
    "alerta",
    "riesgo",
    "ganador",
    "sancion",
    "proveedor",
    "contrato",
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class LeakageError(ConfigError):
    """La feature usaría información que no se conoce al convocar (fuga de datos)."""


@dataclass(frozen=True)
class FeatureSpec:
    """Definición validada de una feature."""

    name: str
    table: str
    column: str
    kind: str
    transform: str = "none"
    available_at: str = AVAILABLE_AT
    conditional: bool = False
    enabled: bool = True
    description: str = ""

    @property
    def source(self) -> str:
        """Columna de origen en la capa gold (``tabla.columna``)."""
        return f"{self.table}.{self.column}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def forbidden_reason(table: str, column: str) -> str | None:
    """Motivo por el que una columna de la capa gold no puede ser feature (o ``None``)."""
    if table in FORBIDDEN_TABLES:
        return FORBIDDEN_TABLES[table]
    qualified = f"{table}.{column}"
    if qualified in FORBIDDEN_COLUMNS:
        return FORBIDDEN_COLUMNS[qualified]
    fragment = next((f for f in FORBIDDEN_NAME_FRAGMENTS if f in column.lower()), None)
    if fragment:
        return f"su nombre ('{fragment}') delata información del resultado del proceso"
    return None


def check_source(source: str, available_at: str, feature: str = "") -> tuple[str, str]:
    """Valida el origen de una feature y devuelve ``(tabla, columna)``.

    Lanza :class:`LeakageError` si la feature usaría información posterior a la
    convocatoria y :class:`ConfigError` si el origen está mal escrito.
    """
    label = f"La feature '{feature}'" if feature else "La columna"
    if available_at != AVAILABLE_AT:
        raise LeakageError(
            f"{label} se conoce en '{available_at}': solo se aceptan features disponibles "
            f"en la '{AVAILABLE_AT}'."
        )
    table, separator, column = str(source).partition(".")
    if not separator or not table or not column:
        raise ConfigError(f"{label}: el origen debe tener la forma tabla.columna, no '{source}'.")
    reason = forbidden_reason(table, column)
    if reason:
        raise LeakageError(f"{label} usa {source}: {reason}.")
    if table not in ALLOWED_TABLES:
        raise LeakageError(
            f"{label} usa la tabla '{table}', que no está entre las permitidas: "
            f"{', '.join(ALLOWED_TABLES)}."
        )
    return table, column


def parse_feature(name: str, config: Mapping[str, Any]) -> FeatureSpec:
    """Convierte la declaración YAML de una feature en un :class:`FeatureSpec` validado."""
    if not _NAME_PATTERN.match(str(name)):
        raise ConfigError(f"Nombre de feature inválido: '{name}' (usa snake_case).")
    if not isinstance(config, Mapping):
        raise ConfigError(f"La feature '{name}' debe declarar source, available_at y kind.")
    missing = [key for key in ("source", "available_at", "kind") if key not in config]
    if missing:
        raise ConfigError(f"A la feature '{name}' le falta: {', '.join(missing)}.")
    table, column = check_source(str(config["source"]), str(config["available_at"]), name)
    kind = str(config["kind"])
    transform = str(config.get("transform") or "none")
    if kind not in KINDS:
        raise ConfigError(f"Feature '{name}': kind '{kind}' no es uno de {', '.join(KINDS)}.")
    if transform not in TRANSFORMS:
        raise ConfigError(
            f"Feature '{name}': transform '{transform}' no es uno de {', '.join(TRANSFORMS)}."
        )
    return FeatureSpec(
        name=str(name),
        table=table,
        column=column,
        kind=kind,
        transform=transform,
        available_at=str(config["available_at"]),
        conditional=bool(config.get("conditional", False)),
        enabled=bool(config.get("enabled", True)),
        description=str(config.get("description") or ""),
    )


def load_feature_specs(
    features: Mapping[str, Any] | None, *, include_disabled: bool = False
) -> list[FeatureSpec]:
    """Valida todas las features declaradas y devuelve las habilitadas.

    También se validan las deshabilitadas: una declaración con fuga de datos es un
    error aunque esté apagada.
    """
    if not features:
        raise ConfigError("config/model_config.yaml no declara features.")
    specs = [parse_feature(name, cfg) for name, cfg in features.items()]
    enabled = [spec for spec in specs if spec.enabled]
    if not enabled:
        raise ConfigError("Todas las features de config/model_config.yaml están deshabilitadas.")
    return specs if include_disabled else enabled


def specs_from_dicts(items: Iterable[Mapping[str, Any]]) -> list[FeatureSpec]:
    """Reconstruye y vuelve a validar las features guardadas en un modelo entrenado."""
    specs = []
    for item in items:
        spec = FeatureSpec(**dict(item))
        check_source(spec.source, spec.available_at, spec.name)
        specs.append(spec)
    return specs


def names_by_kind(specs: Iterable[FeatureSpec]) -> dict[str, list[str]]:
    """Nombres de las features agrupados por tipo (``kind``)."""
    groups: dict[str, list[str]] = {kind: [] for kind in KINDS}
    for spec in specs:
        groups[spec.kind].append(spec.name)
    return groups
