// =============================================================================
// Montos atípicos (Fase 2, machine learning): tabla pred_monto_esperado.
// Requiere haber ejecutado:  contrataciones-ml train  y  contrataciones-ml predict
// (después de cada 'contrataciones run', para que proceso_key coincida con la capa gold).
// -----------------------------------------------------------------------------
// PASO 1 - Crear el parámetro
//   Home > Transform data > Manage Parameters > New Parameter
//     Name:            RutaPredictions
//     Type:            Text
//     Current Value:   C:\proyectos\contrataciones-publicas-peru\data\predictions\
//   (la ruta DEBE terminar en "\")
//
// PASO 2 - Crear la consulta
//   Home > New Source > Blank Query  ->  Advanced Editor  ->  pegar el bloque de abajo
//   Renombrar la consulta EXACTAMENTE como:  pred_monto_esperado
// =============================================================================

let
    Archivo = File.Contents(RutaPredictions & "pred_monto_esperado.parquet"),
    Origen = Parquet.Document(Archivo),
    // Orden de los tipos de desviación para los visuales (Sort by column).
    ConOrden = Table.AddColumn(
        Origen,
        "tipo_desviacion_orden",
        each
            if [tipo_desviacion] = "Sobrecosto inusual" then 1
            else if [tipo_desviacion] = "Subcosto inusual" then 2
            else if [tipo_desviacion] = "Revisar datos" then 3
            else 4,
        Int64.Type
    )
in
    ConOrden

// -----------------------------------------------------------------------------
// Alternativa con PostgreSQL: la tabla pred_monto_esperado (o la vista
// vw_montos_atipicos) está en la misma base que la capa gold si predict se ejecutó
// con carga a la base de datos.
// -----------------------------------------------------------------------------
