-- Alertas de riesgo con el indicador y el contexto del proceso.
DROP VIEW IF EXISTS vw_alertas;
CREATE VIEW vw_alertas AS
SELECT
    al.alerta_key,
    al.ocid,
    i.codigo,
    i.nombre                 AS indicador,
    i.peso,
    al.detalle,
    p.nomenclatura,
    e.nombre                 AS entidad,
    e.departamento,
    m.metodo_detalle         AS procedimiento,
    f.anio,
    p.valor_referencial_pen,
    p.monto_adjudicado_pen,
    p.puntaje_riesgo,
    p.nivel_riesgo
FROM fact_alerta al
JOIN dim_indicador i      ON i.indicador_key = al.indicador_key
JOIN fact_proceso p       ON p.proceso_key = al.proceso_key
LEFT JOIN dim_entidad e   ON e.entidad_key = p.entidad_key
LEFT JOIN dim_metodo m    ON m.metodo_key = p.metodo_key
LEFT JOIN dim_fecha f     ON f.fecha_key = p.fecha_convocatoria_key;
