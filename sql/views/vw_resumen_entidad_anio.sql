-- KPIs por entidad y año (competencia, monto, proveedores y concentración).
DROP VIEW IF EXISTS vw_resumen_entidad_anio;
CREATE VIEW vw_resumen_entidad_anio AS
SELECT
    e.nombre                 AS entidad,
    e.ruc                    AS entidad_ruc,
    e.departamento,
    g.anio,
    g.n_procesos,
    g.n_procesos_competitivos,
    g.n_postor_unico,
    g.pct_postor_unico,
    g.monto_adjudicado_pen,
    g.n_proveedores,
    g.hhi,
    CASE
        WHEN g.hhi IS NULL THEN 'Sin datos'
        WHEN g.hhi >= 2500 THEN 'Alta concentración'
        WHEN g.hhi >= 1500 THEN 'Concentración moderada'
        ELSE 'Baja concentración'
    END                      AS nivel_concentracion,
    g.n_alertas,
    g.n_procesos_riesgo_alto
FROM agg_entidad_anio g
JOIN dim_entidad e ON e.entidad_key = g.entidad_key;
