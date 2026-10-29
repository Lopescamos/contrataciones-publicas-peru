-- Adjudicaciones a proveedores con sanción de inhabilitación vigente en la fecha de adjudicación.
-- Recuerda: es una alerta para revisar, no una conclusión.
SELECT
    f.fecha                         AS fecha_adjudicacion,
    a.ocid,
    p.nomenclatura,
    e.nombre                        AS entidad,
    pr.nombre                       AS proveedor,
    pr.ruc,
    a.monto_asignado_pen
FROM fact_adjudicacion a
JOIN fact_proceso p        ON p.proceso_key = a.proceso_key
JOIN dim_proveedor pr      ON pr.proveedor_key = a.proveedor_key
LEFT JOIN dim_entidad e    ON e.entidad_key = a.entidad_key
LEFT JOIN dim_fecha f      ON f.fecha_key = a.fecha_adjudicacion_key
WHERE a.proveedor_inhabilitado
  AND a.es_valida
ORDER BY f.fecha DESC
