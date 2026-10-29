-- Entidades con mayor concentración de proveedores (índice Herfindahl-Hirschman) en un año.
-- Parámetros: :anio
-- Referencia: HHI < 1500 baja, 1500-2500 moderada, >= 2500 alta concentración.
SELECT
    e.nombre                                          AS entidad,
    e.departamento,
    g.n_procesos,
    g.n_proveedores,
    ROUND(CAST(g.monto_adjudicado_pen AS NUMERIC), 2)  AS monto_adjudicado_pen,
    ROUND(CAST(g.hhi AS NUMERIC), 0)                  AS hhi
FROM agg_entidad_anio g
JOIN dim_entidad e ON e.entidad_key = g.entidad_key
WHERE g.anio = :anio
  AND g.n_procesos >= 5
ORDER BY g.hhi DESC
