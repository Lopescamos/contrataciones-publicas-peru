-- Detalle de adjudicaciones con proveedor, entidad y fecha.
DROP VIEW IF EXISTS vw_adjudicaciones;
CREATE VIEW vw_adjudicaciones AS
SELECT
    a.adjudicacion_key,
    a.ocid,
    a.award_id,
    f.fecha                      AS fecha_adjudicacion,
    f.anio,
    e.nombre                     AS entidad,
    e.departamento               AS departamento_entidad,
    pr.nombre                    AS proveedor,
    pr.ruc                       AS proveedor_ruc,
    pr.tipo_persona,
    pr.tiene_sancion,
    a.estado,
    a.es_valida,
    a.moneda,
    a.monto_adjudicado,
    a.monto_adjudicado_pen,
    a.n_proveedores_adjudicacion,
    a.monto_asignado_pen,
    a.proveedor_inhabilitado
FROM fact_adjudicacion a
LEFT JOIN dim_fecha f      ON f.fecha_key = a.fecha_adjudicacion_key
LEFT JOIN dim_entidad e    ON e.entidad_key = a.entidad_key
LEFT JOIN dim_proveedor pr ON pr.proveedor_key = a.proveedor_key;
