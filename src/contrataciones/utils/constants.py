"""Constantes de negocio y del estándar OCDS."""

from __future__ import annotations

TIMEZONE = "America/Lima"
BASE_CURRENCY = "PEN"
COUNTRY = "Perú"

# --- OCDS: listas de códigos (codelists) traducidas -----------------------------
CATEGORY_LABELS: dict[str, str] = {
    "goods": "Bienes",
    "services": "Servicios",
    "works": "Obras",
    "consultingServices": "Consultoría",
}
UNSPECIFIED = "No especificado"

PROCUREMENT_METHOD_LABELS: dict[str, str] = {
    "open": "Abierto",
    "selective": "Selectivo",
    "limited": "Limitado",
    "direct": "Directo",
}

# --- RUC (Registro Único de Contribuyentes, SUNAT) ----------------------------
RUC_LENGTH = 11
RUC_VALID_PREFIXES: tuple[str, ...] = ("10", "15", "16", "17", "20")
RUC_CHECK_WEIGHTS: tuple[int, ...] = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
RUC_PERSON_TYPES: dict[str, str] = {"10": "Persona natural", "20": "Persona jurídica"}
RUC_OTHER_TYPE = "Otro"
# Los consorcios no tienen RUC propio en la publicación del OECE (código interno de 7 dígitos).
CONSORTIUM_TYPE = "Consorcio"

# --- Departamentos del Perú (clave normalizada -> nombre para mostrar) ---------
DEPARTAMENTOS: dict[str, str] = {
    "AMAZONAS": "Amazonas",
    "ANCASH": "Áncash",
    "APURIMAC": "Apurímac",
    "AREQUIPA": "Arequipa",
    "AYACUCHO": "Ayacucho",
    "CAJAMARCA": "Cajamarca",
    "CALLAO": "Callao",
    "CUSCO": "Cusco",
    "HUANCAVELICA": "Huancavelica",
    "HUANUCO": "Huánuco",
    "ICA": "Ica",
    "JUNIN": "Junín",
    "LA LIBERTAD": "La Libertad",
    "LAMBAYEQUE": "Lambayeque",
    "LIMA": "Lima",
    "LORETO": "Loreto",
    "MADRE DE DIOS": "Madre de Dios",
    "MOQUEGUA": "Moquegua",
    "PASCO": "Pasco",
    "PIURA": "Piura",
    "PUNO": "Puno",
    "SAN MARTIN": "San Martín",
    "TACNA": "Tacna",
    "TUMBES": "Tumbes",
    "UCAYALI": "Ucayali",
}
# Variantes frecuentes que se asimilan a un departamento.
DEPARTAMENTO_ALIASES: dict[str, str] = {
    "CUZCO": "CUSCO",
    "LIMA METROPOLITANA": "LIMA",
    "LIMA PROVINCIAS": "LIMA",
    "LIMA REGION": "LIMA",
    "PROVINCIA CONSTITUCIONAL DEL CALLAO": "CALLAO",
    "PROV CONST DEL CALLAO": "CALLAO",
}

# --- Calendario en español (independiente de la configuración regional) ------
MONTH_NAMES: tuple[str, ...] = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
DAY_NAMES: tuple[str, ...] = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)

# --- Modelo de datos -----------------------------------------------------------
SILVER_TABLES: tuple[str, ...] = (
    "procesos",
    "partes",
    "postores",
    "adjudicaciones",
    "contratos",
    "sanciones",
    "tipo_cambio",
)
# Orden de carga respetando las llaves foráneas (dimensiones antes que hechos).
GOLD_LOAD_ORDER: tuple[str, ...] = (
    "dim_fecha",
    "dim_entidad",
    "dim_proveedor",
    "dim_metodo",
    "dim_categoria",
    "dim_indicador",
    "fact_proceso",
    "fact_adjudicacion",
    "fact_contrato",
    "fact_postor",
    "fact_sancion",
    "fact_alerta",
    "agg_entidad_anio",
)

RISK_LEVELS: tuple[str, ...] = ("Sin alertas", "Bajo", "Medio", "Alto")
