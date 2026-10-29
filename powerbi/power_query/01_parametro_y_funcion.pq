// =============================================================================
// Carga de la capa gold (Parquet) en Power BI con UN parámetro y UNA función.
// Así, si mueves el proyecto de carpeta, solo cambias el parámetro.
// -----------------------------------------------------------------------------
// PASO 1 - Crear el parámetro
//   Home > Transform data > Manage Parameters > New Parameter
//     Name:            RutaCurated
//     Type:            Text
//     Current Value:   C:\proyectos\contrataciones-publicas-peru\data\curated\
//   (la ruta DEBE terminar en "\")
//
// PASO 2 - Crear la función
//   Home > New Source > Blank Query  ->  Advanced Editor  ->  pegar el bloque de abajo
//   Renombrar la consulta como:  fnCargarTabla
// =============================================================================

(nombreTabla as text) as table =>
let
    Archivo = File.Contents(RutaCurated & nombreTabla & ".parquet"),
    Tabla = Parquet.Document(Archivo)
in
    Tabla
