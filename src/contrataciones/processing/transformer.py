"""Modelo dimensional (esquema estrella) para análisis y Power BI: capa gold.

Dimensiones:  dim_fecha, dim_entidad, dim_proveedor, dim_metodo, dim_categoria,
              dim_indicador.
Hechos:       fact_proceso (cabecera), fact_adjudicacion y fact_contrato
              (detalle), fact_postor, fact_sancion, fact_alerta.
Agregado:     agg_entidad_anio (KPIs precalculados por entidad y año).

Convenciones:
    ``*_key``  llave sustituta entera (para relaciones en Power BI y la BD).
    ``*_id``   llave natural de negocio (RUC, ocid, id de origen).
    ``*_pen``  monto expresado en soles.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from contrataciones.processing import risk_indicators as risk
from contrataciones.processing.cleaner import as_text, make_party_key, ruc_person_type
from contrataciones.utils.constants import (
    CATEGORY_LABELS,
    CONSORTIUM_TYPE,
    COUNTRY,
    DAY_NAMES,
    MONTH_NAMES,
    UNSPECIFIED,
)
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Utilidades
# =============================================================================
def assign_keys(df: pd.DataFrame, natural_key: str, key_name: str) -> pd.DataFrame:
    """Ordena por la llave natural y asigna una llave sustituta 1..n determinística."""
    result = df.sort_values(natural_key, kind="stable").reset_index(drop=True)
    result.insert(0, key_name, np.arange(1, len(result) + 1, dtype="int64"))
    return result


def date_key(series: pd.Series) -> pd.Series:
    """Fecha -> entero AAAAMMDD (``Int64``, nulo si no hay fecha)."""
    values = pd.to_datetime(series, errors="coerce")
    key = values.dt.year * 10000 + values.dt.month * 100 + values.dt.day
    return key.astype("Int64")


def _mode(series: pd.Series) -> Any:
    values = series.dropna()
    if values.empty:
        return None
    return values.value_counts().index[0]


def _lookup(keys: pd.Series, dim: pd.DataFrame, natural: str, surrogate: str) -> pd.Series:
    mapping = dim.set_index(natural)[surrogate]
    return keys.map(mapping).astype("Int64")


# =============================================================================
# Dimensiones
# =============================================================================
def build_dim_fecha(dates: Iterable[pd.Series]) -> pd.DataFrame:
    """Calendario continuo que cubre años completos de todas las fechas recibidas."""
    values = pd.concat(
        [pd.to_datetime(s, errors="coerce") for s in dates], ignore_index=True
    ).dropna()
    if values.empty:
        today = pd.Timestamp(date.today())
        start, end = pd.Timestamp(today.year, 1, 1), pd.Timestamp(today.year, 12, 31)
    else:
        start = pd.Timestamp(values.min().year, 1, 1)
        end = pd.Timestamp(values.max().year, 12, 31)
    days = pd.date_range(start, end, freq="D")
    frame = pd.DataFrame({"fecha": days})
    frame.insert(0, "fecha_key", date_key(frame["fecha"]).astype("int64"))
    frame["anio"] = days.year
    frame["semestre"] = np.where(days.month <= 6, 1, 2)
    frame["trimestre"] = days.quarter
    frame["mes"] = days.month
    frame["nombre_mes"] = [MONTH_NAMES[m - 1] for m in days.month]
    frame["anio_mes"] = days.strftime("%Y-%m")
    frame["semana_iso"] = days.isocalendar().week.to_numpy().astype("int64")
    frame["dia"] = days.day
    frame["dia_semana"] = days.dayofweek + 1
    frame["nombre_dia"] = [DAY_NAMES[d] for d in days.dayofweek]
    frame["es_fin_de_semana"] = days.dayofweek >= 5
    return frame


def build_dim_categoria(procesos: pd.DataFrame) -> pd.DataFrame:
    known = list(CATEGORY_LABELS) + ["unspecified"]
    present = [c for c in procesos["categoria_ocds"].dropna().unique() if c not in known]
    codes = known + sorted(present)
    frame = pd.DataFrame(
        {
            "categoria_ocds": codes,
            "categoria": [CATEGORY_LABELS.get(code, UNSPECIFIED) for code in codes],
        }
    )
    frame.insert(0, "categoria_key", np.arange(1, len(frame) + 1, dtype="int64"))
    return frame


def build_dim_metodo(procesos: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        procesos.groupby("metodo_detalle", dropna=False)
        .agg(
            metodo_ocds=("metodo_ocds", _mode),
            es_competitivo=("es_competitivo", lambda s: bool(s.mean() >= 0.5)),
            es_contratacion_directa=("es_contratacion_directa", lambda s: bool(s.mean() >= 0.5)),
        )
        .reset_index()
    )
    grouped["metodo_detalle"] = grouped["metodo_detalle"].fillna(UNSPECIFIED)
    return assign_keys(grouped, "metodo_detalle", "metodo_key")


def resolve_entities(procesos: pd.DataFrame, partes: pd.DataFrame) -> pd.DataFrame:
    """Une cada proceso con la parte compradora para obtener RUC y departamento."""
    buyers = partes[partes["es_comprador"]].drop_duplicates(["ocid", "party_id"])
    by_id = procesos[["ocid", "entidad_id_origen"]].merge(
        buyers[["ocid", "party_id", "ruc", "ruc_valido", "departamento", "nombre"]],
        left_on=["ocid", "entidad_id_origen"],
        right_on=["ocid", "party_id"],
        how="left",
    )
    first_buyer = buyers.drop_duplicates("ocid").set_index("ocid")
    for column in ("ruc", "ruc_valido", "departamento", "nombre"):
        fallback = by_id["ocid"].map(first_buyer[column]) if not first_buyer.empty else None
        if fallback is not None:
            by_id[column] = by_id[column].where(by_id[column].notna(), fallback)
    by_id["ruc_valido"] = by_id["ruc_valido"].fillna(False).astype(bool)
    resolved = procesos.merge(
        by_id[["ocid", "ruc", "ruc_valido", "departamento", "nombre"]].drop_duplicates("ocid"),
        on="ocid",
        how="left",
    ).rename(
        columns={
            "ruc": "entidad_ruc",
            "ruc_valido": "entidad_ruc_valido",
            "departamento": "entidad_departamento",
            "nombre": "entidad_nombre_parte",
        }
    )
    resolved["entidad_ruc_valido"] = resolved["entidad_ruc_valido"].fillna(False).astype(bool)
    resolved["entidad_nombre"] = resolved["entidad_nombre_origen"].fillna(
        resolved["entidad_nombre_parte"]
    )
    resolved["entidad_id"] = make_party_key(
        resolved["entidad_ruc"],
        resolved["entidad_ruc_valido"],
        resolved["entidad_id_origen"],
        resolved["entidad_nombre"],
    )
    return resolved


def build_dim_entidad(procesos: pd.DataFrame) -> pd.DataFrame:
    """Una fila por entidad compradora (llave natural: RUC válido o id de origen)."""
    data = procesos[procesos["entidad_id"].notna()]
    grouped = (
        data.groupby("entidad_id")
        .agg(
            ruc=("entidad_ruc", _mode),
            nombre=("entidad_nombre", _mode),
            departamento=("entidad_departamento", _mode),
        )
        .reset_index()
    )
    grouped["ruc"] = grouped["ruc"].where(grouped["entidad_id"].eq(grouped["ruc"]))
    grouped["nombre"] = grouped["nombre"].fillna(grouped["entidad_id"])
    grouped["pais"] = COUNTRY
    return assign_keys(grouped, "entidad_id", "entidad_key")


def build_dim_proveedor(
    postores: pd.DataFrame,
    adjudicaciones: pd.DataFrame,
    partes: pd.DataFrame,
    sanciones: pd.DataFrame,
) -> pd.DataFrame:
    """Proveedores (postores, adjudicados y sancionados) con atributos consolidados."""
    frames = [
        postores[["proveedor_id", "ruc", "ruc_valido", "nombre"]],
        adjudicaciones[["proveedor_id", "ruc", "ruc_valido", "nombre"]],
    ]
    if sanciones is not None and not sanciones.empty:
        frames.append(
            sanciones.loc[
                sanciones["proveedor_id"].notna(), ["proveedor_id", "ruc", "ruc_valido", "nombre"]
            ]
        )
    people = pd.concat(frames, ignore_index=True)
    people = people[people["proveedor_id"].notna()]
    # Departamento según la dirección publicada en "parties" (misma llave que el proveedor).
    parties = partes[partes["es_postor"] | partes["es_proveedor"]]
    parties = parties.assign(
        proveedor_id=make_party_key(
            parties["ruc"], parties["ruc_valido"], parties["party_id"], parties["nombre"]
        )
    ).dropna(subset=["proveedor_id", "departamento"])
    region_by_supplier = parties.groupby("proveedor_id")["departamento"].agg(_mode)

    grouped = (
        people.groupby("proveedor_id")
        .agg(ruc=("ruc", _mode), ruc_valido=("ruc_valido", "max"), nombre=("nombre", _mode))
        .reset_index()
    )
    grouped["ruc_valido"] = grouped["ruc_valido"].fillna(False).astype(bool)
    grouped["ruc"] = grouped["ruc"].where(grouped["ruc_valido"])
    grouped["nombre"] = grouped["nombre"].fillna(grouped["proveedor_id"])
    grouped["tipo_persona"] = ruc_person_type(grouped["ruc"]).where(
        grouped["ruc_valido"], UNSPECIFIED
    )
    is_consortium = ~grouped["ruc_valido"] & as_text(grouped["nombre"]).fillna("").str.startswith(
        "CONSORCIO"
    )
    grouped.loc[is_consortium, "tipo_persona"] = CONSORTIUM_TYPE
    grouped["departamento"] = grouped["proveedor_id"].map(region_by_supplier)

    if sanciones is not None and not sanciones.empty:
        counts = sanciones.dropna(subset=["proveedor_id"]).groupby("proveedor_id").size()
        grouped["n_sanciones"] = grouped["proveedor_id"].map(counts).fillna(0).astype(int)
    else:
        grouped["n_sanciones"] = 0
    grouped["tiene_sancion"] = grouped["n_sanciones"] > 0
    columns = [
        "proveedor_id",
        "ruc",
        "ruc_valido",
        "nombre",
        "tipo_persona",
        "departamento",
        "tiene_sancion",
        "n_sanciones",
    ]
    return assign_keys(grouped[columns], "proveedor_id", "proveedor_key")


# =============================================================================
# Hechos
# =============================================================================
def _award_totals(adjudicaciones: pd.DataFrame) -> pd.DataFrame:
    valid = adjudicaciones[adjudicaciones["es_valida"]]
    return (
        valid.groupby("ocid")
        .agg(
            n_adjudicaciones=("award_id", "nunique"),
            monto_adjudicado_pen=("monto_asignado_pen", lambda s: s.sum(min_count=1)),
        )
        .reset_index()
    )


def _bidder_counts(postores: pd.DataFrame, procesos: pd.DataFrame) -> pd.Series:
    listed = postores.groupby("ocid")["proveedor_id"].nunique()
    counted = procesos["ocid"].map(listed)
    return counted.fillna(procesos["n_postores_declarado"].astype("float64")).astype("Int64")


def build_gold(
    silver: dict[str, pd.DataFrame],
    rules: dict[str, Any],
    cutoff_date: date | None = None,
) -> dict[str, pd.DataFrame]:
    """Construye todas las tablas gold a partir de la capa silver."""
    cutoff = pd.Timestamp(cutoff_date or date.today())
    partes = silver["partes"]
    postores = silver["postores"]
    adjudicaciones = silver["adjudicaciones"].copy()
    contratos = silver["contratos"].copy()
    sanciones = silver.get("sanciones")
    if sanciones is None:
        sanciones = pd.DataFrame(columns=["proveedor_id", "ruc", "ruc_valido", "nombre"])
    # Si no se ejecutó la conversión de moneda, los montos *_pen son los originales.
    if "monto_pen" not in adjudicaciones:
        adjudicaciones["monto_pen"] = adjudicaciones["monto"]
    if "monto_asignado_pen" not in adjudicaciones:
        adjudicaciones["monto_asignado_pen"] = adjudicaciones["monto_asignado"]
    if "monto_pen" not in contratos:
        contratos["monto_pen"] = contratos["monto"]

    # --- procesos enriquecidos --------------------------------------------------
    procesos = resolve_entities(silver["procesos"], partes)
    if "valor_referencial_pen" not in procesos:
        procesos["valor_referencial_pen"] = procesos["valor_referencial"]
    procesos["n_postores"] = _bidder_counts(postores, procesos)
    procesos = procesos.merge(_award_totals(adjudicaciones), on="ocid", how="left")
    procesos["n_adjudicaciones"] = procesos["n_adjudicaciones"].fillna(0).astype(int)
    reference = procesos["valor_referencial_pen"]
    ratio = procesos["monto_adjudicado_pen"] / reference.where(reference > 0)
    procesos["ratio_adjudicado_referencial"] = ratio.replace([np.inf, -np.inf], np.nan).round(6)

    # --- dimensiones ----------------------------------------------------------
    dim_entidad = build_dim_entidad(procesos)
    dim_proveedor = build_dim_proveedor(postores, adjudicaciones, partes, sanciones)
    dim_metodo = build_dim_metodo(procesos)
    dim_categoria = build_dim_categoria(procesos)
    dim_indicador = risk.indicator_catalog(rules)

    # --- indicadores de riesgo -------------------------------------------------
    entity_year = procesos.set_index("ocid")[["entidad_id", "anio"]]
    adjudicaciones["entidad_id"] = adjudicaciones["ocid"].map(entity_year["entidad_id"])
    adjudicaciones["anio"] = adjudicaciones["ocid"].map(entity_year["anio"]).astype("Int64")
    flags = risk.compute_flags(procesos, adjudicaciones, sanciones, rules)
    scores = risk.score_processes(procesos["ocid"], flags, rules)
    procesos = procesos.merge(scores, on="ocid", how="left")

    # --- fact_proceso --------------------------------------------------------------
    procesos = assign_keys(procesos, "ocid", "proceso_key")
    procesos["entidad_key"] = _lookup(
        procesos["entidad_id"], dim_entidad, "entidad_id", "entidad_key"
    )
    procesos["metodo_key"] = _lookup(
        procesos["metodo_detalle"].fillna(UNSPECIFIED), dim_metodo, "metodo_detalle", "metodo_key"
    )
    procesos["categoria_key"] = _lookup(
        procesos["categoria_ocds"], dim_categoria, "categoria_ocds", "categoria_key"
    )
    procesos["fecha_convocatoria_key"] = date_key(procesos["fecha_publicacion"])
    fact_proceso = procesos[
        [
            "proceso_key",
            "ocid",
            "nomenclatura",
            "descripcion",
            "entidad_key",
            "metodo_key",
            "categoria_key",
            "fecha_convocatoria_key",
            "estado",
            "moneda",
            "valor_referencial",
            "valor_referencial_pen",
            "n_postores",
            "plazo_presentacion_dias",
            "plazo_consultas_dias",
            "n_adjudicaciones",
            "monto_adjudicado_pen",
            "ratio_adjudicado_referencial",
            "n_alertas",
            "puntaje_riesgo",
            "nivel_riesgo",
            "nivel_riesgo_orden",
        ]
    ].copy()
    proceso_keys = fact_proceso.set_index("ocid")["proceso_key"]

    # --- fact_adjudicacion -----------------------------------------------------------
    adjudicaciones["proveedor_inhabilitado"] = risk.sanctioned_award_mask(
        adjudicaciones, sanciones, risk.sanction_keywords(rules)
    )
    # Los registros sin proceso conocido (huérfanos) se excluyen del modelo;
    # quedan contabilizados en el reporte de calidad.
    known = set(proceso_keys.index)
    adj = adjudicaciones[adjudicaciones["ocid"].isin(known)]
    adj = adj.sort_values(["ocid", "award_id", "proveedor_id"], na_position="last")
    adj = adj.reset_index(drop=True)
    fact_adjudicacion = pd.DataFrame(
        {
            "adjudicacion_key": np.arange(1, len(adj) + 1, dtype="int64"),
            "proceso_key": adj["ocid"].map(proceso_keys).astype("Int64"),
            "ocid": adj["ocid"],
            "award_id": adj["award_id"],
            "proveedor_key": _lookup(
                adj["proveedor_id"], dim_proveedor, "proveedor_id", "proveedor_key"
            ),
            "entidad_key": _lookup(adj["entidad_id"], dim_entidad, "entidad_id", "entidad_key"),
            "fecha_adjudicacion_key": date_key(adj["fecha_adjudicacion"]),
            "estado": adj["estado"],
            "moneda": adj["moneda"],
            "monto_adjudicado": adj["monto"],
            "monto_adjudicado_pen": adj["monto_pen"],
            "n_proveedores_adjudicacion": adj["n_proveedores_adjudicacion"],
            "monto_asignado_pen": adj["monto_asignado_pen"],
            "es_valida": adj["es_valida"].astype(bool),
            "proveedor_inhabilitado": adj["proveedor_inhabilitado"].astype(bool),
        }
    )

    # --- fact_contrato ---------------------------------------------------------------
    award_ids = set(zip(adjudicaciones["ocid"], adjudicaciones["award_id"], strict=True))
    con = contratos[contratos["ocid"].isin(known)]
    con = con.sort_values(["ocid", "contract_id"]).reset_index(drop=True)
    fact_contrato = pd.DataFrame(
        {
            "contrato_key": np.arange(1, len(con) + 1, dtype="int64"),
            "proceso_key": con["ocid"].map(proceso_keys).astype("Int64"),
            "ocid": con["ocid"],
            "contract_id": con["contract_id"],
            "award_id": con["award_id"],
            "entidad_key": _lookup(
                con["ocid"].map(entity_year["entidad_id"]), dim_entidad, "entidad_id", "entidad_key"
            ),
            "fecha_firma_key": date_key(con["fecha_firma"]),
            "estado": con["estado"],
            "moneda": con["moneda"],
            "monto_contrato": con["monto"],
            "monto_contrato_pen": con["monto_pen"],
            "fecha_inicio": con["fecha_inicio"].dt.normalize(),
            "fecha_fin": con["fecha_fin"].dt.normalize(),
            "duracion_dias": con["duracion_dias"],
            "tiene_adjudicacion_vinculada": [
                (o, a) in award_ids for o, a in zip(con["ocid"], con["award_id"], strict=True)
            ],
        }
    )

    # --- fact_postor -------------------------------------------------------------------
    winners = set(
        zip(
            adjudicaciones.loc[adjudicaciones["es_valida"], "ocid"],
            adjudicaciones.loc[adjudicaciones["es_valida"], "proveedor_id"],
            strict=True,
        )
    )
    pos = postores[postores["ocid"].isin(known)]
    pos = pos.sort_values(["ocid", "proveedor_id"]).reset_index(drop=True)
    fact_postor = pd.DataFrame(
        {
            "postor_key": np.arange(1, len(pos) + 1, dtype="int64"),
            "proceso_key": pos["ocid"].map(proceso_keys).astype("Int64"),
            "proveedor_key": _lookup(
                pos["proveedor_id"], dim_proveedor, "proveedor_id", "proveedor_key"
            ),
            "ocid": pos["ocid"],
            "es_ganador": [
                (o, p) in winners for o, p in zip(pos["ocid"], pos["proveedor_id"], strict=True)
            ],
        }
    )

    # --- fact_sancion -------------------------------------------------------------------
    if not sanciones.empty and "fecha_inicio" in sanciones:
        san = sanciones.sort_values(["ruc", "fecha_inicio"]).reset_index(drop=True)
        vigente = (san["fecha_inicio"] <= cutoff) & (
            san["fecha_fin"].isna() | (san["fecha_fin"] >= cutoff)
        )
        fact_sancion = pd.DataFrame(
            {
                "sancion_key": np.arange(1, len(san) + 1, dtype="int64"),
                "proveedor_key": _lookup(
                    san["proveedor_id"], dim_proveedor, "proveedor_id", "proveedor_key"
                ),
                "ruc": san["ruc"],
                "tipo_sancion": san["tipo_sancion"],
                "fecha_inicio": san["fecha_inicio"],
                "fecha_fin": san["fecha_fin"],
                "es_definitiva": san["es_definitiva"].astype(bool),
                "vigente_a_fecha_corte": vigente.astype(bool),
                "resolucion": san["resolucion"],
                "motivo": san["motivo"],
            }
        )
    else:
        fact_sancion = pd.DataFrame(
            columns=[
                "sancion_key",
                "proveedor_key",
                "ruc",
                "tipo_sancion",
                "fecha_inicio",
                "fecha_fin",
                "es_definitiva",
                "vigente_a_fecha_corte",
                "resolucion",
                "motivo",
            ]
        )

    # --- fact_alerta -------------------------------------------------------------------
    alerts = flags.sort_values(["ocid", "codigo"]).reset_index(drop=True)
    indicator_keys = dim_indicador.set_index("codigo")["indicador_key"]
    fact_alerta = pd.DataFrame(
        {
            "alerta_key": np.arange(1, len(alerts) + 1, dtype="int64"),
            "proceso_key": alerts["ocid"].map(proceso_keys).astype("Int64"),
            "indicador_key": alerts["codigo"].map(indicator_keys).astype("Int64"),
            "ocid": alerts["ocid"],
            "codigo": alerts["codigo"],
            "detalle": alerts["detalle"],
        }
    )

    # --- agregado entidad-año --------------------------------------------------------
    agg = build_entity_year(procesos, adjudicaciones, dim_entidad)

    # --- dimensión fecha ----------------------------------------------------------------
    dim_fecha = build_dim_fecha(
        [
            procesos["fecha_publicacion"],
            adjudicaciones["fecha_adjudicacion"],
            contratos["fecha_firma"],
        ]
    )

    gold = {
        "dim_fecha": dim_fecha,
        "dim_entidad": dim_entidad,
        "dim_proveedor": dim_proveedor,
        "dim_metodo": dim_metodo,
        "dim_categoria": dim_categoria,
        "dim_indicador": dim_indicador,
        "fact_proceso": fact_proceso,
        "fact_adjudicacion": fact_adjudicacion,
        "fact_contrato": fact_contrato,
        "fact_postor": fact_postor,
        "fact_sancion": fact_sancion,
        "fact_alerta": fact_alerta,
        "agg_entidad_anio": agg,
    }
    for name, frame in gold.items():
        logger.info("Gold %-18s %8d filas", name, len(frame))
    return gold


def build_entity_year(
    procesos: pd.DataFrame, adjudicaciones: pd.DataFrame, dim_entidad: pd.DataFrame
) -> pd.DataFrame:
    """KPIs por entidad y año: competencia, monto, proveedores y concentración (HHI)."""
    base = procesos[procesos["entidad_id"].notna() & procesos["anio"].notna()].copy()
    base["postor_unico"] = base["es_competitivo"] & base["n_postores"].eq(1).fillna(False)
    base["riesgo_alto"] = base["nivel_riesgo"].eq("Alto")
    grouped = (
        base.groupby(["entidad_id", "anio"])
        .agg(
            n_procesos=("ocid", "nunique"),
            n_procesos_competitivos=("es_competitivo", "sum"),
            n_postor_unico=("postor_unico", "sum"),
            monto_adjudicado_pen=("monto_adjudicado_pen", lambda s: s.sum(min_count=1)),
            n_alertas=("n_alertas", "sum"),
            n_procesos_riesgo_alto=("riesgo_alto", "sum"),
        )
        .reset_index()
    )
    competitive = grouped["n_procesos_competitivos"].where(grouped["n_procesos_competitivos"] > 0)
    grouped["pct_postor_unico"] = (
        (grouped["n_postor_unico"] / competitive).astype("float64").round(4)
    )
    shares = risk.supplier_shares(adjudicaciones)
    if shares.empty:
        grouped["n_proveedores"] = 0
        grouped["hhi"] = np.nan
    else:
        shares = shares.assign(anio=shares["anio"].astype("Int64"))
        suppliers = (
            shares.groupby(["entidad_id", "anio"])["proveedor_id"]
            .nunique()
            .rename("n_proveedores")
            .reset_index()
        )
        hhi = risk.herfindahl_index(shares)
        grouped = grouped.merge(suppliers, on=["entidad_id", "anio"], how="left")
        grouped = grouped.merge(hhi, on=["entidad_id", "anio"], how="left")
        grouped["n_proveedores"] = grouped["n_proveedores"].fillna(0).astype(int)
    grouped["hhi"] = grouped["hhi"].astype("float64").round(2)
    grouped["entidad_key"] = _lookup(
        grouped["entidad_id"], dim_entidad, "entidad_id", "entidad_key"
    )
    for column in (
        "n_procesos_competitivos",
        "n_postor_unico",
        "n_alertas",
        "n_procesos_riesgo_alto",
    ):
        grouped[column] = grouped[column].astype(int)
    grouped["anio"] = grouped["anio"].astype(int)
    columns = [
        "entidad_key",
        "anio",
        "n_procesos",
        "n_procesos_competitivos",
        "n_postor_unico",
        "pct_postor_unico",
        "monto_adjudicado_pen",
        "n_proveedores",
        "hhi",
        "n_alertas",
        "n_procesos_riesgo_alto",
    ]
    return grouped[columns].sort_values(["entidad_key", "anio"]).reset_index(drop=True)


def entity_label(dim_entidad: pd.DataFrame) -> pd.Series:
    """Etiqueta legible 'NOMBRE (RUC)' para reportes."""
    ruc = as_text(dim_entidad["ruc"]).fillna("sin RUC")
    return dim_entidad["nombre"].astype(str) + " (" + ruc + ")"
