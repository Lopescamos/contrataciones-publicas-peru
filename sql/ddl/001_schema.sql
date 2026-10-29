-- =============================================================================
-- 001_schema.sql — Modelo estrella (capa gold) para análisis y Power BI.
-- SQL portable: funciona en SQLite y PostgreSQL. Idempotente (IF NOT EXISTS).
-- Ejecutar con:  contrataciones setup-db
-- Convenciones: *_key = llave sustituta, *_id = llave natural, *_pen = soles.
-- =============================================================================

-- ----------------------------------------------------------------- dimensiones
CREATE TABLE IF NOT EXISTS dim_fecha (
    fecha_key           INTEGER PRIMARY KEY,      -- AAAAMMDD
    fecha               DATE NOT NULL,
    anio                INTEGER NOT NULL,
    semestre            INTEGER NOT NULL,
    trimestre           INTEGER NOT NULL,
    mes                 INTEGER NOT NULL,
    nombre_mes          TEXT NOT NULL,
    anio_mes            TEXT NOT NULL,            -- AAAA-MM
    semana_iso          INTEGER NOT NULL,
    dia                 INTEGER NOT NULL,
    dia_semana          INTEGER NOT NULL,         -- 1 = lunes ... 7 = domingo
    nombre_dia          TEXT NOT NULL,
    es_fin_de_semana    BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_entidad (
    entidad_key         INTEGER PRIMARY KEY,
    entidad_id          TEXT NOT NULL UNIQUE,     -- RUC válido o id de origen
    ruc                 TEXT,
    nombre              TEXT NOT NULL,
    departamento        TEXT,
    pais                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_proveedor (
    proveedor_key       INTEGER PRIMARY KEY,
    proveedor_id        TEXT NOT NULL UNIQUE,     -- RUC válido o id de origen
    ruc                 TEXT,
    ruc_valido          BOOLEAN NOT NULL,
    nombre              TEXT NOT NULL,
    tipo_persona        TEXT,
    departamento        TEXT,
    tiene_sancion       BOOLEAN NOT NULL,
    n_sanciones         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_metodo (
    metodo_key              INTEGER PRIMARY KEY,
    metodo_detalle          TEXT NOT NULL UNIQUE, -- tender.procurementMethodDetails
    metodo_ocds             TEXT,                 -- open | selective | limited | direct
    es_competitivo          BOOLEAN NOT NULL,
    es_contratacion_directa BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_categoria (
    categoria_key       INTEGER PRIMARY KEY,
    categoria_ocds      TEXT NOT NULL UNIQUE,     -- goods | services | works | ...
    categoria           TEXT NOT NULL             -- Bienes | Servicios | Obras | ...
);

CREATE TABLE IF NOT EXISTS dim_indicador (
    indicador_key       INTEGER PRIMARY KEY,
    codigo              TEXT NOT NULL UNIQUE,     -- RF01 ... RF07
    nombre              TEXT NOT NULL,
    descripcion         TEXT,
    peso                INTEGER NOT NULL,
    habilitado          BOOLEAN NOT NULL,
    referencia          TEXT
);

-- ----------------------------------------------------------------------- hechos
CREATE TABLE IF NOT EXISTS fact_proceso (
    proceso_key                  INTEGER PRIMARY KEY,
    ocid                         TEXT NOT NULL UNIQUE,
    nomenclatura                 TEXT,
    descripcion                  TEXT,
    entidad_key                  INTEGER REFERENCES dim_entidad (entidad_key),
    metodo_key                   INTEGER REFERENCES dim_metodo (metodo_key),
    categoria_key                INTEGER REFERENCES dim_categoria (categoria_key),
    fecha_convocatoria_key       INTEGER REFERENCES dim_fecha (fecha_key),
    estado                       TEXT,
    moneda                       TEXT,
    valor_referencial            NUMERIC(20, 2),
    valor_referencial_pen        NUMERIC(20, 2),
    n_postores                   INTEGER,
    plazo_presentacion_dias      INTEGER,           -- nulo si tenderPeriod no informa el plazo
    plazo_consultas_dias         INTEGER,           -- tender.enquiryPeriod
    n_adjudicaciones             INTEGER NOT NULL,
    monto_adjudicado_pen         NUMERIC(20, 2),
    ratio_adjudicado_referencial DOUBLE PRECISION,
    n_alertas                    INTEGER NOT NULL,
    puntaje_riesgo               INTEGER NOT NULL,
    nivel_riesgo                 TEXT NOT NULL,     -- Sin alertas | Bajo | Medio | Alto
    nivel_riesgo_orden           INTEGER NOT NULL   -- 0..3, para ordenar en Power BI
);

CREATE TABLE IF NOT EXISTS fact_adjudicacion (
    adjudicacion_key             INTEGER PRIMARY KEY,
    proceso_key                  INTEGER NOT NULL REFERENCES fact_proceso (proceso_key),
    ocid                         TEXT NOT NULL,
    award_id                     TEXT NOT NULL,
    proveedor_key                INTEGER REFERENCES dim_proveedor (proveedor_key),
    entidad_key                  INTEGER REFERENCES dim_entidad (entidad_key),
    fecha_adjudicacion_key       INTEGER REFERENCES dim_fecha (fecha_key),
    estado                       TEXT,
    moneda                       TEXT,
    monto_adjudicado             NUMERIC(20, 2),
    monto_adjudicado_pen         NUMERIC(20, 2),
    n_proveedores_adjudicacion   INTEGER,
    monto_asignado_pen           NUMERIC(20, 2),    -- monto prorrateado entre consorciados
    es_valida                    BOOLEAN NOT NULL,
    proveedor_inhabilitado       BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_contrato (
    contrato_key                 INTEGER PRIMARY KEY,
    proceso_key                  INTEGER NOT NULL REFERENCES fact_proceso (proceso_key),
    ocid                         TEXT NOT NULL,
    contract_id                  TEXT NOT NULL,
    award_id                     TEXT,
    entidad_key                  INTEGER REFERENCES dim_entidad (entidad_key),
    fecha_firma_key              INTEGER REFERENCES dim_fecha (fecha_key),
    estado                       TEXT,
    moneda                       TEXT,
    monto_contrato               NUMERIC(20, 2),
    monto_contrato_pen           NUMERIC(20, 2),
    fecha_inicio                 DATE,
    fecha_fin                    DATE,
    duracion_dias                INTEGER,
    tiene_adjudicacion_vinculada BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_postor (
    postor_key                   INTEGER PRIMARY KEY,
    proceso_key                  INTEGER NOT NULL REFERENCES fact_proceso (proceso_key),
    proveedor_key                INTEGER REFERENCES dim_proveedor (proveedor_key),
    ocid                         TEXT NOT NULL,
    es_ganador                   BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_sancion (
    sancion_key                  INTEGER PRIMARY KEY,
    proveedor_key                INTEGER REFERENCES dim_proveedor (proveedor_key),
    ruc                          TEXT NOT NULL,
    tipo_sancion                 TEXT,
    fecha_inicio                 DATE,
    fecha_fin                    DATE,
    es_definitiva                BOOLEAN NOT NULL,
    vigente_a_fecha_corte        BOOLEAN NOT NULL,
    resolucion                   TEXT,
    motivo                       TEXT
);

CREATE TABLE IF NOT EXISTS fact_alerta (
    alerta_key                   INTEGER PRIMARY KEY,
    proceso_key                  INTEGER NOT NULL REFERENCES fact_proceso (proceso_key),
    indicador_key                INTEGER NOT NULL REFERENCES dim_indicador (indicador_key),
    ocid                         TEXT NOT NULL,
    codigo                       TEXT NOT NULL,
    detalle                      TEXT
);

-- ------------------------------------------------------------------ agregados
CREATE TABLE IF NOT EXISTS agg_entidad_anio (
    entidad_key                  INTEGER NOT NULL REFERENCES dim_entidad (entidad_key),
    anio                         INTEGER NOT NULL,
    n_procesos                   INTEGER NOT NULL,
    n_procesos_competitivos      INTEGER NOT NULL,
    n_postor_unico               INTEGER NOT NULL,
    pct_postor_unico             DOUBLE PRECISION,
    monto_adjudicado_pen         NUMERIC(20, 2),
    n_proveedores                INTEGER NOT NULL,
    hhi                          DOUBLE PRECISION,  -- Herfindahl-Hirschman 0-10 000
    n_alertas                    INTEGER NOT NULL,
    n_procesos_riesgo_alto       INTEGER NOT NULL,
    PRIMARY KEY (entidad_key, anio)
);
