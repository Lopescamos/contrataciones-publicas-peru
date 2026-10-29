# 3. Instalación y configuración

## Requisitos

| Herramienta | Versión | Para qué |
| --- | --- | --- |
| Python | 3.11 o superior (64 bits) | Ejecutar el pipeline |
| Git | cualquiera reciente | Control de versiones |
| Power BI Desktop | actual (Windows) | Dashboard |
| Docker Desktop | opcional | PostgreSQL local con un comando |
| Google Cloud CLI (`gcloud`, `bq`) | opcional | Base de datos o data warehouse en la nube |

## Instalación paso a paso

### Windows (PowerShell)

```powershell
# 1. Ubícate en la carpeta del proyecto
cd C:\proyectos\contrataciones-publicas-peru

# 2. Crea y activa el entorno virtual
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
# Si aparece "running scripts is disabled", ejecuta una vez:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 3. Instala el proyecto con las herramientas de desarrollo y de machine learning
python -m pip install --upgrade pip
pip install -e ".[dev,ml]"

# 4. Crea tu archivo de variables de entorno
Copy-Item .env.example .env

# 5. Verifica la instalación
pytest
contrataciones run --source sample
```

### Linux / macOS (bash)

```bash
cd ~/proyectos/contrataciones-publicas-peru
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,ml]"
cp .env.example .env
pytest
contrataciones run --source sample
```

> `pip install -e .` instala el paquete en modo **editable**: los cambios que hagas en `src/`
> se reflejan sin reinstalar, y quedan disponibles los comandos `contrataciones` y
> `contrataciones-ml`. El extra `ml` agrega scikit-learn (Fase 2); sin él, todo el pipeline de
> analítica funciona igual. Si prefieres no
> instalarlo, los scripts de `scripts/` también funcionan (`python scripts/run_pipeline.py`).

### ¿Qué deberías ver?

Al final de `contrataciones run --source sample` aparece un resumen con las filas por capa, el
resultado de calidad y las rutas generadas:

```
Pipeline 20261019_143959_3e9ab8  |  fuente: sample  |  estado: ok
Filas por capa:
  staging : procesos=1,200, partes=4,512, postores=3,320, adjudicaciones=1,168, contratos=982
  ...
Calidad: 27 reglas, 26 OK, 1 con falla (0 de severidad ERROR)
Salidas:
  reporte_calidad    .../data/processed/reporte_calidad.csv
  curated            .../data/curated
  base_de_datos      sqlite:///.../data/db/contrataciones.db
  reporte_excel      .../data/exports/reporte_contrataciones.xlsx
```

La regla que falla es intencional: el archivo de sanciones de demostración incluye un RUC con
dígito verificador incorrecto para mostrar la validación.

## Configuración

Toda la configuración vive en `config/*.yaml`; los **secretos** (contraseñas, hosts) solo en
`.env`, que nunca se sube a Git. Los YAML leen el `.env` con la sintaxis `${VARIABLE:-defecto}`.

| Archivo | Qué configura |
| --- | --- |
| `.env` | Perfil de BD activo, credenciales, URLs de APIs, nivel de log |
| `config/settings.yaml` | Rutas de datos, tamaño de bloque, filtros por defecto, moneda, calidad |
| `config/db_config.yaml` | Perfiles `local_sqlite`, `local_postgres`, `cloud_postgres`, `custom_url` |
| `config/api_config.yaml` | Endpoints y reintentos de las APIs del OECE, OCP y BCRP |
| `config/sources.yaml` | Ubicación de archivos y alias de columnas del Excel de sanciones |
| `config/risk_rules.yaml` | Umbrales y pesos de los indicadores de riesgo |
| `config/export_config.yaml` | Formato de CSV, compresión Parquet y estilo del Excel |
| `config/model_config.yaml` | Modelo de monto esperado: población, features, división temporal, modelos y umbrales de atípicos (ver [Machine learning](11_machine_learning.md)) |

## Base de datos: tres opciones

### A. SQLite (por defecto, sin instalar nada)

No requiere configuración. La base queda en `data/db/contrataciones.db`. Para explorarla usa
[DBeaver](https://dbeaver.io/) o la extensión *SQLite Viewer* de VS Code, o la CLI:

```bash
contrataciones query sql/queries/08_alertas_por_indicador.sql
```

### B. PostgreSQL local

**Con Docker** (recomendado):

```bash
docker compose up -d                 # levanta PostgreSQL 16 con los datos de .env
```

En `.env` cambia `DB_PROFILE=local_postgres` y luego:

```bash
contrataciones setup-db              # crea tablas, índices y vistas
contrataciones run --source sample   # carga los datos
```

Para una interfaz web de administración: `docker compose --profile tools up -d` y abre
`http://localhost:8080` (Adminer; servidor `postgres`).

**Sin Docker:** instala PostgreSQL para Windows y crea la base desde `psql`:

```sql
CREATE USER analytics WITH PASSWORD 'cambia_esta_clave';
CREATE DATABASE contrataciones OWNER analytics;
```

### C. PostgreSQL en la nube

El perfil `cloud_postgres` sirve para cualquier PostgreSQL administrado. Completa en `.env`:

```dotenv
DB_PROFILE=cloud_postgres
CLOUD_PG_HOST=...
CLOUD_PG_PORT=5432
CLOUD_PG_DATABASE=postgres
CLOUD_PG_USER=...
CLOUD_PG_PASSWORD=...
CLOUD_PG_SSLMODE=require
```

**Supabase o Neon** (suelen ofrecer un plan gratuito; revisa sus condiciones actuales): crea un
proyecto y copia los datos de conexión del panel (*Connect*). En Supabase, si la conexión directa
falla por IPv6, usa la cadena del *Session pooler*.

**Google Cloud SQL con `gcloud`:**

```bash
gcloud config set project TU_PROYECTO
gcloud services enable sqladmin.googleapis.com

gcloud sql instances create contrataciones-pg \
    --database-version=POSTGRES_16 --edition=ENTERPRISE --tier=db-f1-micro \
    --region=southamerica-west1 --storage-size=10GB
gcloud sql databases create contrataciones --instance=contrataciones-pg
gcloud sql users create analytics --instance=contrataciones-pg --password="CLAVE_SEGURA"

# Conexión segura desde tu PC con Cloud SQL Auth Proxy
gcloud sql instances describe contrataciones-pg --format="value(connectionName)"
./cloud-sql-proxy --port 5433 TU_PROYECTO:southamerica-west1:contrataciones-pg
```

Con el proxy activo, en `.env`: `CLOUD_PG_HOST=127.0.0.1`, `CLOUD_PG_PORT=5433`,
`CLOUD_PG_DATABASE=contrataciones`, `CLOUD_PG_USER=analytics` y `CLOUD_PG_SSLMODE=disable` (el
proxy ya cifra la conexión). Cloud SQL **genera costo** mientras la instancia existe; al terminar:
`gcloud sql instances delete contrataciones-pg`.

### D. Data warehouse: BigQuery (opcional)

Para análisis a gran escala puedes cargar la capa gold en BigQuery con la CLI:

```bash
gcloud storage buckets create gs://TU_BUCKET --location=southamerica-west1
gcloud storage cp data/curated/*.parquet gs://TU_BUCKET/curated/
bq mk --dataset --location=southamerica-west1 TU_PROYECTO:contrataciones_pe

for f in data/curated/*.parquet; do
  t=$(basename "$f" .parquet)
  bq load --source_format=PARQUET --replace "contrataciones_pe.$t" "gs://TU_BUCKET/curated/$t.parquet"
done
```

En PowerShell, el bucle equivalente es:

```powershell
Get-ChildItem data\curated\*.parquet | ForEach-Object {
  bq load --source_format=PARQUET --replace "contrataciones_pe.$($_.BaseName)" "gs://TU_BUCKET/curated/$($_.Name)"
}
```

Power BI se conecta a BigQuery con `Get data > Google BigQuery`.

## Solución de problemas

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `contrataciones` no se reconoce como comando | Entorno virtual no activado o paquete no instalado | Activa `.venv` y ejecuta `pip install -e ".[dev]"` |
| `ModuleNotFoundError: sklearn` al usar `contrataciones-ml` | Falta el extra de machine learning | `pip install -e ".[dev,ml]"` |
| `running scripts is disabled on this system` | Política de ejecución de PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `No hay archivos OCDS en data/raw/ocds` | No se descargaron datos reales | `contrataciones download --year 2025` |
| `HTTP 403` al usar `--source api` | El servidor rechaza clientes automatizados | Usa la descarga masiva (`download` + `--source bulk`) |
| `check-api` responde, pero con 0 procesos | El mes consultado aún no tiene datos o el `sourceId` no corresponde | Prueba otro mes: `contrataciones check-api --month 2025-06`; revisa `params` en `config/api_config.yaml` |
| Advertencia "se alcanzó el límite de páginas" | El mes tiene más procesos que `max_pages` × 20 | Sube `--api-max-pages` o usa la descarga masiva para periodos largos |
| El proceso se queda sin memoria con un año completo | Demasiados procesos a la vez | Usa `--limit 50000` para probar, filtra con `--year` o baja `chunk_size` |
| `columnas no definidas en la BD` en el log | El modelo cambió y la tabla es antigua | `contrataciones setup-db --drop` y vuelve a ejecutar |
| `Faltan columnas requeridas ['ruc', ...]` | El Excel de sanciones usa otros encabezados | Agrega los encabezados como alias en `config/sources.yaml` |
| `could not connect to server` (PostgreSQL) | Servidor apagado o datos de `.env` incorrectos | `docker compose ps`, revisa `PG_*`/`CLOUD_PG_*` |
| Power BI no encuentra los Parquet | Ruta del parámetro incorrecta | `RutaCurated` debe terminar en `\` y apuntar a `data\curated\` |
