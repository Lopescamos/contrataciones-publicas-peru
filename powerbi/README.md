# Power BI: guía para construir el dashboard

Esta carpeta contiene todo lo necesario para construir el reporte en **Power BI Desktop**
(Windows). El archivo `.pbix` no se genera por código: lo construyes tú siguiendo esta guía, y
queda guardado en `powerbi/dashboards/`.

```
powerbi/
├── dashboards/        # Aquí guardas contrataciones_peru.pbix (y versiones .pbit)
├── docs/
│   ├── modelo_de_datos.md          # Relaciones, ajustes de columnas, diagrama
│   └── especificacion_dashboard.md # Páginas, visuales, medidas y diseño
├── measures/
│   └── medidas_dax.md              # Todas las medidas DAX listas para copiar
├── power_query/
│   ├── 01_parametro_y_funcion.pq   # Parámetro RutaCurated + función fnCargarTabla
│   ├── 02_consultas_tablas.pq      # Una consulta por tabla (y alternativa PostgreSQL)
│   └── 03_predicciones_ml.pq       # Parámetro RutaPredictions + tabla pred_monto_esperado (ML)
└── theme/
    └── tema_contrataciones.json    # Tema visual sobrio del reporte
```

## Requisitos

1. Haber ejecutado el pipeline al menos una vez (genera `data/curated/*.parquet`):
   ```
   contrataciones run --source sample        # datos de demostración
   contrataciones run --source bulk --year 2025   # datos reales (después de descargarlos)
   ```
2. Power BI Desktop actualizado (Microsoft Store o descarga oficial).
3. Solo para la página de montos atípicos (Fase 2, opcional): entrenar el modelo y predecir
   después de cada corrida del pipeline:
   ```
   contrataciones-ml train
   contrataciones-ml predict
   ```

## Opción de conexión: ¿Parquet o PostgreSQL?

| Fuente | Cuándo usarla | Ventajas |
| --- | --- | --- |
| **Parquet** (`data/curated`) | Trabajo local, portafolio | Sin servidor; tipos de datos exactos; el más rápido de configurar |
| **PostgreSQL** (local o nube) | Reporte compartido o publicado en el servicio de Power BI | Actualización programada con *gateway* o directa si la BD es en la nube |
| CSV (`data/exports/powerbi`) | Si no puedes usar Parquet | Universal, pero sin tipos: hay que ajustarlos a mano |

SQLite no tiene conector nativo en Power BI (requiere un driver ODBC); úsalo solo para análisis
con SQL o Python.

---

## Paso a paso (Parquet)

### 1. Crear el parámetro y la función de carga

1. Abre Power BI Desktop → `Home > Transform data` (abre el **Power Query Editor**).
2. `Home > Manage Parameters > New Parameter`:
   * **Name:** `RutaCurated`
   * **Type:** `Text`
   * **Current Value:** la ruta a `data/curated` terminada en `\`, por ejemplo
     `C:\proyectos\contrataciones-publicas-peru\data\curated\`
3. `Home > New Source > Blank Query` → `Advanced Editor` → pega el contenido de
   `power_query/01_parametro_y_funcion.pq` → **Done**. Renombra la consulta a `fnCargarTabla`.

### 2. Cargar las 13 tablas

Para cada tabla de `power_query/02_consultas_tablas.pq`: `New Source > Blank Query` →
`Advanced Editor` → pega la línea → renombra la consulta **exactamente** con el nombre de la
tabla (`dim_fecha`, `fact_proceso`, ...). Al terminar: `Home > Close & Apply`.

> Atajo: crea la primera consulta, luego clic derecho → `Duplicate` y solo cambia el nombre de
> la tabla dentro de la fórmula.

### 3. Modelo de datos

En `Model view`:

1. Crea las 13 relaciones de `docs/modelo_de_datos.md` (`Manage relationships > New`).
2. Selecciona `dim_fecha` → `Table tools > Mark as date table` → columna `fecha`.
3. Ordenamientos con `Column tools > Sort by column`: `nombre_mes` por `mes`, `nombre_dia` por
   `dia_semana`, `nivel_riesgo` por `nivel_riesgo_orden`.
4. `dim_entidad[departamento]` → `Data category: State or Province`; `pais` → `Country`.
5. Oculta las columnas `*_key` (clic derecho → `Hide in report view`).

### 4. Medidas DAX

1. `Home > Enter data` → tabla vacía llamada `_Medidas` → `Load`.
2. Con `_Medidas` seleccionada: `Modeling > New measure` y copia cada medida de
   `measures/medidas_dax.md`.
3. Organiza en carpetas: `Model view > Properties > Display folder` (01 Volumen, 02 Montos, ...).

### 5. Tema y páginas

1. `View > Themes > Browse for themes` → `theme/tema_contrataciones.json`.
2. Construye las páginas según `docs/especificacion_dashboard.md`.
3. Guarda como `powerbi/dashboards/contrataciones_peru.pbix`.

### 6. Montos atípicos (Fase 2, opcional)

1. Crea el parámetro `RutaPredictions` y la consulta `pred_monto_esperado` con
   `power_query/03_predicciones_ml.pq`.
2. Relación 14 de `docs/modelo_de_datos.md`: `pred_monto_esperado[proceso_key]` →
   `fact_proceso[proceso_key]`, cardinalidad `Many to one (*:1)` y dirección `Single`.
3. Ordena `tipo_desviacion` por `tipo_desviacion_orden` y copia las medidas de la carpeta
   `08 Monto esperado (ML)` de `measures/medidas_dax.md`.
4. Construye la página 7 de `docs/especificacion_dashboard.md`.

### 7. Actualizar los datos

Cada vez que vuelvas a ejecutar el pipeline, en Power BI: `Home > Refresh`. Si moviste la
carpeta del proyecto, cambia el valor de `RutaCurated` (`Transform data > Edit parameters`).
Si usas la página de montos atípicos, ejecuta `contrataciones-ml predict` después de cada
`contrataciones run`: `proceso_key` cambia en cada corrida y la relación con `fact_proceso`
solo es válida si ambas tablas salen de la misma.

---

## Paso a paso (PostgreSQL)

1. Ejecuta el pipeline con base de datos (`DB_PROFILE=local_postgres` o `cloud_postgres` en `.env`).
2. `Home > Get data > PostgreSQL database`:
   * **Server:** `localhost:5432` (o el host de tu proveedor en la nube)
   * **Database:** `contrataciones`
   * **Data Connectivity mode:** `Import`
3. Credenciales: `Database` (usuario y contraseña de `.env`). En la nube, mantén **Encrypt
   connection** activado.
4. En el **Navigator** marca las 13 tablas (o las vistas `vw_*` si prefieres un modelo plano) →
   `Transform data` → renombra las consultas quitando el prefijo `public ` → `Close & Apply`.
5. Continúa desde el paso 3 de la sección anterior.

## Publicar (opcional)

`Home > Publish` → elige tu *workspace*. Para que el servicio actualice datos:

* **Parquet local / PostgreSQL local:** requiere un *On-premises data gateway* en tu PC.
* **PostgreSQL en la nube:** configura las credenciales del origen en el servicio
  (`Settings > Data source credentials`) y la actualización programada.

Antes de publicar algo con datos reales, revisa la nota de interpretación de alertas y la
atribución de la fuente (CC BY 4.0).
