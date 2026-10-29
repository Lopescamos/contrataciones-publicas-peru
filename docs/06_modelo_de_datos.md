# 6. Modelo de datos y diccionario

## Convenciones de nombres

| Patrón | Significado | Ejemplo |
| --- | --- | --- |
| `dim_*` | Dimensión: describe el "quién, qué, dónde, cuándo" | `dim_entidad` |
| `fact_*` | Hecho: eventos medibles | `fact_adjudicacion` |
| `agg_*` | Agregado precalculado | `agg_entidad_anio` |
| `*_key` | Llave sustituta entera (relaciones) | `entidad_key` |
| `*_id` | Llave natural de negocio | `proveedor_id` (RUC) |
| `*_pen` | Monto en soles | `monto_adjudicado_pen` |
| `n_*` | Conteo | `n_postores` |
| `pct_*` | Proporción entre 0 y 1 | `pct_postor_unico` |
| `es_*`, `tiene_*` | Booleano | `es_competitivo` |
| `fecha_*_key` | Fecha como entero AAAAMMDD | `fecha_convocatoria_key = 20250307` |

Los nombres de columnas están en **español** (lenguaje del negocio); el código está en inglés.

---

## Capa gold (`data/curated`, base de datos)

Diagrama de relaciones en [`powerbi/docs/modelo_de_datos.md`](../powerbi/docs/modelo_de_datos.md).

### Granos

| Tabla | Una fila representa... |
| --- | --- |
| `fact_proceso` | un proceso de contratación (`ocid`) |
| `fact_adjudicacion` | un proveedor dentro de una adjudicación (los consorcios generan varias filas) |
| `fact_contrato` | un contrato |
| `fact_postor` | un postor (proveedor) en un proceso |
| `fact_alerta` | una alerta de riesgo de un proceso (proceso × indicador) |
| `fact_sancion` | un registro de sanción a un proveedor |
| `agg_entidad_anio` | una entidad en un año de convocatoria |

### `dim_fecha`

Calendario continuo que cubre años completos.

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `fecha_key` | entero (PK) | Fecha como AAAAMMDD |
| `fecha` | fecha | Fecha calendario |
| `anio`, `semestre`, `trimestre`, `mes`, `dia` | entero | Partes de la fecha |
| `nombre_mes` | texto | Enero ... Diciembre |
| `anio_mes` | texto | AAAA-MM (para ejes de gráficos) |
| `semana_iso` | entero | Semana ISO 8601 |
| `dia_semana` | entero | 1 = lunes ... 7 = domingo |
| `nombre_dia` | texto | Lunes ... Domingo |
| `es_fin_de_semana` | booleano | Sábado o domingo |

### `dim_entidad`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `entidad_key` | entero (PK) | Llave sustituta |
| `entidad_id` | texto (único) | RUC si es válido (en el OECE viene en `additionalIdentifiers`); si no, el id de origen (`PE-CONSUCODE-<código>`) o `NOM-<nombre>` |
| `ruc` | texto | RUC de la entidad (solo si es válido) |
| `nombre` | texto | Nombre más frecuente en los datos |
| `departamento` | texto | Departamento normalizado (25 valores oficiales) |
| `pais` | texto | "Perú" (para mapas en Power BI) |

### `dim_proveedor`

Incluye postores, adjudicados y proveedores que solo aparecen en el registro de sanciones.

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `proveedor_key` | entero (PK) | Llave sustituta |
| `proveedor_id` | texto (único) | RUC si es válido; si no, el id de origen (p. ej. `PE-RUC-1509611` de un consorcio) o `NOM-<nombre>` |
| `ruc` | texto | RUC (solo si es válido) |
| `ruc_valido` | booleano | Pasó la validación de 11 dígitos, prefijo y dígito verificador |
| `nombre` | texto | Nombre o razón social más frecuente |
| `tipo_persona` | texto | Persona jurídica (RUC 20), Persona natural (RUC 10), Otro, Consorcio (sin RUC y nombre "CONSORCIO ..."), No especificado |
| `departamento` | texto | Departamento de la dirección publicada en `parties`. El OECE no publica la dirección de los proveedores (a lo sumo el país), por lo que con sus datos queda vacío |
| `tiene_sancion` | booleano | Tiene al menos un registro en el archivo de sanciones |
| `n_sanciones` | entero | Número de registros de sanción |

### `dim_metodo`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `metodo_key` | entero (PK) | Llave sustituta |
| `metodo_detalle` | texto (único) | Procedimiento (`tender.procurementMethodDetails`) |
| `metodo_ocds` | texto | `open`, `selective`, `limited` o `direct` |
| `es_competitivo` | booleano | Procedimiento con competencia abierta o selectiva |
| `es_contratacion_directa` | booleano | Contratación directa (no competitiva) |

### `dim_categoria`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `categoria_key` | entero (PK) | Llave sustituta |
| `categoria_ocds` | texto (único) | `goods`, `services`, `works`, `consultingServices`, `unspecified` |
| `categoria` | texto | Bienes, Servicios, Obras, Consultoría, No especificado |

### `dim_indicador`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `indicador_key` | entero (PK) | Llave sustituta |
| `codigo` | texto (único) | RF01 ... RF07 |
| `nombre`, `descripcion` | texto | Qué mide el indicador |
| `peso` | entero | Puntos que suma al puntaje de riesgo |
| `habilitado` | booleano | Si se calculó en la ejecución |
| `referencia` | texto | Fuente metodológica |

### `fact_proceso`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `proceso_key` | entero (PK) | Llave sustituta |
| `ocid` | texto (único) | Identificador OCDS del proceso |
| `nomenclatura` | texto | `tender.title` (nomenclatura del proceso) |
| `descripcion` | texto | Objeto de la contratación |
| `entidad_key`, `metodo_key`, `categoria_key` | entero (FK) | Dimensiones |
| `fecha_convocatoria_key` | entero (FK) | Fecha de convocatoria → `dim_fecha` |
| `estado` | texto | Estado del proceso (`active`, `complete`, `cancelled`, `unsuccessful`...) |
| `moneda` | texto | Moneda del valor referencial |
| `valor_referencial` | decimal | Valor referencial en su moneda |
| `valor_referencial_pen` | decimal | Valor referencial en soles |
| `n_postores` | entero | Postores distintos (o `numberOfTenderers` si no hay lista) |
| `plazo_presentacion_dias` | entero | Días entre inicio y cierre de presentación de ofertas; nulo si `tenderPeriod` trae inicio = fin |
| `plazo_consultas_dias` | entero | Días del periodo de consultas y observaciones (`tender.enquiryPeriod`) |
| `n_adjudicaciones` | entero | Adjudicaciones válidas |
| `monto_adjudicado_pen` | decimal | Suma de adjudicaciones válidas en soles |
| `ratio_adjudicado_referencial` | decimal | `monto_adjudicado_pen / valor_referencial_pen` |
| `n_alertas` | entero | Indicadores de riesgo activados |
| `puntaje_riesgo` | entero | Suma de pesos de las alertas (0-100) |
| `nivel_riesgo` | texto | Sin alertas, Bajo, Medio, Alto |
| `nivel_riesgo_orden` | entero | 0-3 para ordenar `nivel_riesgo` en visualizaciones |

### `fact_adjudicacion`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `adjudicacion_key` | entero (PK) | Llave sustituta |
| `proceso_key` | entero (FK) | Proceso → `fact_proceso` |
| `ocid`, `award_id` | texto | Identificadores de origen |
| `proveedor_key` | entero (FK) | Proveedor → `dim_proveedor` |
| `entidad_key` | entero | Entidad (referencia; el filtro llega vía `fact_proceso`) |
| `fecha_adjudicacion_key` | entero | Fecha de la buena pro (AAAAMMDD) |
| `estado` | texto | `active`, `pending`, `cancelled`, `unsuccessful` |
| `moneda` | texto | Moneda original |
| `monto_adjudicado`, `monto_adjudicado_pen` | decimal | Monto total de la adjudicación |
| `n_proveedores_adjudicacion` | entero | Proveedores en la adjudicación (consorcio > 1) |
| `monto_asignado_pen` | decimal | Monto prorrateado al proveedor (suma correcta por proveedor) |
| `es_valida` | booleano | No cancelada ni desierta |
| `proveedor_inhabilitado` | booleano | El proveedor tenía una inhabilitación vigente en la fecha |

> Para sumar montos **por proveedor** usa `monto_asignado_pen`; para el **total del proceso** usa
> `fact_proceso[monto_adjudicado_pen]`. Sumar `monto_adjudicado_pen` de esta tabla duplicaría los
> consorcios.

### `fact_contrato`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `contrato_key` | entero (PK) | Llave sustituta |
| `proceso_key` | entero (FK) | Proceso |
| `ocid`, `contract_id`, `award_id` | texto | Identificadores de origen |
| `entidad_key` | entero | Entidad (referencia) |
| `fecha_firma_key` | entero | Fecha de suscripción (AAAAMMDD) |
| `estado` | texto | Estado del contrato; `sin_estado` si la fuente no lo informa |
| `moneda`, `monto_contrato`, `monto_contrato_pen` | texto / decimal | Monto del contrato |
| `fecha_inicio`, `fecha_fin` | fecha | Vigencia del contrato |
| `duracion_dias` | entero | Días de vigencia |
| `tiene_adjudicacion_vinculada` | booleano | `awardID` existe entre las adjudicaciones del proceso |

### `fact_postor`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `postor_key` | entero (PK) | Llave sustituta |
| `proceso_key` | entero (FK) | Proceso |
| `proveedor_key` | entero (FK) | Proveedor |
| `ocid` | texto | Identificador del proceso |
| `es_ganador` | booleano | El postor recibió una adjudicación válida |

### `fact_sancion`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `sancion_key` | entero (PK) | Llave sustituta |
| `proveedor_key` | entero (FK) | Proveedor (vacío si el RUC no es válido) |
| `ruc`, `tipo_sancion`, `resolucion`, `motivo` | texto | Datos de la sanción |
| `fecha_inicio`, `fecha_fin` | fecha | Vigencia (fin vacío = definitiva) |
| `es_definitiva` | booleano | Sin fecha de fin o tipo "definitiva" |
| `vigente_a_fecha_corte` | booleano | Vigente en la fecha de corte de la ejecución |

### `fact_alerta`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `alerta_key` | entero (PK) | Llave sustituta |
| `proceso_key` | entero (FK) | Proceso |
| `indicador_key` | entero (FK) | Indicador → `dim_indicador` |
| `ocid`, `codigo` | texto | Proceso e indicador (RF01...) |
| `detalle` | texto | Explicación legible, p. ej. "Plazo de 6 días (umbral 15)" |

### `agg_entidad_anio`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `entidad_key`, `anio` | entero (PK compuesta) | Entidad y año de convocatoria |
| `n_procesos`, `n_procesos_competitivos` | entero | Volumen |
| `n_postor_unico`, `pct_postor_unico` | entero / decimal | Competencia |
| `monto_adjudicado_pen` | decimal | Monto adjudicado |
| `n_proveedores` | entero | Proveedores distintos adjudicados |
| `hhi` | decimal | Índice Herfindahl-Hirschman de proveedores (0-10 000) |
| `n_alertas`, `n_procesos_riesgo_alto` | entero | Riesgo |

---

## Tablas de machine learning (Fase 2)

No forman parte de la capa gold ni del DDL del pipeline. `contrataciones-ml predict` genera
`pred_monto_esperado` (una fila por proceso de la población, con su monto esperado y su tipo de
desviación) en `data/predictions` y en la base de datos (`sql/ddl_ml`), sin llaves foráneas
hacia la capa gold. Diccionario completo en [Machine learning](11_machine_learning.md#7-salidas).

## Capa silver (`data/processed`)

Tablas limpias, una por entidad del estándar OCDS, con nombres de negocio. Sirven para análisis
exploratorio y para reconstruir la capa gold.

| Tabla | Columnas |
| --- | --- |
| `procesos` | `ocid`, `nomenclatura`, `descripcion`, `estado`, `metodo_ocds`, `metodo_detalle`, `es_competitivo`, `es_contratacion_directa`, `categoria_ocds`, `categoria`, `moneda`, `valor_referencial`, `valor_referencial_pen_fuente`, `valor_referencial_pen`, `fecha_publicacion`, `fecha_inicio_presentacion`, `fecha_fin_presentacion`, `plazo_presentacion_dias`, `fecha_inicio_consultas`, `fecha_fin_consultas`, `plazo_consultas_dias`, `anio`, `n_postores_declarado`, `entidad_id_origen`, `entidad_nombre_origen`, `fecha_release` |
| `partes` | `ocid`, `party_id`, `nombre`, `ruc`, `ruc_valido`, `roles`, `es_comprador`, `es_postor`, `es_proveedor`, `departamento`, `localidad` |
| `postores` | `ocid`, `tenderer_id`, `nombre`, `ruc`, `ruc_valido`, `proveedor_id` |
| `adjudicaciones` | `ocid`, `award_id`, `estado`, `es_valida`, `fecha_adjudicacion`, `moneda`, `monto`, `monto_pen_fuente`, `monto_pen`, `supplier_id`, `nombre`, `ruc`, `ruc_valido`, `proveedor_id`, `n_proveedores_adjudicacion`, `monto_asignado`, `monto_asignado_pen` |
| `contratos` | `ocid`, `contract_id`, `award_id`, `estado`, `fecha_firma`, `moneda`, `monto`, `monto_pen_fuente`, `monto_pen`, `fecha_inicio`, `fecha_fin`, `duracion_dias` |
| `sanciones` | `proveedor_id`, `ruc`, `ruc_valido`, `nombre`, `tipo_sancion`, `fecha_inicio`, `fecha_fin`, `es_definitiva`, `resolucion`, `motivo` |
| `tipo_cambio` | `fecha`, `moneda`, `tipo_cambio`, `fuente` |

Archivos adicionales de la capa silver:

* `reporte_calidad.csv`: resultado de cada regla de calidad.
* `perfil_columnas.csv`: tipo, nulos, valores únicos y un ejemplo por columna.

## Reglas de negocio aplicadas

| Regla | Dónde |
| --- | --- |
| RUC válido = 11 dígitos, prefijo 10/15/16/17/20 y dígito verificador módulo 11 | `cleaner.is_valid_ruc` |
| Fechas OCDS con zona horaria se convierten a hora de Lima | `cleaner.parse_datetime` |
| Valor referencial ≤ 0 = no informado | `cleaner.clean_procesos` |
| Proceso competitivo = método `open`/`selective` y no "directa" | `cleaner.clean_procesos` |
| Adjudicación válida = estado distinto de `cancelled` y `unsuccessful` | `cleaner.clean_adjudicaciones` |
| Monto de consorcio prorrateado en partes iguales | `cleaner.clean_adjudicaciones` |
| Postores deduplicados por proceso y RUC | `cleaner.clean_postores` |
| Montos en moneda extranjera: monto en soles publicado (`amount_PEN`) o, si no hay, × tipo de cambio del día (o último hábil) | `currency.convert_to_pen` |
| Periodo con inicio = fin = plazo no informado (nulo) | `cleaner.clean_procesos` |
| Adjudicación sin estado = válida; contrato sin estado = `sin_estado` | `cleaner.clean_adjudicaciones`, `cleaner.clean_contratos` |
| Proveedor sin RUC con nombre "CONSORCIO ..." = tipo Consorcio | `transformer.build_dim_proveedor` |
