# 10. Convenciones y contribución

## Código

| Tema | Convención |
| --- | --- |
| Estilo | PEP 8 con `ruff` (línea de 100 caracteres). `ruff format` antes de cada commit |
| Idioma | Código (funciones, variables, módulos) en **inglés**; datos, columnas, logs y documentación en **español** |
| Tipos | *Type hints* en todas las funciones públicas (`from __future__ import annotations`) |
| Docstrings | En español, describiendo qué hace, parámetros relevantes y lo que devuelve |
| Capas | `ingestion` lee, `processing` transforma, `export` escribe. `processing` nunca hace E/S externa |
| Configuración | Ningún valor de negocio (umbrales, rutas, URLs) fijo en el código: va en `config/*.yaml` |
| Secretos | Solo en `.env` (nunca en YAML, código ni Git) |
| Logging | `get_logger(__name__)`; nunca `print` dentro del paquete (excepto en la CLI) |
| pandas | Compatible con pandas 2.2+ y 3.x: sin `inplace`, sin asignaciones encadenadas, `.loc` para modificar |

## Datos

| Tema | Convención |
| --- | --- |
| Nombres de columnas | `snake_case` en español; sufijos `_key`, `_id`, `_pen`; prefijos `n_`, `pct_`, `es_` |
| Formato entre capas | Parquet |
| Fechas | Hora de Lima, sin zona horaria; llaves de fecha como AAAAMMDD |
| Montos | `float` en Python, `NUMERIC(20,2)` en SQL; siempre indicar la moneda o usar `_pen` |
| Capas | Nunca modificar `data/raw`; todo lo demás se regenera con el pipeline |

## Pruebas

* Framework: `pytest`. Ejecuta `pytest` antes de cada commit.
* Cada módulo tiene su archivo de pruebas en `tests/` con la misma estructura de carpetas.
* Las pruebas no usan internet: las APIs se simulan con `responses`.
* La base de datos se prueba con SQLite siempre y con PostgreSQL si existe `TEST_POSTGRES_URL`:

  ```bash
  # PowerShell
  $env:TEST_POSTGRES_URL = "postgresql+psycopg2://analytics:clave@localhost:5432/contrataciones"
  pytest tests/test_export/test_db_writer.py
  ```

* Cobertura: `pytest --cov=contrataciones --cov-report=term-missing`.
* La prueba de punta a punta (`tests/test_pipeline.py`) ejecuta el pipeline sobre los datos
  sintéticos en una carpeta temporal y valida todas las consultas SQL.
* Modelo de monto esperado (Fase 2): `tests/test_features/` y `tests/test_models/` incluyen la
  guardia contra la fuga de datos, el canario (con ruido puro ningún modelo supera a la mediana)
  y la prueba de punta a punta de `contrataciones-ml`. Toda feature nueva necesita su prueba.
* `tests/test_processing/test_oece_format.py` fija el comportamiento ante las particularidades de
  la publicación real del OECE (fixture `make_oece_release` en `tests/conftest.py`). Si aparece un
  caso nuevo en los datos reales, agrégalo ahí primero.

## Flujo de trabajo con Git

```bash
git checkout -b feature/indicador-fraccionamiento
# ... cambios + pruebas ...
ruff format src tests scripts && ruff check src tests scripts && pytest
git commit -m "feat(riesgo): agrega indicador RF08 de fraccionamiento"
git push origin feature/indicador-fraccionamiento   # y abrir Pull Request
```

Mensajes de commit con [Conventional Commits](https://www.conventionalcommits.org/es/):
`feat`, `fix`, `docs`, `test`, `refactor`, `chore`, con el ámbito entre paréntesis
(`ingesta`, `limpieza`, `riesgo`, `bd`, `powerbi`).

La integración continua (`.github/workflows/ci.yml`) ejecuta lint, pruebas con SQLite y
PostgreSQL y el pipeline de demostración en cada *push* y *pull request*.

## Versionado

[Versionado semántico](https://semver.org/lang/es/) (`MAYOR.MENOR.PARCHE`) y registro de cambios en
`CHANGELOG.md` con el formato [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Un cambio en el modelo gold que rompa el dashboard o las consultas es un cambio **MAYOR**.

## Recetas para extender el proyecto

### Agregar una fuente de datos nueva (por ejemplo, un catálogo de entidades en Excel)

1. Define su contrato (ubicación y alias de columnas) en `config/sources.yaml`.
2. Léela con `load_tabular` + `apply_column_mapping` (`ingestion/excel_loader.py`).
3. Escribe su limpieza en `processing/cleaner.py` y úsala en `pipeline.py`.
4. Si alimenta el modelo, agrégala en `processing/transformer.py`, en `sql/ddl/001_schema.sql` y
   en `GOLD_LOAD_ORDER` (`utils/constants.py`).
5. Pruebas y documentación (diccionario de datos y fuentes).

### Agregar una columna al modelo gold

1. Calcúlala en `transformer.py`.
2. Agrégala al DDL (`sql/ddl/001_schema.sql`).
3. Documenta la columna en `docs/06_modelo_de_datos.md`.
4. Ejecuta `contrataciones setup-db --drop` y el pipeline.

### Agregar un indicador de riesgo

Ver [Indicadores de riesgo](08_indicadores_de_riesgo.md#agregar-un-indicador-nuevo).

### Agregar una feature al modelo de monto esperado

Declárala en `config/model_config.yaml` con su origen en la capa gold y
`available_at: convocatoria`; la guardia rechaza cualquier columna del resultado. Pasos y
criterios en [Machine learning](11_machine_learning.md#12-extender).

### Agregar una consulta SQL de negocio

Crea `sql/queries/NN_nombre.sql` siguiendo las reglas de SQL portable de
[Base de datos](09_base_de_datos.md); la prueba de punta a punta la ejecutará automáticamente
(agrega sus parámetros en `QUERY_PARAMS` de `tests/test_pipeline.py` si los usa).
