# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[versionado semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- Fase 2 (machine learning): **modelo de monto esperado** que estima cuánto debería costar un
  proceso según su perfil al convocarse y marca los montos adjudicados atípicos (sobrecosto o
  subcosto inusual). Ver `docs/11_machine_learning.md`.
- `src/contrataciones/features/`: catálogo de features con guardia contra la fuga de datos
  (`LeakageError`; las columnas del resultado se rechazan aunque se declaren en el YAML),
  dataset de modelado desde la capa gold (población, motivos de exclusión y fecha de
  adjudicación para la división), transformaciones sin estado (logaritmo, mes, tipo de entidad)
  y auditoría de disponibilidad de los datos (Fase 0) sobre la capa gold, las páginas crudas y
  la historia de versiones de la API.
- `src/contrataciones/models/`: división temporal con corte por disponibilidad del monto y
  ventana de madurez; línea base B1 (mediana por método y categoría), Ridge e
  HistGradientBoosting en `Pipeline`s de scikit-learn; selección en validación, evaluación en
  prueba y criterio de aceptación; predicción fuera de muestra por trimestres; montos atípicos
  con escala robusta (MAD con piso); registro versionado (joblib, catálogo YAML y bitácora
  JSON); puntaje, exportación y reporte Excel.
- Comando `contrataciones-ml` (`train`, `predict`, `list`), `scripts/train.py`,
  `scripts/predict.py` y `make train` / `make predict`.
- Salidas: `data/predictions/pred_monto_esperado.parquet` y `.csv`,
  `data/features/dataset_modelado.parquet`, `data/exports/reporte_montos_atipicos.xlsx`, tabla
  `pred_monto_esperado` (`sql/ddl_ml`, sin llaves foráneas hacia la capa gold), vista
  `vw_montos_atipicos` y consulta `sql/queries_ml/01_atipicos_por_entidad.sql`.
- Power BI: consulta `03_predicciones_ml.pq`, relación con `fact_proceso`, medidas *08 Monto
  esperado (ML)* y página 7 *Montos atípicos* en la especificación.
- Notebooks `notebooks/ml/` (auditoría de fuga de datos, objetivo, modelos, montos atípicos).
- 107 pruebas: guardia anti-fuga, canario (con ruido puro ningún modelo supera a la mediana y
  una columna con fuga lo dispara), señal plantada, división temporal, predicción fuera de
  muestra con un estimador espía, atípicos, registro y punta a punta de `contrataciones-ml`.
- Infraestructura: extra opcional `ml` (scikit-learn >= 1.9) y `requirements-ml.txt`;
  `config/model_config.yaml`; rutas `features`, `predictions` y `models` en `settings.yaml`;
  carpetas `data/features/`, `data/predictions/` y `models/`.

### Cambiado

- Los notebooks de análisis pasan a `notebooks/analytics/`; los de machine learning irán en
  `notebooks/ml/`. La celda de configuración ubica la raíz del proyecto buscando
  `pyproject.toml`, por lo que funcionan desde cualquier subcarpeta.
- `make install` instala también el extra `ml`; `make clean` borra `data/features/` y
  `data/predictions/`.
- La integración continua instala el extra `ml` y ejecuta `contrataciones-ml train` y
  `predict` sobre los datos sintéticos.
- `export/excel_exporter.py`: etiquetas en español para las columnas del reporte de montos
  atípicos (sin cambios para el reporte existente).

### Corregido

- La prueba de rutas absolutas de `tests/test_config.py` usaba una ruta POSIX fija y fallaba
  en Windows.

## [1.0.0] - 2026-10-19

### Agregado

- Ingesta de datos OCDS del OECE desde archivos `.jsonl(.gz)`, descarga masiva del Registro de
  Datos de OCP (publicación 135) y API del Portal de Contrataciones Abiertas (endpoint `records`
  consultado por mes con `dataSegmentationID`, paginado por `links.next`), con reintentos, pausas,
  límite de páginas por mes y advertencia si se alcanza.
- Lectura de Excel/CSV de sanciones con detección de la fila de encabezados y mapeo de columnas
  por alias configurables.
- Conversión de montos a soles: primero el monto en soles publicado por la fuente
  (`value.amount_PEN`) y, si no existe, la API de series del BCRP (serie PD04638PD) con caché local.
- Aplanado OCDS por bloques a cinco tablas (procesos, partes, postores, adjudicaciones, contratos).
- Limpieza de dominio: validación de RUC con dígito verificador, fechas a hora de Lima,
  departamentos normalizados, prorrateo de consorcios y deduplicación de postores.
- Adaptación a la publicación real del OECE: RUC de la entidad desde `additionalIdentifiers`,
  departamento desde `address.department`, plazos con inicio = fin tratados como no informados,
  periodo de consultas (`enquiryPeriod`), estados vacíos, postores tomados de `parties` y
  consorcios identificados por su código (`tipo_persona = Consorcio`).
- 27 reglas de calidad de datos con severidades y umbrales; perfil de columnas.
- Modelo estrella (6 dimensiones, 6 hechos, 1 agregado) e índice HHI por entidad y año.
- Siete indicadores de riesgo (RF01-RF07) con puntaje y niveles configurables; RF02 puede evaluar
  el plazo de presentación o el de consultas (`period`).
- Exportación a Parquet, CSV, reporte Excel formateado y bases de datos SQLite / PostgreSQL
  (carga con `COPY`), con DDL portable, 5 vistas y 8 consultas de negocio.
- CLI `contrataciones` (`run`, `download`, `setup-db`, `query`, `check-api`, `sample`).
- Notebooks de exploración, calidad, gasto y riesgo; guía de Power BI con medidas DAX, Power
  Query y tema.
- Datos sintéticos de demostración con la estructura de la publicación real, pruebas
  automatizadas y CI con GitHub Actions.
