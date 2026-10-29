// =============================================================================
// Una consulta por tabla del modelo estrella.
// Para cada tabla: Home > New Source > Blank Query > Advanced Editor, pega la
// línea correspondiente y renombra la consulta EXACTAMENTE como la tabla
// (las medidas DAX usan estos nombres).
// =============================================================================

// ---- Consulta: dim_fecha
let Origen = fnCargarTabla("dim_fecha") in Origen

// ---- Consulta: dim_entidad
let Origen = fnCargarTabla("dim_entidad") in Origen

// ---- Consulta: dim_proveedor
let Origen = fnCargarTabla("dim_proveedor") in Origen

// ---- Consulta: dim_metodo
let Origen = fnCargarTabla("dim_metodo") in Origen

// ---- Consulta: dim_categoria
let Origen = fnCargarTabla("dim_categoria") in Origen

// ---- Consulta: dim_indicador
let Origen = fnCargarTabla("dim_indicador") in Origen

// ---- Consulta: fact_proceso
let Origen = fnCargarTabla("fact_proceso") in Origen

// ---- Consulta: fact_adjudicacion
let Origen = fnCargarTabla("fact_adjudicacion") in Origen

// ---- Consulta: fact_contrato
let Origen = fnCargarTabla("fact_contrato") in Origen

// ---- Consulta: fact_postor
let Origen = fnCargarTabla("fact_postor") in Origen

// ---- Consulta: fact_sancion
let Origen = fnCargarTabla("fact_sancion") in Origen

// ---- Consulta: fact_alerta
let Origen = fnCargarTabla("fact_alerta") in Origen

// ---- Consulta: agg_entidad_anio
let Origen = fnCargarTabla("agg_entidad_anio") in Origen

// -----------------------------------------------------------------------------
// Alternativa: conectar a PostgreSQL (local o nube) en lugar de Parquet.
//   Home > Get data > PostgreSQL database
//     Server:   localhost:5432   (o el host de Supabase / Neon / Cloud SQL)
//     Database: contrataciones
//     Data Connectivity mode: Import
//   Ejemplo en M para una tabla:
// let
//     Origen = PostgreSQL.Database("localhost:5432", "contrataciones"),
//     Tabla = Origen{[Schema = "public", Item = "fact_proceso"]}[Data]
// in
//     Tabla
// -----------------------------------------------------------------------------
