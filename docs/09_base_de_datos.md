# 9. Base de datos

El pipeline carga la capa gold en una base de datos relacional para consultas SQL, herramientas
de BI y acceso de otros usuarios. El mismo SQL funciona en **SQLite** y **PostgreSQL** (las
pruebas automatizadas lo verifican en ambos motores).

## Perfiles de conexión

Definidos en `config/db_config.yaml`; el activo se elige con `DB_PROFILE` en `.env` o con
`--db-profile` en la CLI.

| Perfil | Motor | Uso típico | Configuración |
| --- | --- | --- | --- |
| `local_sqlite` | SQLite | Empezar, pruebas, portafolio | Ninguna (archivo `data/db/contrataciones.db`) |
| `local_postgres` | PostgreSQL | Desarrollo con un motor "real" | `docker compose up -d` + variables `PG_*` |
| `cloud_postgres` | PostgreSQL administrado | Compartir datos, Power BI publicado | Variables `CLOUD_PG_*` (SSL requerido) |
| `custom_url` | Cualquiera soportado por SQLAlchemy | Casos especiales | `DATABASE_URL` |

Instalación y creación de cada opción: [Instalación y configuración](03_instalacion_y_configuracion.md).

## Objetos SQL

```
sql/
├── ddl/
│   ├── 001_schema.sql      13 tablas con llaves primarias y foráneas (CREATE TABLE IF NOT EXISTS)
│   └── 002_indexes.sql     Índices sobre llaves foráneas y filtros frecuentes
├── views/
│   ├── vw_procesos.sql              Proceso con sus dimensiones (vista plana)
│   ├── vw_adjudicaciones.sql        Adjudicación con proveedor, entidad y fecha
│   ├── vw_alertas.sql               Alertas con indicador y contexto del proceso
│   ├── vw_resumen_entidad_anio.sql  KPIs por entidad-año con nivel de concentración (HHI)
│   └── vw_resumen_proveedor.sql     Participación, adjudicaciones y sanciones por proveedor
└── queries/
    ├── 01_gasto_por_anio_y_categoria.sql
    ├── 02_top_entidades_por_monto.sql         (:anio, :limite)
    ├── 03_top_proveedores_por_monto.sql       (:anio, :limite)
    ├── 04_postor_unico_por_procedimiento.sql
    ├── 05_adjudicaciones_a_inhabilitados.sql
    ├── 06_concentracion_hhi_por_entidad.sql   (:anio)
    ├── 07_procesos_riesgo_alto.sql            (:limite)
    └── 08_alertas_por_indicador.sql
```

Objetos de la Fase 2 (machine learning), que crea `contrataciones-ml predict` y no el pipeline:

```
sql/
├── ddl_ml/
│   └── 001_pred_monto_esperado.sql   Tabla de predicciones, sin llaves foráneas hacia la capa gold
├── views_ml/
│   └── vw_montos_atipicos.sql         Atípicos con el contexto del proceso y sus alertas por reglas
└── queries_ml/
    └── 01_atipicos_por_entidad.sql    (:minimo)
```

Van en carpetas propias porque el pipeline ejecuta todos los scripts de `sql/ddl` y las pruebas
de punta a punta ejecutan todas las consultas de `sql/queries` contra la capa gold.

### Crear o recrear el esquema

```bash
contrataciones setup-db                 # crea lo que falte (idempotente)
contrataciones setup-db --drop          # elimina y recrea las tablas (cambios de modelo)
contrataciones setup-db --db-profile cloud_postgres
```

El pipeline también ejecuta el DDL antes de cargar, así que `setup-db` solo es necesario para
preparar una base vacía o recrearla.

## Estrategias de carga

| Estrategia | Cómo | Cuándo |
| --- | --- | --- |
| **Full refresh** (por defecto) | Borra el contenido de las tablas y carga todo, en una transacción | Siempre que se reprocesa el periodo completo |
| Append | Agrega filas sin borrar | Cargas incrementales controladas |
| Upsert | `db_writer.upsert(...)`: inserta o actualiza por llave (`ON CONFLICT`) | Actualizaciones puntuales desde código |

Se configura en `db_config.yaml > load.mode`. En PostgreSQL la carga usa `COPY ... FROM STDIN`
(`use_copy: true`), mucho más rápido que `INSERT`.

## Ejecutar consultas

```bash
# Mostrar en pantalla
contrataciones query sql/queries/04_postor_unico_por_procedimiento.sql

# Con parámetros
contrataciones query sql/queries/02_top_entidades_por_monto.sql --param anio=2025 --param limite=10

# Exportar a Excel o CSV
contrataciones query sql/queries/07_procesos_riesgo_alto.sql --param limite=100 --output riesgo.xlsx
```

Desde Python:

```python
from contrataciones.ingestion.db_connector import DatabaseConnector

with DatabaseConnector() as db:            # usa el perfil de DB_PROFILE
    top = db.read_sql_file("sql/queries/02_top_entidades_por_monto.sql",
                           params={"anio": 2025, "limite": 10})
    resumen = db.read_query("SELECT nivel_riesgo, COUNT(*) AS n FROM fact_proceso GROUP BY nivel_riesgo")
```

## Reglas para escribir SQL portable

Para que una consulta funcione en SQLite y PostgreSQL:

* Usa `DROP VIEW IF EXISTS` + `CREATE VIEW` (no `CREATE OR REPLACE VIEW`).
* No uses funciones de fecha propias de un motor (`strftime`, `date_trunc`): une con `dim_fecha`
  y usa `anio`, `mes`, `anio_mes`.
* Para promedios y porcentajes multiplica por `1.0` o `100.0` (evita la división entera de
  PostgreSQL) y redondea con `ROUND(CAST(x AS NUMERIC), 2)`.
* En filtros booleanos usa la columna directamente (`WHERE es_valida`).
* Parámetros con nombre (`:anio`), que SQLAlchemy traduce para cada motor.
* Sin `;` al final de los archivos de `sql/queries` (una consulta por archivo).

## Conectar otras herramientas

| Herramienta | Conexión |
| --- | --- |
| Power BI | `Get data > PostgreSQL database` (ver `powerbi/README.md`) |
| DBeaver | Nueva conexión PostgreSQL o SQLite (archivo `data/db/contrataciones.db`) |
| Excel | `Data > Get Data > From Database > From PostgreSQL Database` |
| Python / pandas | `DatabaseConnector` o `pandas.read_sql` con SQLAlchemy |
