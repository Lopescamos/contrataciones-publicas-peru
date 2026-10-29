# Glosario

## Contrataciones públicas (Perú)

> Definiciones generales. Los procedimientos, sus nombres y montos dependen de la norma vigente en
> la fecha de cada proceso: Ley N.° 30225 hasta abril de 2025 y Ley N.° 32069 desde entonces. Los
> datos históricos incluyen procedimientos de ambos marcos.

| Término | Definición |
| --- | --- |
| **Adjudicación (buena pro)** | Decisión que otorga el contrato a un postor. En OCDS: `awards` |
| **Adjudicación simplificada** | Procedimiento de selección para montos intermedios, con plazos más cortos que una licitación |
| **Comparación de precios** | Procedimiento para bienes y servicios comunes de disponibilidad inmediata |
| **Concurso público** | Procedimiento para contratar servicios (incluida consultoría) |
| **Consorcio** | Agrupación de proveedores que postulan juntos. En la publicación del OECE aparece como un solo proveedor con un código interno de 7 dígitos (sin RUC propio) y sin el detalle de sus integrantes |
| **Contratación directa** | Procedimiento sin competencia, permitido en supuestos definidos por la ley |
| **Entidad** | Organismo público que contrata (ministerio, gobierno regional, municipalidad, etc.) |
| **Inhabilitación** | Sanción del Tribunal que impide contratar con el Estado de forma temporal o definitiva |
| **Ley N.° 32069** | Ley General de Contrataciones Públicas, vigente desde el 22 de abril de 2025 |
| **Licitación pública** | Procedimiento para bienes y obras de mayor monto |
| **Nomenclatura** | Código del procedimiento (por ejemplo `AS-SM-52-2024-ENTIDAD-1`) |
| **OECE** | Organismo Especializado para las Contrataciones Públicas Eficientes; reemplazó al OSCE |
| **OSCE** | Organismo Supervisor de las Contrataciones del Estado (denominación anterior) |
| **Postor** | Proveedor que presenta una oferta en un procedimiento |
| **RNP** | Registro Nacional de Proveedores |
| **RUC** | Registro Único de Contribuyentes (SUNAT): 11 dígitos, prefijo 10 (persona natural) o 20 (persona jurídica) y dígito verificador |
| **SEACE** | Sistema Electrónico de Contrataciones del Estado, donde se registran los procesos |
| **Subasta inversa electrónica** | Procedimiento para bienes y servicios comunes donde gana el menor precio |
| **Tribunal de Contrataciones Públicas** | Órgano que resuelve controversias e impone sanciones a proveedores |
| **UIT** | Unidad Impositiva Tributaria; referencia para montos mínimos de los procedimientos |
| **Valor referencial / estimado** | Monto que la entidad estima para la contratación. En OCDS: `tender.value` |

## Estándar OCDS

| Término | Definición |
| --- | --- |
| **OCDS** | *Open Contracting Data Standard*: modelo de datos internacional para publicar contrataciones |
| **OCID** | Identificador único de un proceso de contratación (prefijo del publicador + id) |
| **Release** | Publicación de información sobre un proceso en un momento dado (por etapa) |
| **Record / release compilado** | Fusión de todos los releases de un proceso: su foto más reciente y completa |
| **Package** | Contenedor JSON de releases (`releases`) o records (`records`) |
| **additionalIdentifiers** | Identificadores adicionales de una organización; el OECE publica ahí el RUC de las entidades |
| **dataSegmentation** | Extensión del OECE: mes de inicio de la convocatoria (`AAAA-MM`) con que se segmentan los datos y se consulta la API |
| **enquiryPeriod** | Periodo de formulación de consultas y observaciones de una convocatoria |
| **PE-CONSUCODE** | Esquema de identificadores con que el OECE identifica a las entidades (código propio, no el RUC) |
| **tenderPeriod** | Periodo de presentación de ofertas; en la publicación del OECE suele traer solo la fecha de convocatoria |
| **parties** | Organizaciones que participan en el proceso, con sus `roles` |
| **tender / awards / contracts** | Etapas de convocatoria, adjudicación y contrato |
| **procurementMethod** | Clasificación del estándar: `open`, `selective`, `limited`, `direct` |
| **Red flag** | Indicador de riesgo calculado a partir de los datos |

## Datos y analítica

| Término | Definición |
| --- | --- |
| **Arquitectura medallion** | Organización de datos en capas bronze (crudo), silver (limpio) y gold (listo para consumo) |
| **Dimensión / hecho** | En un esquema estrella: tablas descriptivas (quién, qué, cuándo) y tablas de eventos medibles |
| **ETL** | *Extract, Transform, Load*: extraer, transformar y cargar datos |
| **Esquema estrella** | Modelo con una tabla de hechos central rodeada de dimensiones |
| **Full refresh** | Estrategia de carga que reemplaza todo el contenido de las tablas |
| **HHI** | Índice Herfindahl-Hirschman: suma de los cuadrados de las participaciones; mide concentración |
| **Idempotente** | Que ejecutarlo varias veces produce el mismo resultado |
| **Llave natural / sustituta** | Identificador de negocio (RUC) frente a un entero generado para relacionar tablas |
| **Parquet** | Formato de archivo columnar, comprimido y tipado |
| **Upsert** | Insertar o actualizar según exista la llave |

## Machine learning (Fase 2)

| Término | Definición |
| --- | --- |
| **Canario de fuga** | Prueba con un objetivo de ruido puro: si un modelo lo "predice", alguna variable contiene el resultado |
| **Escala robusta (MAD)** | 1.4826 x la mediana de las desviaciones absolutas respecto de la mediana; resiste valores extremos |
| **Fuga de datos** (*data leakage*) | Usar como variable información que solo se conoce después del hecho que se predice |
| **Línea base** | Modelo simple de referencia (aquí, la mediana de la razón por método y categoría) que un modelo debe superar |
| **Monto esperado** | Estimación de cuánto debería adjudicarse un proceso según su perfil al convocarse |
| **Predicción fuera de muestra** | Predicción de un dato con un modelo que no lo usó para entrenar |
| **Sobrecosto / subcosto inusual** | Monto adjudicado muy por encima o por debajo del esperado (z robusto y desviación mínima) |
| **TargetEncoder** | Codifica una categoría con muchos valores (la entidad) por el promedio del objetivo, aprendido solo del entrenamiento |
| **Validación temporal** | Entrenar con el pasado y evaluar con el futuro, como ocurre en la práctica |
| **z robusto** | Distancia al centro del segmento medida en escalas robustas |
