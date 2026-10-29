# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[versionado semántico](https://semver.org/lang/es/).

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
