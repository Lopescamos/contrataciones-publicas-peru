-- Cantidad de procesos marcados por cada indicador de riesgo.
SELECT
    i.codigo,
    i.nombre                               AS indicador,
    i.peso,
    COUNT(DISTINCT al.ocid)                AS n_procesos_marcados,
    ROUND(CAST(100.0 * COUNT(DISTINCT al.ocid)
               / NULLIF((SELECT COUNT(*) FROM fact_proceso), 0) AS NUMERIC), 2) AS pct_procesos
FROM dim_indicador i
LEFT JOIN fact_alerta al ON al.indicador_key = i.indicador_key
GROUP BY i.codigo, i.nombre, i.peso
ORDER BY i.codigo
