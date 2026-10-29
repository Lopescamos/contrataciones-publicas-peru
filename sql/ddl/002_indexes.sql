-- =============================================================================
-- 002_indexes.sql — Índices sobre llaves foráneas y filtros frecuentes.
-- Portable SQLite / PostgreSQL. Idempotente.
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_fact_proceso_entidad      ON fact_proceso (entidad_key);
CREATE INDEX IF NOT EXISTS ix_fact_proceso_metodo       ON fact_proceso (metodo_key);
CREATE INDEX IF NOT EXISTS ix_fact_proceso_fecha        ON fact_proceso (fecha_convocatoria_key);
CREATE INDEX IF NOT EXISTS ix_fact_proceso_nivel        ON fact_proceso (nivel_riesgo);

CREATE INDEX IF NOT EXISTS ix_fact_adjudicacion_proceso   ON fact_adjudicacion (proceso_key);
CREATE INDEX IF NOT EXISTS ix_fact_adjudicacion_proveedor ON fact_adjudicacion (proveedor_key);
CREATE INDEX IF NOT EXISTS ix_fact_adjudicacion_entidad   ON fact_adjudicacion (entidad_key);
CREATE INDEX IF NOT EXISTS ix_fact_adjudicacion_fecha     ON fact_adjudicacion (fecha_adjudicacion_key);

CREATE INDEX IF NOT EXISTS ix_fact_contrato_proceso     ON fact_contrato (proceso_key);
CREATE INDEX IF NOT EXISTS ix_fact_postor_proceso       ON fact_postor (proceso_key);
CREATE INDEX IF NOT EXISTS ix_fact_postor_proveedor     ON fact_postor (proveedor_key);
CREATE INDEX IF NOT EXISTS ix_fact_sancion_proveedor    ON fact_sancion (proveedor_key);
CREATE INDEX IF NOT EXISTS ix_fact_alerta_proceso       ON fact_alerta (proceso_key);
CREATE INDEX IF NOT EXISTS ix_fact_alerta_indicador     ON fact_alerta (indicador_key);
CREATE INDEX IF NOT EXISTS ix_dim_proveedor_ruc         ON dim_proveedor (ruc);
CREATE INDEX IF NOT EXISTS ix_dim_entidad_ruc           ON dim_entidad (ruc);
