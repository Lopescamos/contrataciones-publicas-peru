-- Vista plana de procesos: el hecho principal con sus dimensiones.
-- Útil para análisis ad hoc en SQL, DBeaver, Excel o como alternativa al modelo estrella.
DROP VIEW IF EXISTS vw_procesos;
CREATE VIEW vw_procesos AS
SELECT
    p.proceso_key,
    p.ocid,
    p.nomenclatura,
    p.descripcion,
    f.fecha                       AS fecha_convocatoria,
    f.anio,
    f.mes,
    f.anio_mes,
    e.nombre                      AS entidad,
    e.ruc                         AS entidad_ruc,
    e.departamento,
    m.metodo_detalle              AS procedimiento,
    m.es_competitivo,
    c.categoria,
    p.estado,
    p.moneda,
    p.valor_referencial_pen,
    p.n_postores,
    p.plazo_presentacion_dias,
    p.plazo_consultas_dias,
    p.n_adjudicaciones,
    p.monto_adjudicado_pen,
    p.ratio_adjudicado_referencial,
    p.n_alertas,
    p.puntaje_riesgo,
    p.nivel_riesgo
FROM fact_proceso p
LEFT JOIN dim_fecha f     ON f.fecha_key = p.fecha_convocatoria_key
LEFT JOIN dim_entidad e   ON e.entidad_key = p.entidad_key
LEFT JOIN dim_metodo m    ON m.metodo_key = p.metodo_key
LEFT JOIN dim_categoria c ON c.categoria_key = p.categoria_key;
