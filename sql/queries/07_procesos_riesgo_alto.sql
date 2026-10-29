-- Procesos con mayor puntaje de riesgo.
-- Parámetros: :limite
SELECT
    p.ocid,
    p.nomenclatura,
    e.nombre                         AS entidad,
    m.metodo_detalle                 AS procedimiento,
    f.anio,
    ROUND(CAST(p.valor_referencial_pen AS NUMERIC), 2) AS valor_referencial_pen,
    ROUND(CAST(p.monto_adjudicado_pen AS NUMERIC), 2)  AS monto_adjudicado_pen,
    p.n_postores,
    p.n_alertas,
    p.puntaje_riesgo,
    p.nivel_riesgo
FROM fact_proceso p
LEFT JOIN dim_entidad e ON e.entidad_key = p.entidad_key
LEFT JOIN dim_metodo m  ON m.metodo_key = p.metodo_key
LEFT JOIN dim_fecha f   ON f.fecha_key = p.fecha_convocatoria_key
WHERE p.n_alertas > 0
ORDER BY p.puntaje_riesgo DESC, p.valor_referencial_pen DESC
LIMIT :limite
