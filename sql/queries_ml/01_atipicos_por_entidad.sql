-- Montos atípicos por entidad (Fase 2, ML): cuántos procesos se apartan del monto esperado.
-- Requiere 'contrataciones-ml predict' con carga a la base de datos.
-- Parámetros: :minimo (mínimo de procesos evaluados por entidad)
SELECT
    e.nombre                                                                 AS entidad,
    e.departamento,
    COUNT(*)                                                                 AS n_procesos,
    SUM(CASE WHEN pr.tipo_desviacion = 'Sobrecosto inusual' THEN 1 ELSE 0 END) AS n_sobrecosto,
    SUM(CASE WHEN pr.tipo_desviacion = 'Subcosto inusual' THEN 1 ELSE 0 END)   AS n_subcosto,
    ROUND(CAST(100.0 * SUM(CASE WHEN pr.es_atipico THEN 1 ELSE 0 END)
               / NULLIF(COUNT(*), 0) AS NUMERIC), 2)                         AS pct_atipicos,
    ROUND(CAST(SUM(CASE WHEN pr.tipo_desviacion = 'Sobrecosto inusual'
                        THEN pr.monto_adjudicado_pen - pr.monto_esperado_pen
                        ELSE 0 END) AS NUMERIC), 2)                          AS monto_sobre_esperado_pen
FROM pred_monto_esperado pr
JOIN fact_proceso p     ON p.ocid = pr.ocid
JOIN dim_entidad e      ON e.entidad_key = p.entidad_key
GROUP BY e.nombre, e.departamento
HAVING COUNT(*) >= :minimo
ORDER BY n_sobrecosto DESC, pct_atipicos DESC
