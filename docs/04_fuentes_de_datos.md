# 4. Fuentes de datos

| # | Fuente | Tipo | Uso en el proyecto | Licencia / condiciones |
| --- | --- | --- | --- | --- |
| F1 | Registro de Datos de Open Contracting Partnership: publicación del OECE | Descarga masiva (`.jsonl.gz` anual) | **Fuente principal** de procesos de contratación | CC BY 4.0 |
| F2 | API del Portal de Contrataciones Abiertas del OECE | API REST (JSON) | Fuente complementaria (datos más recientes) | Datos abiertos del Estado |
| F3 | Registro de proveedores sancionados (Tribunal de Contrataciones) | Excel / CSV | Cruce de sanciones (indicador RF06) | Datos abiertos del Estado |
| F4 | BCRPData: tipo de cambio | API REST (JSON) | Conversión de montos en dólares a soles | Condiciones de uso de BCRPData |

---

## F1 · Datos OCDS del OECE (descarga masiva)

El OECE (antes OSCE) publica en su
[Portal de Contrataciones Abiertas](https://contratacionesabiertas.oece.gob.pe/) los procesos
registrados en el SEACE bajo el estándar **OCDS**. El
[Registro de Datos de OCP](https://data.open-contracting.org/es/publication/135) los redistribuye
en archivos anuales, con estas características (consultadas en octubre de 2026):

* **Cobertura:** de 2003 a la fecha, con actualización diaria en el portal y descarga mensual en
  el registro.
* **Licencia:** Creative Commons Atribución 4.0 (CC BY 4.0).
* **Prefijo OCID:** `ocds-dgv273` (SEACE v2 usa `ocds-dgv273-seacev2` y SEACE v3
  `ocds-dgv273-seacev3`).
* **Formatos:** JSON Lines comprimido (un proceso por línea), CSV y Excel (este último solo para
  años con menos de un millón de filas).
* **Procedimientos incluidos:** licitación pública, concurso público, adjudicación simplificada,
  subasta inversa electrónica, selección de consultores individuales, comparación de precios,
  contratación directa y concurso de proyecto de arquitectura.
* **No incluye** contrataciones sin procedimiento de selección (como las menores a 3, 8 o 9 UIT).
* **Extensiones OCDS** usadas por el publicador: nombre de moneda y tipo de cambio, valor total de
  ítems, cierre de contrato, departamento e información adicional del proceso.

### Cómo descargarla

```bash
contrataciones download --year 2025              # un año  -> data/raw/ocds/oece_2025.jsonl.gz
contrataciones download --year 2023-2025         # varios años
```

La URL usada es `https://data.open-contracting.org/es/publication/135/download?name=<año>.jsonl.gz`
(configurable en `config/api_config.yaml`). Un año reciente pesa del orden de 150 MB comprimido.
También puedes descargar el archivo manualmente desde el navegador y copiarlo en `data/raw/ocds/`.

### Estructura de un proceso OCDS (release compilado)

```
release
├── ocid                    Identificador único del proceso
├── date                    Fecha de la última actualización
├── buyer {id, name}        Entidad compradora (id = PE-CONSUCODE-<código>)
├── parties[]               Organizaciones con sus roles (buyer, procuringEntity, tenderer, supplier)
│   ├── identifier {scheme, id}        PE-CONSUCODE (entidades) o PE-RUC (proveedores)
│   ├── additionalIdentifiers[]        RUC de la entidad (scheme PE-RUC)
│   ├── address {region, department}   department = departamento; region puede ser la provincia
│   └── roles[]
├── tender                  Convocatoria
│   ├── title / description      Nomenclatura y objeto del proceso
│   ├── status                   Estado (suele venir vacío en la publicación del OECE)
│   ├── procurementMethod        open | selective | limited | direct
│   ├── procurementMethodDetails Procedimiento según la normativa peruana
│   ├── mainProcurementCategory  goods | services | works
│   ├── value {amount, currency, amount_PEN}  Valor referencial (y su equivalente en soles)
│   ├── tenderPeriod {startDate, endDate}     Plazo de presentación (a menudo inicio = fin)
│   ├── enquiryPeriod {startDate, endDate}    Formulación de consultas y observaciones
│   ├── numberOfTenderers / tenderers[]       Postores (también en parties con rol tenderer)
│   └── items[]
├── awards[]                Adjudicaciones (buena pro): value, date, status, suppliers[]
├── contracts[]             Contratos: awardID, value, dateSigned, period, status
└── dataSegmentation {id}   Mes de inicio de la convocatoria (AAAA-MM), extensión del OECE
```

### Mapeo de campos usados

| Campo OCDS | Columna (silver) | Notas |
| --- | --- | --- |
| `ocid` | `ocid` | Llave del proceso |
| `tender.title` | `nomenclatura` | En la publicación del OECE suele contener la nomenclatura (p. ej. `AS-SM-52-2024-ENTIDAD-1`) |
| `tender.description` | `descripcion` | Objeto de la contratación |
| `tender.procurementMethod` | `metodo_ocds` | Clasificación del estándar |
| `tender.procurementMethodDetails` | `metodo_detalle` | Procedimiento peruano |
| `tender.mainProcurementCategory` | `categoria_ocds` → `categoria` | Traducido a Bienes / Servicios / Obras |
| `tender.value.amount` / `currency` | `valor_referencial` / `moneda` | ≤ 0 se trata como no informado |
| `tender.value.amount_PEN` | `valor_referencial_pen_fuente` | Monto en soles publicado; se prefiere al tipo de cambio |
| `tender.datePublished` o `tenderPeriod.startDate` | `fecha_publicacion` | Fecha de convocatoria (hora de Lima) |
| `tender.tenderPeriod` | `plazo_presentacion_dias` | Días entre inicio y cierre; nulo si inicio = fin |
| `tender.enquiryPeriod` | `plazo_consultas_dias` | Días del periodo de consultas y observaciones |
| `tender.tenderers[]` (o `parties` con rol `tenderer`) | tabla `postores` | Deduplicados por RUC o código |
| `parties[].identifier.id`, `additionalIdentifiers[]` (PE-RUC) | `ruc` | Validado con dígito verificador |
| `parties[].address.department` (o `region`) | `departamento` | Normalizado a los 25 departamentos |
| `awards[].value`, `date`, `status` | tabla `adjudicaciones` | Una fila por proveedor (consorcios prorrateados) |
| `contracts[]` | tabla `contratos` | `awardID` vincula con la adjudicación |

### Particularidades de la publicación real

Observadas en *records* reales de la API del OECE (`seace_v3`, convocatorias de abril de 2024) y
reproducidas en los datos sintéticos y en las pruebas (`tests/test_processing/test_oece_format.py`):

| Rasgo | Ejemplo | Tratamiento en el pipeline |
| --- | --- | --- |
| Entidades identificadas con un código propio, no con el RUC | `PE-CONSUCODE-1984`; el RUC va en `additionalIdentifiers` | Se lee el RUC de `additionalIdentifiers`; si falta, la llave es el código |
| `address.region` con la provincia | `region: HUAYTARA`, `department: HUANCAVELICA` | Se prioriza `department` |
| `tenderPeriod` con inicio = fin (solo la fecha de convocatoria) | 19 de 20 procesos de la muestra | El plazo queda **nulo** (no 0 días); regla INFO en calidad; RF02 puede usar `enquiryPeriod` |
| Estados vacíos en `tender`, `awards` y `contracts` | `status: null` | Adjudicación sin estado = válida; contrato sin estado = `sin_estado` |
| Valor referencial en 0 | `amount: 0.0` (4 de 20) | Se trata como no informado |
| Monto en soles publicado por la fuente | `value.amount_PEN` | Se usa para montos en moneda extranjera antes que el tipo de cambio |
| Consorcios sin RUC propio | `PE-RUC-1509611` (código de 7 dígitos), `CONSORCIO ...` | Llave = código; `tipo_persona = Consorcio`; RF06 no puede cruzarlos con sanciones |
| Postores solo en `parties` | `tender.tenderers` ausente (2 de 20) | Se toman las partes con rol `tenderer` |
| Proveedores sin dirección | `address` ausente o solo `countryName` | `dim_proveedor.departamento` queda vacío; el análisis territorial usa el departamento de la entidad |
| Una adjudicación por proveedor | `awards[].id = <tenderId>-<código del proveedor>` | Sin cambios: el modelo ya es una fila por proveedor |

### Problemas de calidad conocidos

El Registro de Datos de OCP reporta para esta publicación: identificadores duplicados en
`tenderers` (también en `parties`), contratos sin estado, códigos de `documentType` no
documentados y adjudicaciones no vinculadas con contratos (y viceversa). El pipeline los mide en
cada ejecución y los reporta como reglas **INFO** (ver [Calidad de datos](07_calidad_de_datos.md)).

---

## F2 · API del Portal de Contrataciones Abiertas del OECE

* **URL base:** `https://contratacionesabiertas.oece.gob.pe/api/v1`. El portal publica la
  documentación interactiva (OpenAPI) en su sección «API».
* **Endpoint usado:** `records?sourceId=seace_v3&dataSegmentationID=AAAA-MM&page=N`. Devuelve un
  *record package*: por cada proceso, su `compiledRelease` (la foto completa del proceso) y la
  lista de releases enlazados. Trae 20 procesos por página.
* **Segmentación:** `dataSegmentationID` es el **año y mes de inicio de la convocatoria**. El
  pipeline consulta un mes por vez.
* **Paginación:** por el enlace `links.next` (`...&page=2`); termina cuando no hay página siguiente.
  La paginación tradicional permite recorrer hasta 10 000 resultados por consulta.
* **Sistemas de origen (`sourceId`):** `seace_v3` (vigente) y `seace_v2` (histórico, incluye el
  SEACE v1). Se configura con `OECE_API_SOURCE_ID`.
* **Otros endpoints** (no usados por el pipeline): `files?year=AAAA&source=seace_v3` (meses con
  paquete de descarga masiva, que se publica con retraso), `file/{source}/{tipo}/{año}/{mes}`
  (descarga mensual en JSON, CSV o Excel), `record/{ocid}`, `releases` y `recordsAfter` /
  `releasesAfter` (recorrido secuencial para más de 10 000 resultados, con `size` ≤ 100).

### Cómo usarla

```bash
contrataciones check-api                       # prueba el mes anterior (y la API del BCRP)
contrataciones check-api --month 2025-09       # prueba un mes concreto
contrataciones run --source api --month 2025-09 --api-max-pages 5 --no-db   # prueba corta
contrataciones run --source api --year 2025    # los 12 meses de 2025
contrataciones run --source api                # por defecto: mes actual y anterior
```

| Parámetro | Dónde | Por defecto |
| --- | --- | --- |
| Meses a consultar | `--month` (repetible), `--year`, `--date-from`/`--date-to` | `months_back: 2` |
| Páginas por mes | `--api-max-pages` o `max_pages` | 50 (1 000 procesos por mes) |
| Pausa entre solicitudes | `min_interval_seconds` | 0,5 s |
| Reintentos (429 y 5xx) | `retries` | 5, con espera exponencial |

Si un mes tiene más páginas que el límite, la ejecución termina con estado
`ok_con_advertencias` y lo indica ("se alcanzó el límite de páginas"). Para años completos usa la
descarga masiva (F1): es más rápida y no depende de la disponibilidad de la API.

Cada página recibida se guarda en `data/raw/api/<id_ejecucion>/<AAAA-MM>_page_00001.json` (capa
bronze), así se puede reprocesar sin volver a llamar a la API.

> **Disponibilidad.** Proyectos de la comunidad reportan bloqueos ocasionales a clientes
> automatizados (HTTP 403). El cliente envía un `User-Agent` de navegador, respeta pausas y
> reintentos, y `check-api` explica qué hacer si el servidor rechaza la conexión. El lector se
> validó con respuestas reales de la API y la paginación con pruebas que simulan el servidor;
> ejecuta `contrataciones check-api` en tu equipo antes de la primera corrida.

---

## F3 · Proveedores sancionados (Tribunal de Contrataciones Públicas)

El Tribunal de Contrataciones (antes del Estado, hoy Públicas) sanciona a proveedores, por ejemplo
con **inhabilitación temporal o definitiva** para contratar con el Estado. Estos registros se
publican como datos abiertos en la [Plataforma Nacional de Datos Abiertos](https://www.datosabiertos.gob.pe/)
(busca los conjuntos del OECE/OSCE sobre proveedores sancionados o inhabilitados) y pueden
verificarse por RUC en las consultas en línea del Registro Nacional de Proveedores (RNP).

### Cómo usarla

1. Descarga el archivo (Excel o CSV) y cópialo en `data/raw/excel/` con un nombre que contenga
   `sancion` o `inhabilit` (por ejemplo `proveedores_sancionados_2025.xlsx`).
2. Ejecuta el pipeline: el archivo se detecta solo. También puedes indicarlo con
   `--sanctions ruta/al/archivo.xlsx`.

### Contrato de datos (columnas)

El lector detecta la fila de encabezados aunque haya títulos encima y mapea los nombres con los
alias de `config/sources.yaml`:

| Columna canónica | Obligatoria | Alias aceptados (ejemplos) |
| --- | --- | --- |
| `ruc` | Sí | RUC, Nro. RUC, N° RUC, RUC del proveedor |
| `fecha_inicio` | Sí | Fecha inicio, Fecha de inicio, Inicio, Desde |
| `fecha_fin` | No | Fecha fin, Fecha de término, Hasta (vacía = sanción definitiva) |
| `nombre` | No | Nombre, Razón social, Nombre o razón social |
| `tipo_sancion` | No | Tipo de sanción, Sanción |
| `resolucion` | No | Resolución, Número de resolución |
| `motivo` | No | Motivo, Infracción, Causal |

Si el archivo trae otros encabezados, agrégalos como alias en `config/sources.yaml`; no hace falta
modificar código. Las fechas pueden venir como `dd/mm/aaaa`, `aaaa-mm-dd` o como fecha de Excel.

---

## F4 · Tipo de cambio (BCRPData)

La API de series estadísticas del Banco Central de Reserva del Perú es pública y no requiere
clave. Formato:

```
https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{serie}/json/{inicio}/{fin}/{idioma}
```

Se usa la serie diaria **PD04638PD** (TC interbancario, venta, S/ por US$). El pipeline solo la
consulta si hay montos en moneda extranjera, para el rango de fechas necesario, y guarda una caché
en `data/external/tipo_cambio_bcrp.csv`. Si la API no responde, usa la caché. Fines de semana y
feriados toman el último tipo de cambio disponible (hasta 10 días antes, configurable).

Alternativa sin API: `--rates file --rates-file mi_tipo_cambio.csv` con columnas
`fecha, moneda, tipo_cambio`.

---

## Datos de demostración (`data/sample`)

Los archivos de `data/sample` son **sintéticos**: entidades y proveedores llamados "DEMO", OCID con
prefijo `ocds-demo00` y RUC del rango `20999xxxxxx`. Tienen la misma estructura que las fuentes
reales e incluyen a propósito los problemas de calidad conocidos, para probar todo el pipeline sin
internet. Se regeneran con `contrataciones sample`. **No representan datos reales.**

## Atribución

Al publicar resultados (dashboard, informe, portafolio) incluye una nota como:

> Fuente: Organismo Especializado para las Contrataciones Públicas Eficientes (OECE), Portal de
> Contrataciones Abiertas, datos en estándar OCDS, redistribuidos por el Registro de Datos de
> Open Contracting Partnership bajo licencia CC BY 4.0. Elaboración propia.
