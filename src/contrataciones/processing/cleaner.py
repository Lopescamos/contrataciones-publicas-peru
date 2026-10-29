"""Limpieza de datos: funciones genéricas y reglas del dominio de contrataciones.

Funciones genéricas (reutilizables en cualquier proyecto):
    as_text, clean_name, remove_duplicates, handle_nulls, standardize_text,
    fix_dtypes, flag_outliers_iqr, parse_datetime, parse_date_flexible, to_number.

Funciones de dominio (contrataciones del Perú):
    extract_ruc, is_valid_ruc, ruc_person_type, normalize_departamento y
    clean_procesos / clean_partes / clean_postores / clean_adjudicaciones /
    clean_contratos / clean_sanciones, que producen la capa silver.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from contrataciones.utils.constants import (
    CATEGORY_LABELS,
    DEPARTAMENTO_ALIASES,
    DEPARTAMENTOS,
    RUC_CHECK_WEIGHTS,
    RUC_LENGTH,
    RUC_OTHER_TYPE,
    RUC_PERSON_TYPES,
    RUC_VALID_PREFIXES,
    TIMEZONE,
    UNSPECIFIED,
)
from contrataciones.utils.helpers import is_missing
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

_TZ_SUFFIX = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")
_RUC_PATTERN = r"(?<!\d)(\d{11})(?!\d)"


# =============================================================================
# Texto
# =============================================================================
def strip_accents(text: str) -> str:
    """Quita tildes y diacríticos: 'Áncash' -> 'Ancash'."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_key(value: Any) -> str | None:
    """Clave de comparación: MAYÚSCULAS, sin tildes ni signos, espacios simples."""
    if is_missing(value):
        return None
    text = strip_accents(str(value)).upper()
    text = re.sub(r"[^0-9A-Z]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def as_text(series: pd.Series) -> pd.Series:
    """Convierte una serie a texto conservando los vacíos como nulos."""
    if isinstance(series.dtype, pd.StringDtype):
        return series
    return series.map(lambda v: None if is_missing(v) else str(v)).astype(object)


def clean_name(series: pd.Series, upper: bool = True) -> pd.Series:
    """Limpia nombres: espacios extra, comillas, mayúsculas y vacíos -> nulo."""
    text = as_text(series).str.strip().str.replace(r"\s+", " ", regex=True)
    text = text.str.strip("\"'").str.strip()
    if upper:
        text = text.str.upper()
    return text.mask(text.eq(""))


def standardize_text(df: pd.DataFrame, columns: Iterable[str], upper: bool = True) -> pd.DataFrame:
    """Aplica :func:`clean_name` a varias columnas."""
    result = df.copy()
    for column in columns:
        result[column] = clean_name(result[column], upper=upper)
    return result


# =============================================================================
# Genéricas
# =============================================================================
def remove_duplicates(
    df: pd.DataFrame, subset: list[str] | None = None, keep: str = "first"
) -> tuple[pd.DataFrame, int]:
    """Elimina duplicados y devuelve ``(df_limpio, filas_eliminadas)``."""
    before = len(df)
    result = df.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)
    return result, before - len(result)


def handle_nulls(
    df: pd.DataFrame,
    strategy: str,
    columns: list[str] | None = None,
    fill_value: Any = None,
) -> pd.DataFrame:
    """Trata nulos con una estrategia: drop, fill_value, fill_mean, fill_median, fill_mode."""
    result = df.copy()
    columns = columns or list(result.columns)
    if strategy == "drop":
        return result.dropna(subset=columns).reset_index(drop=True)
    for column in columns:
        if strategy == "fill_value":
            result[column] = result[column].fillna(fill_value)
        elif strategy == "fill_mean":
            result[column] = result[column].fillna(result[column].mean())
        elif strategy == "fill_median":
            result[column] = result[column].fillna(result[column].median())
        elif strategy == "fill_mode":
            mode = result[column].mode(dropna=True)
            if not mode.empty:
                result[column] = result[column].fillna(mode.iloc[0])
        else:
            raise ValueError(f"Estrategia de nulos desconocida: {strategy}")
    return result


def to_number(series: pd.Series) -> pd.Series:
    """Convierte a número decimal (los valores no numéricos quedan como NaN)."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return series.astype("float64")
    text = as_text(series).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(text, errors="coerce").astype("float64")


def to_int(series: pd.Series) -> pd.Series:
    """Convierte a entero con soporte de nulos (``Int64``)."""
    return to_number(series).round().astype("Int64")


def parse_datetime(series: pd.Series, timezone: str = TIMEZONE) -> pd.Series:
    """Fechas ISO 8601 -> datetime local de Lima sin zona horaria.

    Las fechas con zona (``2024-08-03T18:00:00-05:00`` o ``...Z``) se convierten
    a la hora de Lima; las fechas sin zona se interpretan como hora local.
    """
    text = as_text(series)
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    has_zone = text.str.contains(_TZ_SUFFIX, regex=True, na=False)
    if has_zone.any():
        aware = pd.to_datetime(text[has_zone], errors="coerce", utc=True, format="ISO8601")
        result.loc[has_zone] = (
            aware.dt.tz_convert(timezone).dt.tz_localize(None).astype("datetime64[ns]")
        )
    naive = ~has_zone & text.notna()
    if naive.any():
        parsed = pd.to_datetime(text[naive], errors="coerce", format="ISO8601")
        result.loc[naive] = parsed.astype("datetime64[ns]")
    return result


def parse_date_flexible(series: pd.Series, dayfirst: bool = True) -> pd.Series:
    """Fechas en formatos mixtos (ISO, dd/mm/aaaa, número de serie de Excel) -> datetime."""
    if pd.api.types.is_datetime64_any_dtype(series):
        values = series.dt.tz_localize(None) if series.dt.tz is not None else series
        return values.astype("datetime64[ns]").dt.normalize()
    text = as_text(series).str.strip()
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    iso = text.str.match(r"^\d{4}-\d{2}-\d{2}", na=False)
    if iso.any():
        result.loc[iso] = pd.to_datetime(text[iso].str[:10], errors="coerce", format="%Y-%m-%d")
    slash = text.str.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{4}", na=False) & ~iso
    if slash.any():
        cleaned = text[slash].str.replace("-", "/", regex=False).str.split(" ").str[0]
        fmt = "%d/%m/%Y" if dayfirst else "%m/%d/%Y"
        result.loc[slash] = pd.to_datetime(cleaned, errors="coerce", format=fmt)
    serial = text.str.fullmatch(r"\d{5}(\.0+)?", na=False) & ~iso & ~slash
    if serial.any():
        days = pd.to_numeric(text[serial], errors="coerce")
        result.loc[serial] = pd.Timestamp("1899-12-30") + pd.to_timedelta(days, unit="D")
    rest = text.notna() & ~iso & ~slash & ~serial
    if rest.any():
        result.loc[rest] = pd.to_datetime(
            text[rest], errors="coerce", dayfirst=dayfirst, format="mixed"
        )
    return result.dt.normalize()


def fix_dtypes(df: pd.DataFrame, schema: Mapping[str, str]) -> pd.DataFrame:
    """Aplica tipos declarativos: ``str | float | int | datetime | date | bool``."""
    result = df.copy()
    for column, kind in schema.items():
        if column not in result.columns:
            continue
        if kind == "str":
            result[column] = as_text(result[column])
        elif kind == "float":
            result[column] = to_number(result[column])
        elif kind == "int":
            result[column] = to_int(result[column])
        elif kind == "datetime":
            result[column] = parse_datetime(result[column])
        elif kind == "date":
            result[column] = parse_date_flexible(result[column])
        elif kind == "bool":
            result[column] = result[column].fillna(False).astype(bool)
        else:
            raise ValueError(f"Tipo no soportado en fix_dtypes: {kind}")
    return result


def flag_outliers_iqr(series: pd.Series, k: float = 3.0) -> pd.Series:
    """Marca valores atípicos por rango intercuartílico (no los elimina)."""
    values = to_number(series)
    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    iqr = q3 - q1
    if pd.isna(iqr) or iqr == 0:
        return pd.Series(False, index=series.index)
    return ((values < q1 - k * iqr) | (values > q3 + k * iqr)).fillna(False)


# =============================================================================
# RUC y departamentos
# =============================================================================
def is_valid_ruc(value: Any) -> bool:
    """Valida un RUC: 11 dígitos, prefijo válido y dígito verificador (módulo 11).

    >>> is_valid_ruc("20131312955")  # RUC de la SUNAT
    True
    >>> is_valid_ruc("20131312954")
    False
    """
    if is_missing(value):
        return False
    text = str(value).strip()
    if len(text) != RUC_LENGTH or not text.isdigit() or text[:2] not in RUC_VALID_PREFIXES:
        return False
    total = sum(
        int(digit) * weight for digit, weight in zip(text[:10], RUC_CHECK_WEIGHTS, strict=True)
    )
    check = 11 - (total % 11)
    if check == 10:
        check = 0
    elif check == 11:
        check = 1
    return check == int(text[10])


def extract_ruc(series: pd.Series) -> pd.Series:
    """Extrae el primer número de 11 dígitos (p. ej. de ``PE-RUC-20131312955``)."""
    return as_text(series).str.extract(_RUC_PATTERN, expand=False)


def valid_ruc_mask(series: pd.Series) -> pd.Series:
    """Serie booleana: True si el RUC es válido."""
    cache = {value: is_valid_ruc(value) for value in series.dropna().unique()}
    return series.map(cache).fillna(False).astype(bool)


def ruc_person_type(series: pd.Series) -> pd.Series:
    """Tipo de contribuyente según el prefijo del RUC (10 natural, 20 jurídica)."""
    prefix = as_text(series).str[:2]
    labels = prefix.map(RUC_PERSON_TYPES)
    return labels.where(prefix.isna() | labels.notna(), RUC_OTHER_TYPE)


def normalize_departamento(series: pd.Series) -> pd.Series:
    """Normaliza nombres de región/departamento al nombre oficial con tildes."""
    cache: dict[Any, Any] = {}
    for value in series.dropna().unique():
        key = normalize_key(value)
        if key is None:
            cache[value] = None
            continue
        key = DEPARTAMENTO_ALIASES.get(key, key)
        if key not in DEPARTAMENTOS:
            if key.startswith("LIMA"):
                key = "LIMA"
            elif "CALLAO" in key:
                key = "CALLAO"
        cache[value] = DEPARTAMENTOS.get(key, str(value).strip().title())
    return series.map(cache).astype(object).where(series.notna(), None)


def make_party_key(
    ruc: pd.Series, ruc_ok: pd.Series, party_id: pd.Series, name: pd.Series
) -> pd.Series:
    """Llave natural de una organización: RUC válido > id de origen > nombre.

    En la publicación del OECE las entidades se identifican con códigos
    ``PE-CONSUCODE-<n>`` y los consorcios con códigos internos (no RUC); en esos
    casos se usa el id de origen tal cual.
    """
    by_id = as_text(party_id).str.strip().str.upper()
    by_name = "NOM-" + clean_name(name)
    key = by_id.where(by_id.notna() & by_id.ne(""), by_name)
    return ruc.where(ruc_ok, key)


# =============================================================================
# Dominio: capa silver
# =============================================================================
def _contains_any(series: pd.Series, keywords: Iterable[str]) -> pd.Series:
    keys = [normalize_key(k) for k in keywords if normalize_key(k)]
    if not keys:
        return pd.Series(False, index=series.index)
    normalized = series.map(normalize_key)
    pattern = "|".join(re.escape(k) for k in keys)
    return normalized.str.contains(pattern, regex=True, na=False)


def _column(df: pd.DataFrame, name: str) -> pd.Series:
    """Columna opcional: si no existe (staging de versiones previas), devuelve nulos."""
    if name in df.columns:
        return df[name]
    return pd.Series([None] * len(df), index=df.index, dtype=object)


def _positive_days(start: pd.Series, end: pd.Series) -> pd.Series:
    """Días enteros entre dos fechas; nulo si el periodo no es positivo.

    En la publicación del OECE ``tenderPeriod`` suele traer inicio = fin (solo la
    fecha de convocatoria): ese caso se trata como plazo no informado.
    """
    seconds = (end - start).dt.total_seconds()
    days = (seconds // 86400).astype("Int64")
    return days.where(seconds > 0)


def clean_procesos(
    raw: pd.DataFrame,
    competitive_methods: Iterable[str] = ("open", "selective"),
    non_competitive_keywords: Iterable[str] = ("DIRECTA",),
) -> pd.DataFrame:
    """Procesos de contratación limpios (un registro por ``ocid``)."""
    df = raw.copy()
    df = df[as_text(df["ocid"]).notna()]
    df["fecha_release"] = parse_datetime(df["release_date"])
    df = df.sort_values("fecha_release", na_position="first").drop_duplicates("ocid", keep="last")

    metodo_ocds = as_text(df["procurement_method"]).str.strip().str.lower()
    metodo_detalle = (
        as_text(df["procurement_method_details"]).str.strip().str.replace(r"\s+", " ", regex=True)
    )
    metodo_detalle = metodo_detalle.mask(metodo_detalle.eq("")).fillna(UNSPECIFIED)
    directa = _contains_any(metodo_detalle, non_competitive_keywords) | metodo_ocds.eq("direct")
    competitive = metodo_ocds.isin(list(competitive_methods)) | (
        metodo_ocds.isna() & metodo_detalle.ne(UNSPECIFIED)
    )

    out = pd.DataFrame(
        {
            "ocid": as_text(df["ocid"]).str.strip(),
            "nomenclatura": clean_name(df["tender_title"], upper=False),
            "descripcion": clean_name(df["tender_description"], upper=False),
            "estado": as_text(df["tender_status"]).str.strip().str.lower(),
            "metodo_ocds": metodo_ocds,
            "metodo_detalle": metodo_detalle,
            "es_competitivo": (competitive & ~directa).astype(bool),
            "es_contratacion_directa": directa.astype(bool),
            "categoria_ocds": as_text(df["main_category"]).str.strip(),
            "moneda": as_text(df["tender_value_currency"]).str.strip().str.upper(),
            "valor_referencial": to_number(df["tender_value_amount"]),
            "valor_referencial_pen_fuente": to_number(_column(df, "tender_value_amount_pen")),
            "fecha_inicio_presentacion": parse_datetime(df["tender_period_start"]),
            "fecha_fin_presentacion": parse_datetime(df["tender_period_end"]),
            "fecha_inicio_consultas": parse_datetime(_column(df, "enquiry_period_start")),
            "fecha_fin_consultas": parse_datetime(_column(df, "enquiry_period_end")),
            "n_postores_declarado": to_int(df["number_of_tenderers"]),
            "entidad_id_origen": as_text(df["buyer_id"]).str.strip(),
            "entidad_nombre_origen": clean_name(df["buyer_name"]),
            "fecha_release": df["fecha_release"],
        }
    )
    out["categoria_ocds"] = out["categoria_ocds"].fillna("unspecified")
    out["categoria"] = out["categoria_ocds"].map(CATEGORY_LABELS).fillna(UNSPECIFIED)
    published = parse_datetime(df["tender_date_published"])
    out["fecha_publicacion"] = published.fillna(out["fecha_inicio_presentacion"])
    out["plazo_presentacion_dias"] = _positive_days(
        out["fecha_inicio_presentacion"], out["fecha_fin_presentacion"]
    )
    out["plazo_consultas_dias"] = _positive_days(
        out["fecha_inicio_consultas"], out["fecha_fin_consultas"]
    )
    out["anio"] = out["fecha_publicacion"].dt.year.astype("Int64")
    for column in ("valor_referencial", "valor_referencial_pen_fuente"):
        out.loc[out[column].le(0).fillna(False), column] = np.nan
    columns = [
        "ocid",
        "nomenclatura",
        "descripcion",
        "estado",
        "metodo_ocds",
        "metodo_detalle",
        "es_competitivo",
        "es_contratacion_directa",
        "categoria_ocds",
        "categoria",
        "moneda",
        "valor_referencial",
        "valor_referencial_pen_fuente",
        "fecha_publicacion",
        "fecha_inicio_presentacion",
        "fecha_fin_presentacion",
        "plazo_presentacion_dias",
        "fecha_inicio_consultas",
        "fecha_fin_consultas",
        "plazo_consultas_dias",
        "anio",
        "n_postores_declarado",
        "entidad_id_origen",
        "entidad_nombre_origen",
        "fecha_release",
    ]
    return out[columns].reset_index(drop=True)


def clean_partes(raw: pd.DataFrame) -> pd.DataFrame:
    """Organizaciones por proceso con RUC validado y departamento normalizado."""
    df = raw[as_text(raw["ocid"]).notna()].copy()
    # RUC: identificador principal > identificador adicional PE-RUC > id de la parte.
    ruc = (
        extract_ruc(df["identifier_id"])
        .fillna(extract_ruc(_column(df, "additional_ruc")))
        .fillna(extract_ruc(df["party_id"]))
    )
    roles = as_text(df["roles"]).fillna("")
    out = pd.DataFrame(
        {
            "ocid": as_text(df["ocid"]).str.strip(),
            "party_id": as_text(df["party_id"]).str.strip(),
            "nombre": clean_name(df["party_name"]),
            "ruc": ruc,
            "roles": roles.mask(roles.eq("")),
            "es_comprador": roles.str.contains(r"buyer|procuringEntity", regex=True),
            "es_postor": roles.str.contains("tenderer", regex=False),
            "es_proveedor": roles.str.contains("supplier", regex=False),
            "departamento": normalize_departamento(df["region"]),
            "localidad": clean_name(df["locality"], upper=False),
        }
    )
    out["ruc_valido"] = valid_ruc_mask(out["ruc"])
    out, _ = remove_duplicates(out, subset=["ocid", "party_id", "nombre"])
    columns = [
        "ocid",
        "party_id",
        "nombre",
        "ruc",
        "ruc_valido",
        "roles",
        "es_comprador",
        "es_postor",
        "es_proveedor",
        "departamento",
        "localidad",
    ]
    return out[columns]


def _attach_party_ruc(df: pd.DataFrame, id_column: str, partes: pd.DataFrame) -> pd.Series:
    """RUC desde el propio id o, si no lo tiene, desde la tabla de partes."""
    own = extract_ruc(df[id_column])
    if partes is None or partes.empty:
        return own
    lookup = (
        partes.dropna(subset=["party_id", "ruc"])
        .drop_duplicates(["ocid", "party_id"])
        .set_index(["ocid", "party_id"])["ruc"]
    )
    keys = pd.MultiIndex.from_arrays([as_text(df["ocid"]), as_text(df[id_column])])
    from_parties = pd.Series(lookup.reindex(keys).to_numpy(), index=df.index)
    return own.fillna(from_parties)


def clean_postores(
    raw: pd.DataFrame, partes: pd.DataFrame | None = None
) -> tuple[pd.DataFrame, int]:
    """Postores por proceso, sin duplicados. Devuelve ``(df, duplicados_eliminados)``."""
    df = raw[as_text(raw["ocid"]).notna()].copy()
    ruc = _attach_party_ruc(df, "tenderer_id", partes)
    out = pd.DataFrame(
        {
            "ocid": as_text(df["ocid"]).str.strip(),
            "tenderer_id": as_text(df["tenderer_id"]).str.strip(),
            "nombre": clean_name(df["tenderer_name"]),
            "ruc": ruc,
        }
    )
    out["ruc_valido"] = valid_ruc_mask(out["ruc"])
    out["proveedor_id"] = make_party_key(
        out["ruc"], out["ruc_valido"], out["tenderer_id"], out["nombre"]
    )
    out = out[out["proveedor_id"].notna()]
    # Problema conocido de la fuente: postores con identificadores duplicados.
    out, removed = remove_duplicates(out, subset=["ocid", "proveedor_id"])
    return out, removed


def clean_adjudicaciones(
    raw: pd.DataFrame,
    partes: pd.DataFrame | None = None,
    invalid_status: Iterable[str] = ("cancelled", "unsuccessful"),
) -> pd.DataFrame:
    """Adjudicaciones por proveedor con montos prorrateados entre consorciados."""
    df = raw[as_text(raw["ocid"]).notna()].copy()
    ruc = _attach_party_ruc(df, "supplier_id", partes)
    out = pd.DataFrame(
        {
            "ocid": as_text(df["ocid"]).str.strip(),
            "award_id": as_text(df["award_id"]).str.strip().fillna("SIN_ID"),
            "estado": as_text(df["award_status"]).str.strip().str.lower(),
            "fecha_adjudicacion": parse_datetime(df["award_date"]),
            "moneda": as_text(df["award_value_currency"]).str.strip().str.upper(),
            "monto": to_number(df["award_value_amount"]),
            "monto_pen_fuente": to_number(_column(df, "award_value_amount_pen")),
            "supplier_id": as_text(df["supplier_id"]).str.strip(),
            "nombre": clean_name(df["supplier_name"]),
            "ruc": ruc,
            "n_proveedores_adjudicacion": to_int(df["n_suppliers"]),
        }
    )
    out["ruc_valido"] = valid_ruc_mask(out["ruc"])
    has_supplier = out["supplier_id"].notna() | out["nombre"].notna()
    out["proveedor_id"] = make_party_key(
        out["ruc"], out["ruc_valido"], out["supplier_id"], out["nombre"]
    )
    out["proveedor_id"] = out["proveedor_id"].where(has_supplier)
    divisor = out["n_proveedores_adjudicacion"].astype("float64").where(lambda s: s > 0, 1.0)
    out["monto_asignado"] = out["monto"] / divisor
    out["es_valida"] = ~out["estado"].isin(list(invalid_status))
    out, _ = remove_duplicates(out, subset=["ocid", "award_id", "proveedor_id"])
    columns = [
        "ocid",
        "award_id",
        "estado",
        "es_valida",
        "fecha_adjudicacion",
        "moneda",
        "monto",
        "monto_pen_fuente",
        "supplier_id",
        "nombre",
        "ruc",
        "ruc_valido",
        "proveedor_id",
        "n_proveedores_adjudicacion",
        "monto_asignado",
    ]
    return out[columns]


def clean_contratos(raw: pd.DataFrame) -> pd.DataFrame:
    """Contratos tipados; los contratos sin estado se marcan como ``sin_estado``."""
    df = raw[as_text(raw["ocid"]).notna()].copy()
    out = pd.DataFrame(
        {
            "ocid": as_text(df["ocid"]).str.strip(),
            "contract_id": as_text(df["contract_id"]).str.strip(),
            "award_id": as_text(df["award_id"]).str.strip(),
            "estado": as_text(df["contract_status"]).str.strip().str.lower().fillna("sin_estado"),
            "fecha_firma": parse_datetime(df["date_signed"]),
            "moneda": as_text(df["contract_value_currency"]).str.strip().str.upper(),
            "monto": to_number(df["contract_value_amount"]),
            "monto_pen_fuente": to_number(_column(df, "contract_value_amount_pen")),
            "fecha_inicio": parse_datetime(df["period_start"]),
            "fecha_fin": parse_datetime(df["period_end"]),
        }
    )
    delta = out["fecha_fin"] - out["fecha_inicio"]
    out["duracion_dias"] = (delta.dt.total_seconds() // 86400).astype("Int64")
    out["contract_id"] = out["contract_id"].fillna("SIN_ID")
    out, _ = remove_duplicates(out, subset=["ocid", "contract_id"])
    return out


def clean_sanciones(mapped: pd.DataFrame) -> pd.DataFrame:
    """Sanciones del Tribunal ya mapeadas a columnas canónicas (ver sources.yaml)."""
    df = mapped.copy()
    ruc = extract_ruc(df["ruc"])
    out = pd.DataFrame(
        {
            "ruc": ruc,
            "nombre": clean_name(df["nombre"]) if "nombre" in df else None,
            "tipo_sancion": clean_name(df["tipo_sancion"]) if "tipo_sancion" in df else None,
            "fecha_inicio": parse_date_flexible(df["fecha_inicio"]),
            "fecha_fin": parse_date_flexible(df["fecha_fin"]) if "fecha_fin" in df else pd.NaT,
            "resolucion": clean_name(df["resolucion"]) if "resolucion" in df else None,
            "motivo": clean_name(df["motivo"], upper=False) if "motivo" in df else None,
        }
    )
    out["ruc_valido"] = valid_ruc_mask(out["ruc"])
    tipo = out["tipo_sancion"].fillna("")
    out["es_definitiva"] = out["fecha_fin"].isna() | tipo.str.contains("DEFINITIV", na=False)
    out["proveedor_id"] = out["ruc"].where(out["ruc_valido"])
    out = out[out["ruc"].notna()]
    out, _ = remove_duplicates(out, subset=["ruc", "fecha_inicio", "fecha_fin", "resolucion"])
    columns = [
        "proveedor_id",
        "ruc",
        "ruc_valido",
        "nombre",
        "tipo_sancion",
        "fecha_inicio",
        "fecha_fin",
        "es_definitiva",
        "resolucion",
        "motivo",
    ]
    return out[columns]


EMPTY_SANCIONES = pd.DataFrame(
    {
        "proveedor_id": pd.Series(dtype=object),
        "ruc": pd.Series(dtype=object),
        "ruc_valido": pd.Series(dtype=bool),
        "nombre": pd.Series(dtype=object),
        "tipo_sancion": pd.Series(dtype=object),
        "fecha_inicio": pd.Series(dtype="datetime64[ns]"),
        "fecha_fin": pd.Series(dtype="datetime64[ns]"),
        "es_definitiva": pd.Series(dtype=bool),
        "resolucion": pd.Series(dtype=object),
        "motivo": pd.Series(dtype=object),
    }
)
