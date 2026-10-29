-- Tasa de postor único por tipo de procedimiento (solo procedimientos competitivos).
SELECT
    m.metodo_detalle                                                   AS procedimiento,
    COUNT(*)                                                           AS n_procesos,
    SUM(CASE WHEN p.n_postores = 1 THEN 1 ELSE 0 END)                  AS n_postor_unico,
    ROUND(CAST(100.0 * SUM(CASE WHEN p.n_postores = 1 THEN 1 ELSE 0 END)
               / NULLIF(COUNT(*), 0) AS NUMERIC), 2)                   AS pct_postor_unico,
    ROUND(CAST(AVG(p.n_postores) AS NUMERIC), 2)                       AS promedio_postores
FROM fact_proceso p
JOIN dim_metodo m ON m.metodo_key = p.metodo_key
WHERE m.es_competitivo
  AND COALESCE(p.estado, '') NOT IN ('cancelled', 'withdrawn')
GROUP BY m.metodo_detalle
ORDER BY pct_postor_unico DESC
