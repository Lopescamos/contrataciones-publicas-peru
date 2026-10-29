-- =============================================================================
-- 001_pred_monto_esperado.sql — Predicciones del modelo de monto esperado (Fase 2, ML).
-- SQL portable: SQLite y PostgreSQL. Idempotente (IF NOT EXISTS).
-- Lo ejecuta 'contrataciones-ml predict', no el pipeline de analítica: por eso vive en
-- sql/ddl_ml y no en sql/ddl (el pipeline ejecuta todos los scripts de esa carpeta).
-- Sin llaves foráneas hacia la capa gold: el pipeline recarga fact_proceso con DELETE y
-- SQLite valida las llaves foráneas (PRAGMA foreign_keys = ON). Se une por ocid.
-- =============================================================================

CREATE TABLE IF NOT EXISTS pred_monto_esperado (
    proceso_key                     INTEGER,           -- llave de fact_proceso en la misma corrida
    ocid                            TEXT PRIMARY KEY,
    valor_referencial_pen           NUMERIC(20, 2),
    monto_adjudicado_pen            NUMERIC(20, 2),
    ratio_adjudicado_referencial    DOUBLE PRECISION,
    ratio_esperado                  DOUBLE PRECISION,
    monto_esperado_pen              NUMERIC(20, 2),
    monto_minimo_esperado_pen       NUMERIC(20, 2),
    monto_maximo_esperado_pen       NUMERIC(20, 2),
    pct_desviacion                  DOUBLE PRECISION,  -- monto real / monto esperado - 1
    residuo_log                     DOUBLE PRECISION,
    z_robusto                       DOUBLE PRECISION,
    tipo_desviacion                 TEXT NOT NULL,     -- Normal | Sobrecosto inusual | Subcosto inusual | Revisar datos
    es_atipico                      BOOLEAN NOT NULL,
    es_adjudicado_igual_referencial BOOLEAN NOT NULL,
    segmento_escala                 TEXT,              -- segmento cuya escala se usó (o Global)
    origen_prediccion               TEXT NOT NULL,     -- Histórico (fuera de muestra) | Nuevo (modelo final)
    modelo_version                  TEXT NOT NULL,
    modelo_aceptado                 BOOLEAN NOT NULL,
    fecha_prediccion                DATE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_pred_monto_esperado_proceso ON pred_monto_esperado (proceso_key);
CREATE INDEX IF NOT EXISTS ix_pred_monto_esperado_tipo    ON pred_monto_esperado (tipo_desviacion);
