-- Resumen por proveedor: participación, adjudicaciones y sanciones.
DROP VIEW IF EXISTS vw_resumen_proveedor;
CREATE VIEW vw_resumen_proveedor AS
SELECT
    pr.proveedor_key,
    pr.nombre                                              AS proveedor,
    pr.ruc,
    pr.tipo_persona,
    pr.tiene_sancion,
    pr.n_sanciones,
    COALESCE(par.n_procesos_postulados, 0)                 AS n_procesos_postulados,
    COALESCE(adj.n_procesos_ganados, 0)                    AS n_procesos_ganados,
    COALESCE(adj.n_entidades, 0)                           AS n_entidades,
    adj.monto_asignado_pen,
    COALESCE(adj.n_adjudicaciones_inhabilitado, 0)         AS n_adjudicaciones_inhabilitado
FROM dim_proveedor pr
LEFT JOIN (
    SELECT proveedor_key, COUNT(DISTINCT ocid) AS n_procesos_postulados
    FROM fact_postor
    GROUP BY proveedor_key
) par ON par.proveedor_key = pr.proveedor_key
LEFT JOIN (
    SELECT
        proveedor_key,
        COUNT(DISTINCT ocid)                                         AS n_procesos_ganados,
        COUNT(DISTINCT entidad_key)                                  AS n_entidades,
        SUM(monto_asignado_pen)                                      AS monto_asignado_pen,
        SUM(CASE WHEN proveedor_inhabilitado THEN 1 ELSE 0 END)      AS n_adjudicaciones_inhabilitado
    FROM fact_adjudicacion
    WHERE es_valida
    GROUP BY proveedor_key
) adj ON adj.proveedor_key = pr.proveedor_key;
