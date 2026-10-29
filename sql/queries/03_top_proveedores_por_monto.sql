-- Top de proveedores por monto adjudicado (prorrateado en consorcios) en un año.
-- Parámetros: :anio, :limite
SELECT
    pr.nombre                                              AS proveedor,
    pr.ruc,
    pr.tipo_persona,
    pr.tiene_sancion,
    COUNT(DISTINCT a.ocid)                                 AS n_procesos_ganados,
    COUNT(DISTINCT a.entidad_key)                          AS n_entidades,
    ROUND(CAST(SUM(a.monto_asignado_pen) AS NUMERIC), 2)   AS monto_asignado_pen
FROM fact_adjudicacion a
JOIN dim_proveedor pr ON pr.proveedor_key = a.proveedor_key
JOIN dim_fecha f      ON f.fecha_key = a.fecha_adjudicacion_key
WHERE a.es_valida
  AND f.anio = :anio
GROUP BY pr.proveedor_key, pr.nombre, pr.ruc, pr.tipo_persona, pr.tiene_sancion
ORDER BY monto_asignado_pen DESC
LIMIT :limite
