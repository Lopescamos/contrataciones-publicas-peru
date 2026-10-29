-- Top de entidades por monto adjudicado en un año.
-- Parámetros: :anio, :limite
-- Uso: contrataciones query sql/queries/02_top_entidades_por_monto.sql --param anio=2025 --param limite=10
SELECT
    e.nombre                                           AS entidad,
    e.ruc,
    e.departamento,
    COUNT(*)                                           AS n_procesos,
    ROUND(CAST(SUM(p.monto_adjudicado_pen) AS NUMERIC), 2) AS monto_adjudicado_pen,
    SUM(CASE WHEN p.n_alertas > 0 THEN 1 ELSE 0 END)   AS n_procesos_con_alerta
FROM fact_proceso p
JOIN dim_entidad e ON e.entidad_key = p.entidad_key
JOIN dim_fecha f   ON f.fecha_key = p.fecha_convocatoria_key
WHERE f.anio = :anio
GROUP BY e.entidad_key, e.nombre, e.ruc, e.departamento
ORDER BY monto_adjudicado_pen DESC
LIMIT :limite
