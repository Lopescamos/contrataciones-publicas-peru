# Estructura real — contrataciones-publicas-peru

```
contrataciones-publicas-peru/
│
├── README.md                       # Arquitectura, inicio rápido, comandos, enlaces a docs
├── CHANGELOG.md                     # Historial de versiones (Keep a Changelog)
├── LICENSE                          # MIT
├── pyproject.toml                   # Paquete `contrataciones`, dependencias, entry point CLI
├── Makefile                         # make install / test / lint / run
├── docker-compose.yml                # PostgreSQL local para pruebas
├── .env.example                     # Plantilla de variables (API, DB) sin valores reales
├── .gitignore                       # Excluye data generada y .env; conserva .gitkeep
│
├── config/                          # Ningún valor de negocio va en el código
│   ├── settings.yaml                #   → rutas base, nivel de logging
│   ├── db_config.yaml               #   → perfiles: sqlite / local_postgres / nube
│   ├── api_config.yaml              #   → endpoint OECE: records, dataSegmentationID,
│   │                                #     months_back, max_pages, files_endpoint
│   ├── sources.yaml                 #   → alias de columnas del Excel de sanciones
│   ├── risk_rules.yaml              #   → umbrales/pesos RF01-RF07, periodo de RF02
│   └── export_config.yaml           #   → hojas del Excel, formato del CSV Power BI
│
├── data/                            # Arquitectura medallion
│   ├── raw/                         #   bronce: api/, bulk/, excel/ (crudo, sin tocar)
│   ├── processed/                   #   plata: *.parquet limpios + reporte_calidad.csv
│   │   └── _staging/                #     resultado intermedio del aplanado OCDS
│   ├── curated/                     #   oro: 13 tablas del modelo estrella (*.parquet)
│   ├── exports/                     #   reporte_contrataciones.xlsx + CSV para Power BI
│   ├── db/                          #   contrataciones.db (SQLite)
│   ├── external/                    #   caché del tipo de cambio BCRP
│   └── sample/                      #   datos sintéticos: ocds_sample.jsonl (1200),
│                                    #     sanciones_sample.xlsx, tipo_cambio_sample.csv
│
├── docs/
│   ├── 01_contexto_y_objetivos.md    # Por qué existe, qué preguntas responde, alcance
│   ├── 02_arquitectura.md            # Diagrama + decisiones de diseño (ADRs)
│   ├── 03_instalacion_y_configuracion.md  # Guía paso a paso + troubleshooting
│   ├── 04_fuentes_de_datos.md        # Estructura OCDS + particularidades reales del OECE
│   ├── 05_pipeline_etl.md            # Los 9 pasos del pipeline + opciones de CLI
│   ├── 06_modelo_de_datos.md         # Diccionario de datos: 13 tablas, cada columna
│   ├── 07_calidad_de_datos.md        # Las 27 reglas de calidad y sus severidades
│   ├── 08_indicadores_de_riesgo.md   # RF01-RF07: qué detecta cada uno, cómo agregar uno
│   ├── 09_base_de_datos.md           # SQL portable, 5 vistas, 8 consultas de negocio
│   ├── 10_convenciones_y_contribucion.md  # Estilo, Git, versionado, recetas de extensión
│   ├── glosario.md                   # Términos OCDS y de negocio
│   └── roadmap.md                    # Fases futuras (Fase 2: Machine Learning)
│
├── notebooks/                        # Se guardan sin salidas (convención del proyecto)
│   ├── 01_exploracion_ocds.ipynb      #   → estructura cruda, particularidades reales
│   ├── 02_calidad_de_datos.ipynb      #   → qué reglas fallan más, distribución
│   ├── 03_analisis_gasto.ipynb        #   → gasto por entidad, departamento, método
│   └── 04_indicadores_riesgo.ipynb    #   → distribución de puntajes y alertas
│
├── powerbi/
│   ├── README.md                     # Cómo construir el .pbix desde los CSV exportados
│   ├── docs/especificacion_dashboard.md  # Especificación de las 6 páginas
│   ├── docs/modelo_de_datos.md        # Relaciones entre tablas gold dentro de Power BI
│   └── measures/medidas_dax.md        # Catálogo de medidas DAX documentadas
│
├── scripts/                          # Atajos directos, sin pasar por la CLI completa
│   ├── run_pipeline.py                #   → corre el pipeline con parámetros por defecto
│   ├── download_bulk.py               #   → descarga el Registro de OCP anual
│   ├── setup_db.py                    #   → crea tablas, vistas, índices
│   ├── refresh_data.py                #   → descarga + pipeline, pensado para cron
│   └── generate_sample_data.py        #   → regenera data/sample con semilla fija
│
├── sql/
│   ├── ddl/001_schema.sql             # Las 13 tablas del modelo gold, tipos y comentarios
│   ├── views/                         # 5 vistas (ej. vw_procesos.sql)
│   └── queries/                       # 8 consultas de negocio, portables SQLite/PostgreSQL
│       ├── 02_top_entidades_por_monto.sql   # agrupa por llave surrogada (no por nombre)
│       └── 03_top_proveedores_por_monto.sql # idem, evita fusionar homónimos sin RUC
│
├── src/contrataciones/
│   ├── ingestion/                     # — CAPA DE INGESTA — trae datos de cualquier fuente
│   │   ├── api_client.py              #   → cliente HTTP con reintentos y paginación
│   │   ├── ocds_source.py             #   → OCDSApiSource.iter_releases(), month_segments(),
│   │   │                              #     available_months(), fuente de descarga masiva
│   │   ├── bcrp_client.py             #   → tipo de cambio del BCRP, con caché local
│   │   ├── excel_loader.py            #   → carga Excel/CSV con mapeo de columnas
│   │   ├── file_detector.py           #   → detect_format(path) -> csv/xlsx/json/parquet
│   │   └── db_connector.py            #   → conexión SQLAlchemy (SQLite/PostgreSQL)
│   │
│   ├── processing/                    # — CAPA DE PROCESAMIENTO — limpia, valida, transforma
│   │   ├── ocds_flattener.py          #   → flatten_release(release) -> dict[tabla, filas]
│   │   │                              #     extrae RUC adicional, monto PEN, enquiryPeriod
│   │   ├── cleaner.py                 #   → clean_procesos(df), clean_partes(df),
│   │   │                              #     clean_postores(df), clean_adjudicaciones(df),
│   │   │                              #     clean_contratos(df), make_party_key(...)
│   │   │                              #     (llave en cascada: RUC → id fuente → nombre)
│   │   ├── currency.py                #   → convert_to_pen(df, ..., source_pen_col)
│   │   │                              #     prioriza el PEN del publicador sobre BCRP
│   │   ├── validator.py               #   → run_quality_suite(tablas) -> 27 reglas
│   │   │                              #     (severidad ERROR/ADVERTENCIA/INFO)
│   │   ├── risk_indicators.py         #   → flag_* por cada RF01-RF07, catálogo y puntaje
│   │   └── transformer.py             #   → build_gold(tablas, reglas) -> 13 tablas estrella
│   │
│   ├── export/                        # — CAPA DE EXPORTACIÓN —
│   │   ├── csv_exporter.py            #   → export a Parquet/CSV
│   │   ├── excel_exporter.py          #   → reporte Excel con rankings, alertas, notas
│   │   └── db_writer.py               #   → carga el modelo gold a BD en una transacción
│   │
│   ├── utils/                         # — TRANSVERSAL —
│   │   ├── config_loader.py           #   → combina YAML de config/ con .env
│   │   ├── logger.py                  #   → logger centralizado del proyecto
│   │   ├── helpers.py                 #   → fechas, formateo
│   │   └── constants.py               #   → CONSORTIUM_TYPE, orden de carga del modelo
│   │
│   ├── pipeline.py                    # Pipeline/PipelineOptions: orquesta los 9 pasos
│   ├── cli.py                         # Comando `contrataciones`: run/download/setup-db/
│   │                                  #   query/check-api/sample
│   └── sample_data.py                 # Generador sintético (semilla fija, imita al OECE)
│
├── tests/                             # pytest, sin internet real (`responses` simula HTTP)
│   ├── conftest.py                    #   → make_release(), make_oece_release()
│   ├── test_ingestion/                #   → API, descarga masiva, BCRP
│   ├── test_processing/               #   → limpieza, calidad, riesgo, moneda
│   │   └── test_oece_format.py        #     fija el comportamiento ante datos reales OECE
│   ├── test_export/                   #   → Excel/CSV, escritura a BD
│   └── test_pipeline.py               #   → punta a punta + valida las 8 consultas SQL
│
└── .github/workflows/ci.yml           # ruff + pytest (SQLite y PostgreSQL) + pipeline sample
```

---

## Orden de creación: cómo construirías este proyecto paso a paso

Si estuvieras construyendo este proyecto tú solo, no creas todo el árbol de arriba de una vez.
Se va agregando en el mismo orden que los 12 pasos de la metodología (ver
`metodologia_analitica_detallada.md`). Este es el mapeo completo: qué se crea en cada paso, y por
qué en ese momento y no antes.

### Paso 1 — Entender el problema
Todavía no hay repositorio. Es una conversación/nota informal donde queda claro el problema de
negocio. Cuando ya tienes claro el tema, el **primer archivo real**:
- `docs/01_contexto_y_objetivos.md`

### Paso 2 — Mapear las fuentes de datos
Exploración pura, sin comprometerte a una estructura todavía:
- `notebooks/01_exploracion_ocds.ipynb` — para mirar muestras reales de la fuente
- Empiezas a llenar `docs/04_fuentes_de_datos.md` con lo que vas descubriendo

*Por qué aquí y no después: si programas antes de explorar, vas a tener que rehacer el modelo de
datos cuando la realidad no coincida con lo que asumiste.*

### Paso 3 — Diseñar la estructura del proyecto
Nace el esqueleto del repositorio: carpetas vacías (`.gitkeep` donde haga falta) y archivos base,
sin lógica real todavía:
- `README.md` (versión mínima), `LICENSE`, `CHANGELOG.md` (vacío), `.gitignore`
- `pyproject.toml` (solo lo esencial)
- Esqueleto de carpetas: `config/`, `data/{raw,processed,curated,exports,db,external,sample}/`,
  `docs/`, `notebooks/`, `powerbi/`, `scripts/`, `sql/{ddl,views,queries}/`,
  `src/contrataciones/{ingestion,processing,export,utils}/` (cada una con su `__init__.py`),
  `tests/`
- `docs/02_arquitectura.md` — documentas por qué elegiste esta estructura, mientras la decisión
  está fresca

*Por qué aquí: necesitas un lugar donde poner el código antes de escribir la primera línea, y
documentar la arquitectura ahora es más barato que reconstruirla de memoria después.*

### Paso 4 — Configurar el entorno de trabajo
- `.env.example`, `Makefile`, `docker-compose.yml`
- `git init` + primer commit con el esqueleto del paso 3
- `config/settings.yaml`, `config/db_config.yaml` (estructura mínima)
- `docs/03_instalacion_y_configuracion.md` (borrador)

### Paso 5 — Ingesta (capa bronce)
Primer código real del proyecto. Conviene este orden interno:
1. `src/contrataciones/ingestion/file_detector.py` y `excel_loader.py` — lo más simple primero
2. `src/contrataciones/sample_data.py` + `data/sample/` — **antes de atacar la API real**, generas
   datos sintéticos que imitan lo descubierto en el paso 2, para desarrollar y probar el resto del
   pipeline sin depender de la disponibilidad ni los límites de la fuente real
3. `src/contrataciones/ingestion/api_client.py` y `ocds_source.py` (la fuente real)
4. `src/contrataciones/ingestion/bcrp_client.py`, `db_connector.py`
5. `config/api_config.yaml`, `config/sources.yaml`
6. `scripts/download_bulk.py`
7. `tests/conftest.py` (fixtures básicas) y `tests/test_ingestion/`
8. Primeros archivos poblando `data/raw/`

*Por qué el generador sintético va antes que la API real: te desacopla de una fuente externa que
puede estar caída, tener límites de uso, o requerir gestión de acceso, y te deja seguir avanzando
en paralelo.*

### Paso 6 — Limpieza y calidad (capa plata)
- `src/contrataciones/processing/ocds_flattener.py`
- `src/contrataciones/processing/cleaner.py`
- `src/contrataciones/processing/currency.py`
- `src/contrataciones/processing/validator.py`
- `tests/test_processing/` (limpieza, calidad, moneda)
- `docs/07_calidad_de_datos.md`
- Primeros archivos en `data/processed/` y `data/processed/_staging/`

*Aquí es típico volver a `docs/04_fuentes_de_datos.md` para anotar las particularidades reales que
vas descubriendo al limpiar de verdad.*

### Paso 7 — Modelado analítico (capa oro)
- `src/contrataciones/processing/transformer.py`
- `sql/ddl/001_schema.sql`
- `docs/06_modelo_de_datos.md`
- Primera versión de `src/contrataciones/pipeline.py` y `cli.py` — ya tienes ingesta + limpieza +
  modelo, vale la pena armar un primer flujo de punta a punta, aunque todavía falten pasos
- Primeros archivos en `data/curated/`

### Paso 8 — Reglas de negocio e indicadores
- `src/contrataciones/processing/risk_indicators.py`
- `config/risk_rules.yaml`
- `docs/08_indicadores_de_riesgo.md`
- `tests/test_processing/test_risk_indicators.py`
- Se actualiza `sql/ddl/001_schema.sql` (agrega `fact_alerta`) y se extiende
  `transformer.py`/`pipeline.py` para incluir este paso

### Paso 9 — Pruebas automatizadas
Las pruebas ya se vienen escribiendo desde el paso 5; lo que se formaliza aquí:
- `.github/workflows/ci.yml` — integración continua sobre todo lo que ya existe
- Se revisa la cobertura y se llenan huecos (por ejemplo, un archivo dedicado como
  `tests/test_processing/test_oece_format.py` para fijar casos raros de datos reales)

### Paso 10 — Entrega al usuario final
- `src/contrataciones/export/csv_exporter.py`, `excel_exporter.py`, `db_writer.py`
- `config/export_config.yaml`
- `sql/views/`, `sql/queries/`
- `scripts/setup_db.py`
- `powerbi/README.md`, `powerbi/docs/`, `powerbi/measures/`
- Se completa `cli.py` con `run`, `setup-db`, `query`
- Primeros archivos en `data/exports/` y `data/db/`

### Paso 11 — Documentación
Se terminan los documentos que dependían de que el proyecto ya existiera completo:
- `docs/05_pipeline_etl.md`, `docs/09_base_de_datos.md`, `docs/10_convenciones_y_contribucion.md`,
  `docs/glosario.md`, `docs/roadmap.md`
- `README.md` en su versión final
- `notebooks/02_calidad_de_datos.ipynb`, `03_analisis_gasto.ipynb`, `04_indicadores_riesgo.ipynb`
- Primeras entradas reales en `CHANGELOG.md`

### Paso 12 — Mantenimiento y flujo de trabajo
- `scripts/refresh_data.py`
- `scripts/generate_sample_data.py` (si no se hizo ya en el paso 5)
- Se revisa y endurece `.github/workflows/ci.yml` con lo aprendido
- Se formaliza el flujo de ramas/PRs en Git para los cambios que vengan después (como la Fase 2 de
  Machine Learning)

