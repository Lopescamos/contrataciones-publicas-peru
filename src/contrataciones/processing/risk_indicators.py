"""Indicadores de riesgo (red flags) basados en reglas transparentes.

Cada indicador marca procesos de contratación que conviene revisar. Una alerta
NO es evidencia de corrupción ni de irregularidad: es una señal para priorizar
la revisión humana. La metodología se basa en la guía *Red Flags in Public
Procurement* (Open Contracting Partnership, 2024) y en la librería Cardinal.

=====  ===========================================  ===========================
Código Indicador                                    Referencia
=====  ===========================================  ===========================
RF01   Postor único en procedimiento competitivo    Cardinal R018
RF02   Plazo de presentación corto                  Cardinal R003
RF03   Adjudicación >= 98 % del valor referencial   Indicador del proyecto
RF04   Adjudicación supera el valor referencial     Indicador del proyecto
RF05   Contratación directa                         Indicador del proyecto
RF06   Proveedor inhabilitado al adjudicarse        Cruce con sanciones del TCP
RF07   Concentración proveedor-entidad              Indicador del proyecto
=====  ===========================================  ===========================

Puntaje del proceso = suma de pesos de sus alertas (tope 100), y nivel
Sin alertas / Bajo / Medio / Alto según ``config/risk_rules.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from contrataciones.processing.cleaner import normalize_key
from contrataciones.utils.constants import RISK_LEVELS
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

FLAG_COLUMNS = ["ocid", "codigo", "detalle"]


@dataclass(frozen=True)
class Indicator:
    codigo: str
    nombre: str
    descripcion: str
    referencia: str


CATALOG: dict[str, Indicator] = {
    "RF01": Indicator(
        "RF01",
        "Postor único",
        "Procedimiento competitivo en el que se registró un solo postor.",
        "OCP Cardinal R018 - Single bid received",
    ),
    "RF02": Indicator(
        "RF02",
        "Plazo de presentación corto",
        "En un procedimiento competitivo, el plazo evaluado (presentación de ofertas o, si se "
        "configura, formulación de consultas) es menor al umbral.",
        "OCP Cardinal R003 - Short submission period",
    ),
    "RF03": Indicator(
        "RF03",
        "Adjudicación cercana al valor referencial",
        "En un procedimiento competitivo, el monto adjudicado es al menos el 98 % del valor "
        "referencial (señal de poca presión competitiva sobre el precio).",
        "Indicador del proyecto (guía OCP 2024: precio sin competencia)",
    ),
    "RF04": Indicator(
        "RF04",
        "Adjudicación supera el valor referencial",
        "El monto adjudicado total es mayor que el valor referencial del proceso.",
        "Indicador del proyecto",
    ),
    "RF05": Indicator(
        "RF05",
        "Contratación directa",
        "Procedimiento no competitivo (contratación directa). Informativo: puede ser legal.",
        "Indicador del proyecto",
    ),
    "RF06": Indicator(
        "RF06",
        "Proveedor inhabilitado al adjudicarse",
        "El proveedor tenía una sanción de inhabilitación vigente en la fecha de adjudicación.",
        "Cruce con sanciones del Tribunal de Contrataciones Públicas",
    ),
    "RF07": Indicator(
        "RF07",
        "Concentración proveedor-entidad",
        "Un proveedor concentra al menos el 50 % del monto adjudicado por una entidad en el año.",
        "Indicador del proyecto (guía OCP 2024: concentración de mercado)",
    ),
}


def _cfg(rules: dict[str, Any], code: str) -> dict[str, Any]:
    return (rules.get("indicators") or {}).get(code) or {}


def is_enabled(rules: dict[str, Any], code: str) -> bool:
    return bool(_cfg(rules, code).get("enabled", True))


def _flags(frame: pd.DataFrame, code: str, detail: pd.Series | str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=FLAG_COLUMNS)
    detalle = detail if isinstance(detail, pd.Series) else pd.Series(detail, index=frame.index)
    return pd.DataFrame(
        {
            "ocid": frame["ocid"].to_numpy(),
            "codigo": code,
            "detalle": detalle.astype(str).to_numpy(),
        }
    )


def eligible_processes(procesos: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """Excluye procesos cancelados o retirados de todos los indicadores."""
    excluded = [s.lower() for s in rules.get("excluded_tender_status", ["cancelled"])]
    return procesos[~procesos["estado"].fillna("").str.lower().isin(excluded)]


# -----------------------------------------------------------------------------
# Indicadores a nivel de proceso
# -----------------------------------------------------------------------------
def flag_single_bidder(procesos: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """RF01: procedimiento competitivo con exactamente un postor."""
    hits = procesos[procesos["es_competitivo"] & procesos["n_postores"].eq(1).fillna(False)]
    return _flags(hits, "RF01", "1 postor en " + hits["metodo_detalle"].astype(str))


RF02_PERIODS: dict[str, tuple[str, str]] = {
    "presentacion": ("plazo_presentacion_dias", "Plazo de presentación"),
    "consultas": ("plazo_consultas_dias", "Plazo de consultas"),
}


def flag_short_submission(procesos: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """RF02: plazo menor al umbral (general o por procedimiento).

    ``period: presentacion`` (por defecto) evalúa ``tender.tenderPeriod``;
    ``period: consultas`` evalúa ``tender.enquiryPeriod``, útil cuando la fuente
    no informa el cierre de la presentación (ver docs/08_indicadores_de_riesgo.md).
    Los procesos sin plazo informado no se evalúan.
    """
    cfg = _cfg(rules, "RF02")
    period = str(cfg.get("period") or "presentacion").strip().lower()
    if period not in RF02_PERIODS:
        raise ValueError(f"RF02.period debe ser uno de {sorted(RF02_PERIODS)}, no '{period}'")
    column, label = RF02_PERIODS[period]
    default = int(cfg.get("threshold_days", 15))
    by_method = {str(k): int(v) for k, v in (cfg.get("threshold_by_method") or {}).items()}
    threshold = procesos["metodo_detalle"].map(by_method).fillna(default)
    if column in procesos:
        days = procesos[column].astype("float64")
    else:
        days = pd.Series(np.nan, index=procesos.index)
    mask = days.notna() & (days < threshold) & procesos["es_competitivo"]
    hits = procesos[mask]
    detail = (
        f"{label} de "
        + days[mask].astype(int).astype(str)
        + " días (umbral "
        + threshold[mask].astype(int).astype(str)
        + ")"
    )
    return _flags(hits, "RF02", detail)


def flag_price_near_reference(procesos: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """RF03: adjudicado / referencial entre ``min_ratio`` y 100 %."""
    min_ratio = float(_cfg(rules, "RF03").get("min_ratio", 0.98))
    ratio = procesos["ratio_adjudicado_referencial"].astype("float64")
    mask = procesos["es_competitivo"] & ratio.between(min_ratio, 1.0, inclusive="both")
    hits = procesos[mask]
    return _flags(hits, "RF03", "Adjudicado al " + (ratio[mask] * 100).round(1).astype(str) + " %")


def flag_award_above_reference(procesos: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """RF04: adjudicado total > referencial x (1 + tolerancia)."""
    tolerance = float(_cfg(rules, "RF04").get("tolerance", 0.0))
    ratio = procesos["ratio_adjudicado_referencial"].astype("float64")
    mask = ratio > 1.0 + tolerance + 1e-9
    hits = procesos[mask.fillna(False)]
    detail = "Adjudicado al " + (ratio[mask.fillna(False)] * 100).round(1).astype(str) + " %"
    return _flags(hits, "RF04", detail)


def flag_direct_contracting(procesos: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """RF05: contratación directa (no competitiva)."""
    hits = procesos[procesos["es_contratacion_directa"]]
    return _flags(hits, "RF05", hits["metodo_detalle"].astype(str))


# -----------------------------------------------------------------------------
# Indicadores a nivel de adjudicación
# -----------------------------------------------------------------------------
def filter_sanction_types(sanciones: pd.DataFrame, keywords: list[str] | None) -> pd.DataFrame:
    """Conserva las sanciones cuyo tipo contiene alguna palabra clave (o sin tipo)."""
    if not keywords or sanciones.empty or "tipo_sancion" not in sanciones:
        return sanciones
    keys = [normalize_key(k) for k in keywords if normalize_key(k)]
    tipo = sanciones["tipo_sancion"].map(normalize_key)
    matches = tipo.apply(lambda t: t is None or any(k in t for k in keys))
    return sanciones[matches.astype(bool)]


def sanctioned_award_mask(
    adjudicaciones: pd.DataFrame,
    sanciones: pd.DataFrame,
    type_keywords: list[str] | None = None,
) -> pd.Series:
    """True si el proveedor tenía una sanción vigente en la fecha de adjudicación."""
    result = pd.Series(False, index=adjudicaciones.index)
    if sanciones is None or sanciones.empty or adjudicaciones.empty:
        return result
    sanciones = filter_sanction_types(sanciones, type_keywords)
    if sanciones.empty:
        return result
    valid = sanciones[sanciones["ruc_valido"] & sanciones["fecha_inicio"].notna()]
    candidates = adjudicaciones[
        adjudicaciones["ruc_valido"] & adjudicaciones["fecha_adjudicacion"].notna()
    ]
    if valid.empty or candidates.empty:
        return result
    merged = (
        candidates[["ruc", "fecha_adjudicacion"]]
        .reset_index()
        .merge(valid[["ruc", "fecha_inicio", "fecha_fin"]], on="ruc", how="inner")
    )
    award_day = merged["fecha_adjudicacion"].dt.normalize()
    end = merged["fecha_fin"].fillna(pd.Timestamp.max.normalize())
    inside = (award_day >= merged["fecha_inicio"]) & (award_day <= end)
    hit_rows = merged.loc[inside, "index"].unique()
    result.loc[hit_rows] = True
    return result


def sanction_keywords(rules: dict[str, Any]) -> list[str]:
    return list(_cfg(rules, "RF06").get("sanction_type_keywords") or [])


def flag_sanctioned_supplier(
    adjudicaciones: pd.DataFrame, sanciones: pd.DataFrame, rules: dict[str, Any] | None = None
) -> pd.DataFrame:
    """RF06: proveedor inhabilitado en la fecha de adjudicación."""
    mask = sanctioned_award_mask(adjudicaciones, sanciones, sanction_keywords(rules or {}))
    hits = adjudicaciones[mask & adjudicaciones["es_valida"]]
    if hits.empty:
        return pd.DataFrame(columns=FLAG_COLUMNS)
    detail = "Proveedor " + hits["ruc"].astype(str) + " con sanción vigente"
    flags = _flags(hits, "RF06", detail)
    return flags.drop_duplicates(subset=["ocid", "codigo"])


def supplier_shares(adjudicaciones: pd.DataFrame) -> pd.DataFrame:
    """Participación de cada proveedor en el monto adjudicado por entidad y año."""
    valid = adjudicaciones[
        adjudicaciones["es_valida"]
        & adjudicaciones["proveedor_id"].notna()
        & adjudicaciones["entidad_id"].notna()
        & adjudicaciones["anio"].notna()
        & (adjudicaciones["monto_asignado_pen"] > 0)
    ]
    if valid.empty:
        return pd.DataFrame(
            columns=[
                "entidad_id",
                "anio",
                "proveedor_id",
                "monto",
                "monto_entidad",
                "share",
                "n_procesos_entidad",
            ]
        )
    by_supplier = (
        valid.groupby(["entidad_id", "anio", "proveedor_id"], as_index=False)["monto_asignado_pen"]
        .sum()
        .rename(columns={"monto_asignado_pen": "monto"})
    )
    by_entity = (
        valid.groupby(["entidad_id", "anio"])
        .agg(monto_entidad=("monto_asignado_pen", "sum"), n_procesos_entidad=("ocid", "nunique"))
        .reset_index()
    )
    shares = by_supplier.merge(by_entity, on=["entidad_id", "anio"], how="left")
    shares["share"] = shares["monto"] / shares["monto_entidad"]
    return shares


def herfindahl_index(shares: pd.DataFrame) -> pd.DataFrame:
    """Índice Herfindahl-Hirschman (0-10 000) por entidad y año."""
    if shares.empty:
        return pd.DataFrame(columns=["entidad_id", "anio", "hhi"])
    frame = shares.assign(sq=(shares["share"] * 100) ** 2)
    return (
        frame.groupby(["entidad_id", "anio"], as_index=False)["sq"]
        .sum()
        .rename(columns={"sq": "hhi"})
    )


def flag_supplier_concentration(
    adjudicaciones: pd.DataFrame, rules: dict[str, Any]
) -> pd.DataFrame:
    """RF07: proveedor con participación >= ``min_share`` en una entidad-año."""
    cfg = _cfg(rules, "RF07")
    min_share = float(cfg.get("min_share", 0.5))
    min_processes = int(cfg.get("min_processes", 5))
    shares = supplier_shares(adjudicaciones)
    if shares.empty:
        return pd.DataFrame(columns=FLAG_COLUMNS)
    dominant = shares[
        (shares["share"] >= min_share) & (shares["n_procesos_entidad"] >= min_processes)
    ]
    if dominant.empty:
        return pd.DataFrame(columns=FLAG_COLUMNS)
    awards = adjudicaciones[adjudicaciones["es_valida"]].merge(
        dominant[["entidad_id", "anio", "proveedor_id", "share"]],
        on=["entidad_id", "anio", "proveedor_id"],
        how="inner",
    )
    detail = (
        "Proveedor concentra "
        + (awards["share"] * 100).round(1).astype(str)
        + " % del monto de la entidad en "
        + awards["anio"].astype("Int64").astype(str)
    )
    return _flags(awards, "RF07", detail).drop_duplicates(subset=["ocid", "codigo"])


# -----------------------------------------------------------------------------
# Orquestación
# -----------------------------------------------------------------------------
def compute_flags(
    procesos: pd.DataFrame,
    adjudicaciones: pd.DataFrame,
    sanciones: pd.DataFrame,
    rules: dict[str, Any],
) -> pd.DataFrame:
    """Calcula todas las alertas habilitadas. Devuelve ``ocid, codigo, detalle``."""
    base = eligible_processes(procesos, rules)
    eligible_ocids = set(base["ocid"])
    awards = adjudicaciones[adjudicaciones["ocid"].isin(eligible_ocids)]
    functions = {
        "RF01": lambda: flag_single_bidder(base, rules),
        "RF02": lambda: flag_short_submission(base, rules),
        "RF03": lambda: flag_price_near_reference(base, rules),
        "RF04": lambda: flag_award_above_reference(base, rules),
        "RF05": lambda: flag_direct_contracting(base, rules),
        "RF06": lambda: flag_sanctioned_supplier(awards, sanciones, rules),
        "RF07": lambda: flag_supplier_concentration(awards, rules),
    }
    frames = []
    for code, function in functions.items():
        if not is_enabled(rules, code):
            continue
        result = function()
        logger.info("Indicador %s (%s): %d procesos", code, CATALOG[code].nombre, len(result))
        frames.append(result)
    if not frames:
        return pd.DataFrame(columns=FLAG_COLUMNS)
    flags = pd.concat([f for f in frames if not f.empty] or [frames[0]], ignore_index=True)
    return flags.drop_duplicates(subset=["ocid", "codigo"]).reset_index(drop=True)


def score_processes(ocids: pd.Series, flags: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """Puntaje y nivel de riesgo por proceso."""
    weights = {code: int(_cfg(rules, code).get("weight", 0)) for code in CATALOG}
    scoring = rules.get("scoring") or {}
    max_score = int(scoring.get("max_score", 100))
    levels = scoring.get("levels") or {"Medio": 25, "Alto": 50}
    medium, high = int(levels.get("Medio", 25)), int(levels.get("Alto", 50))

    base = pd.DataFrame({"ocid": ocids.drop_duplicates().to_numpy()})
    if flags.empty:
        base["n_alertas"] = 0
        base["puntaje_riesgo"] = 0
    else:
        weighted = flags.assign(peso=flags["codigo"].map(weights).fillna(0))
        agg = weighted.groupby("ocid").agg(
            n_alertas=("codigo", "nunique"), puntaje_riesgo=("peso", "sum")
        )
        base = base.merge(agg, on="ocid", how="left")
        base["n_alertas"] = base["n_alertas"].fillna(0).astype(int)
        base["puntaje_riesgo"] = base["puntaje_riesgo"].fillna(0).clip(upper=max_score).astype(int)
    score = base["puntaje_riesgo"]
    base["nivel_riesgo"] = np.select(
        [score >= high, score >= medium, score > 0],
        ["Alto", "Medio", "Bajo"],
        default="Sin alertas",
    )
    # Orden para visualizaciones (Power BI: "Sort by column").
    base["nivel_riesgo_orden"] = (
        base["nivel_riesgo"]
        .map({level: position for position, level in enumerate(RISK_LEVELS)})
        .astype(int)
    )
    return base


def indicator_catalog(rules: dict[str, Any]) -> pd.DataFrame:
    """Catálogo de indicadores (dimensión ``dim_indicador``)."""
    rows = []
    for position, (code, indicator) in enumerate(CATALOG.items(), start=1):
        cfg = _cfg(rules, code)
        rows.append(
            {
                "indicador_key": position,
                "codigo": code,
                "nombre": indicator.nombre,
                "descripcion": indicator.descripcion,
                "peso": int(cfg.get("weight", 0)),
                "habilitado": bool(cfg.get("enabled", True)),
                "referencia": indicator.referencia,
            }
        )
    return pd.DataFrame(rows)
