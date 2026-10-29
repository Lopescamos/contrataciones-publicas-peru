-- Monto adjudicado y número de procesos por año y categoría.
-- Uso: contrataciones query sql/queries/01_gasto_por_anio_y_categoria.sql
SELECT
    f.anio,
    c.categoria,
    COUNT(*)                                   AS n_procesos,
    SUM(p.n_adjudicaciones)                    AS n_adjudicaciones,
    ROUND(CAST(SUM(p.monto_adjudicado_pen) AS NUMERIC), 2) AS monto_adjudicado_pen
FROM fact_proceso p
JOIN dim_fecha f     ON f.fecha_key = p.fecha_convocatoria_key
JOIN dim_categoria c ON c.categoria_key = p.categoria_key
GROUP BY f.anio, c.categoria
ORDER BY f.anio, monto_adjudicado_pen DESC
