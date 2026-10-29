-- Montos atípicos (Fase 2, ML): procesos cuyo monto adjudicado se aleja del monto esperado,
-- con el contexto del proceso y su puntaje de riesgo por reglas (RF01-RF07) para comparar.
-- Incluye sobrecostos, subcostos y casos a revisar por datos. Requiere la capa gold.
-- Una desviación inusual NO prueba una irregularidad: señala un proceso que conviene revisar.
DROP VIEW IF EXISTS vw_montos_atipicos;
CREATE VIEW vw_montos_atipicos AS
SELECT
    pr.ocid,
    p.nomenclatura,
    p.descripcion,
    f.fecha                         AS fecha_convocatoria,
    f.anio,
    e.nombre                        AS entidad,
    e.departamento,
    m.metodo_detalle                AS procedimiento,
    c.categoria,
    pr.valor_referencial_pen,
    pr.monto_adjudicado_pen,
    pr.monto_esperado_pen,
    pr.monto_minimo_esperado_pen,
    pr.monto_maximo_esperado_pen,
    pr.pct_desviacion,
    pr.z_robusto,
    pr.tipo_desviacion,
    pr.es_adjudicado_igual_referencial,
    pr.origen_prediccion,
    pr.modelo_version,
    pr.modelo_aceptado,
    p.n_alertas,
    p.puntaje_riesgo,
    p.nivel_riesgo
FROM pred_monto_esperado pr
JOIN fact_proceso p       ON p.ocid = pr.ocid
LEFT JOIN dim_fecha f     ON f.fecha_key = p.fecha_convocatoria_key
LEFT JOIN dim_entidad e   ON e.entidad_key = p.entidad_key
LEFT JOIN dim_metodo m    ON m.metodo_key = p.metodo_key
LEFT JOIN dim_categoria c ON c.categoria_key = p.categoria_key
WHERE pr.tipo_desviacion <> 'Normal';
