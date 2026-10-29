# Metodología para proyectos de analítica de datos (con ejemplos aplicados)

> Guía paso a paso de cómo abordar un proyecto de analítica de datos en el trabajo real, con el
> caso de **contrataciones públicas del Perú (OECE/SEACE, OCDS)** como ejemplo recurrente.

---

## 1. Entender el problema y las preguntas de negocio

Este primer paso es, con diferencia, el que más errores de carrera evita, porque todo lo que
haces después depende de haberlo hecho bien. La idea central: **nadie te paga por tu código, te
paga por una decisión que ese código permite tomar**. Si no tienes clara esa decisión, puedes
construir un pipeline impecable que responda la pregunta equivocada.

### Qué significa "entender el problema" en concreto

No es solo escuchar el pedido y anotarlo. Es convertir una frase ambigua en una definición
operativa. Compara:

* Pedido tal cual llega: *"necesito ver cómo nos está yendo con los proveedores"*
* Problema bien definido: *"el gerente de compras quiere identificar, antes de fin de mes, qué 10
  proveedores concentran más del 30% del gasto anual, para renegociar contratos en la próxima
  reunión de directorio"*

La segunda versión ya te dice qué calcular, para cuándo, y qué pasa con el resultado. La primera
no te deja empezar a trabajar en serio.

### Preguntas que debes hacer (o hacerte tú mismo si nadie te las responde)

* **¿Qué decisión vas a tomar con esto?** Es la pregunta más importante. Si la respuesta es
  "ninguna en particular, solo quiero ver el dato", es una señal de que el pedido todavía está muy
  crudo.
* **¿Quién va a consumir el resultado y cómo?** Un gerente quiere un número y una conclusión en
  una diapositiva; un analista de otro equipo quiere una tabla para seguir trabajando sobre ella.
  Cambia completamente el entregable.
* **¿Con qué frecuencia se necesita?** ¿Es un análisis puntual o algo que vas a tener que repetir
  cada semana/mes? Si se repite, vale la pena automatizarlo; si es puntual, un notebook rápido
  puede bastar.
* **¿Qué alcance tiene?** Periodo de tiempo, región, categoría, unidad de negocio. Sin esto,
  puedes analizar 5 años cuando solo importaba el último trimestre.
* **¿Ya existen definiciones de las métricas clave?** "Proveedor activo" o "proceso adjudicado"
  pueden significar cosas distintas para distintas personas en la misma empresa. Si asumes una
  definición sin confirmarla, el análisis queda mal desde la raíz.
* **¿De dónde vienen los datos, y ya tienes acceso?** A veces el pedido asume que existe una
  fuente que en realidad no está disponible o tiene huecos.
* **¿Cómo se ve el éxito?** ¿Qué resultado haría que esto se considere útil? A veces ayuda pedir
  un ejemplo de un reporte anterior parecido, aunque sea de otro tema.

### Técnicas útiles

* **Parafrasear y confirmar**: repetir el pedido con tus propias palabras ("entonces lo que
  necesitas es X, para Y, antes de Z, ¿correcto?") antes de empezar. Detecta malentendidos gratis.
* **Pedir un ejemplo concreto**: "¿me puedes mostrar un reporte parecido que ya exista?" revela
  expectativas de formato que nadie te iba a decir en palabras.
* **Los 5 porqués**: si alguien pide un dato, preguntar "¿para qué lo necesitas?" una o dos veces
  más de lo que se siente natural, suele destapar el problema de negocio real detrás del pedido
  técnico.

### Ejemplo aplicado: contrataciones públicas

Imagina que trabajas en control interno y tu jefe te dice: *"revisa los datos de contrataciones y
dime si hay algo raro"*. Después de preguntar, descubres: la decisión es derivar casos a
auditoría; el consumidor es un equipo de auditores (no el público); la frecuencia es mensual; el
alcance real es un departamento y periodo específicos, no todo el Perú desde siempre; "raro" se
traduce en indicadores concretos (postor único, plazos cortos, proveedores sancionados,
concentración de gasto); el éxito es una lista corta (20-30 casos), no miles de alertas sin
priorizar. El problema bien definido queda:

> *"El equipo de control interno necesita, cada mes, una lista priorizada (máximo 30-50 casos) de
> procesos de contratación pública con señales de riesgo (postor único, plazos cortos,
> sobrecostos, proveedores sancionados, concentración de gasto), exportable a Excel, para derivar
> los casos más fuertes a auditoría."*

Esa frase ya dicta el diseño del indicador de riesgo, el modelo de datos y el formato del
entregable.

### El resultado de esta etapa

No es código, es un documento corto (puede ser un párrafo en un ticket, no necesita ser formal)
que deja por escrito: la pregunta de negocio, el alcance, el entregable esperado, la frecuencia, y
los criterios de éxito.

### El riesgo de saltarte este paso

Es la causa número uno de retrabajo: construir el pipeline completo y que, al mostrarlo, la
persona diga "ah, no, yo necesitaba esto por región, no por entidad". Cuando el pedido es caro de
rehacer o ambiguo, vale la pena frenar y preguntar antes de escribir una sola línea.

---

## 2. Mapear las fuentes de datos

Este paso es donde la teoría del paso 1 choca con la realidad. Puedes tener clarísimo qué
pregunta de negocio responder, pero si no exploras bien los datos antes de diseñar el pipeline, te
vas a topar con sorpresas a mitad de camino que te obligan a rehacer medio proyecto. La idea
central: **nunca diseñes el modelo de datos antes de haber mirado los datos reales**, aunque
tengas documentación oficial de por medio — la documentación casi nunca coincide al 100% con lo
que realmente llega.

### Qué significa "mapear las fuentes" en concreto

No es solo anotar "los datos están en tal API". Es responder, para cada fuente, qué forma tiene
exactamente, qué tan completa y confiable es, y qué vas a tener que compensar en el código porque
la fuente no te lo da limpio. Compara:

* Mapeo superficial: *"los datos de contrataciones están en el portal del OECE, en formato OCDS"*
* Mapeo real: *"hay dos formas de obtener los datos — descarga masiva anual (completa pero
  desactualizada) y una API paginada (reciente pero con límites de página); el estándar OCDS
  define `tenderPeriod` como el plazo de presentación, pero en la práctica el 95% de los registros
  tienen `startDate == endDate`, así que el plazo real está en `enquiryPeriod`; el RUC del
  proveedor casi nunca viene en el campo principal, está escondido en `additionalIdentifiers`; los
  consorcios no tienen RUC propio, solo un código interno de 7 dígitos"*

La primera versión te deja diseñar un modelo que se rompe en la primera corrida con datos reales.
La segunda es exactamente lo que se descubre al revisar muestras reales de la fuente.

### Preguntas que debes hacer (o investigar tú mismo)

* **¿Qué formas de acceso existen?** Archivo descargable, API, base de datos, Excel manual. A
  veces hay varias, y cada una tiene ventajas distintas (completitud vs. actualidad).
* **¿Qué tan actualizada está cada fuente?** Una descarga masiva puede tener meses de atraso; una
  API puede tener solo los últimos 2-3 meses.
* **¿El dato real coincide con la documentación oficial?** Casi nunca al 100%. Hay que conseguir
  una muestra real y mirarla campo por campo.
* **¿Qué campos están casi siempre vacíos o mal poblados?** Los estados de adjudicación y contrato
  pueden venir vacíos en la mayoría de los registros; el postor del proceso a veces no está en el
  campo "oficial" sino que hay que buscarlo en otro lado.
* **¿Hay límites técnicos de la fuente?** Paginación, límite de requests por minuto, tamaño máximo
  de descarga, autenticación.
* **¿Qué identificadores usa la fuente para relacionar entidades?** El identificador "obvio"
  (como el RUC) puede faltar en muchos casos y necesitar una llave alternativa de respaldo.
* **¿Qué calidad tiene el dato de verdad?** Duplicados, nulos, inconsistencias de formato de
  fecha, monedas mezcladas.
* **¿Hay alguna fuente secundaria necesaria para enriquecer el análisis?** Tipo de cambio,
  padrones de sanciones, catálogos de referencia.

### Técnicas útiles

* **Pedir o conseguir una muestra real antes de programar nada.**
* **Hacer un "data profiling" rápido**: contar nulos por columna, valores únicos, rangos de
  fechas, antes de diseñar el esquema.
* **Probar los límites de la API a mano** (Postman, curl, un script simple) antes de escribir el
  cliente definitivo.
* **Desconfiar de los campos "casi siempre llenos"**: si el 95% de los registros tienen un patrón
  raro, asume que es el comportamiento normal de la fuente, no un error aislado.

### Ejemplo aplicado: contrataciones públicas

El estándar OCDS, en teoría, define `tender.tenderers` como la lista de postores y
`tenderPeriod` como el plazo de presentación de ofertas. Al revisar muestras reales del OECE se
descubrió que: el RUC de la entidad vive en `additionalIdentifiers`, no en el campo principal; el
plazo de presentación casi siempre tiene inicio = fin (el plazo real está en `enquiryPeriod`); los
consorcios ganadores no tienen RUC, solo un código interno; y en varios procesos `tender.tenderers`
viene vacío, obligando a tomar los postores desde `parties` filtrando por rol. Ese hallazgo obligó
a rediseñar el aplanador de datos y la lógica de llaves antes de poder confiar en el modelo.

### El resultado de esta etapa

Un documento que detalla, por cada fuente: cómo se accede, qué forma real tiene el dato, qué
particularidades o problemas conocidos tiene, y qué se va a tener que resolver en el código de
limpieza.

### El riesgo de saltarte este paso

Diseñas el modelo de datos, escribes el pipeline completo, y a la primera corrida con datos reales
todo se rompe: fechas que no parsean, llaves que no cruzan, montos que no cuadran porque asumiste
una sola moneda.

---

## 3. Diseñar la estructura del proyecto

La idea central: **el código que no tiene una estructura clara se vuelve imposible de mantener
en semanas, no en años**. Diseñar la estructura antes de escribir lógica evita que termines con un
solo script de 2,000 líneas donde nadie (ni tú mismo en 3 meses) puede ubicar nada.

### Qué significa "diseñar la estructura" en concreto

* Estructura pobre: un solo notebook o script que hace todo: descarga, limpia, calcula y exporta
  en el mismo bloque de código, sin separación.
* Estructura bien pensada: capas separadas — **ingesta** (trae los datos crudos), **procesamiento**
  (limpia, valida, transforma), **export** (entrega el resultado) — con una carpeta `utils` para lo
  transversal (logging, configuración) y un punto de entrada (`pipeline.py` + `cli.py`) que
  orquesta todo sin mezclar responsabilidades.

### Decisiones que debes tomar

* **¿Qué arquitectura de capas de datos usar?** La más común en la industria es la arquitectura
  "medallion": bronce (datos crudos, sin tocar) → plata (datos limpios) → oro (modelo listo para
  análisis). Separar estas capas en carpetas distintas (`data/raw`, `data/processed`,
  `data/curated`) evita que una transformación mal hecha contamine el dato original.
  * Puedes profundizar en esta arquitectura cuando quieras — hay más matices sobre por qué se
    separa en tres capas y no menos.
* **¿Cómo se organiza el código?** Por capas (`ingestion/`, `processing/`, `export/`), para que
  cada módulo tenga una sola responsabilidad y las pruebas sean más simples.
* **¿Dónde van las configuraciones?** Nunca mezcladas con el código: rutas, umbrales, URLs de API
  van en archivos de configuración (YAML, `.env`), para poder cambiar comportamiento sin tocar
  lógica.
* **¿Qué convenciones de nombres se usan?** Nombres de columnas, de archivos, de funciones,
  consistentes en todo el proyecto.

### Ejemplo aplicado: contrataciones públicas

La estructura que armamos separó `ingestion` (API, descarga masiva, Excel de sanciones, tipo de
cambio), `processing` (aplanado del OCDS, limpieza, calidad, moneda, modelo gold, indicadores de
riesgo) y `export` (Parquet/CSV, Excel, carga a base de datos), orquestados por `pipeline.py` y
expuestos por `cli.py`. Esto permitió, por ejemplo, que cuando descubrimos las particularidades
reales del OECE (paso 2), solo tuviéramos que tocar `cleaner.py` y `ocds_flattener.py` — el resto
del proyecto (exportación, base de datos, Power BI) no se vio afectado porque no sabe nada sobre
la forma cruda de los datos.

### El resultado de esta etapa

Un esqueleto de carpetas y archivos (puede estar vacío o con ejemplos mínimos) más un README que
explica qué va en cada carpeta y por qué.

### El riesgo de saltarte este paso

Terminas con un proyecto donde cambiar una sola regla de negocio obliga a tocar código de ingesta,
de limpieza y de exportación al mismo tiempo, porque todo está mezclado — y cada cambio se vuelve
riesgoso.

---

## 4. Configurar el entorno de trabajo

La idea central: **"en mi máquina funciona" no es un estándar aceptable en un trabajo real**. Si
otra persona (o tú mismo en otra computadora) no puede levantar el proyecto en minutos siguiendo
instrucciones claras, el proyecto no está realmente terminado.

### Qué significa "configurar el entorno" en concreto

* Entorno mal gestionado: dependencias instaladas globalmente, sin registro de versiones; secretos
  (contraseñas, tokens de API) escritos directo en el código.
* Entorno bien gestionado: un entorno virtual aislado con las versiones exactas de cada librería
  registradas; secretos solo en un archivo `.env` que nunca se sube al control de versiones;
  configuración por ambiente (desarrollo, producción) separada del código.

### Decisiones que debes tomar

* **¿Qué gestor de entorno usar?** `venv`, `conda`, `poetry`, según el ecosistema del equipo.
* **¿Cómo se registran las dependencias?** Un archivo de dependencias con versiones fijadas, para
  que la instalación sea reproducible.
* **¿Dónde van los secretos?** Nunca en el código ni en un archivo versionado. Un `.env` (ignorado
  por Git) con un `.env.example` como plantilla pública.
* **¿Se necesita Git desde el día uno?** Sí, casi siempre — aunque el proyecto sea pequeño,
  empezar sin control de versiones es una decisión que casi siempre se termina lamentando.

### Ejemplo aplicado: contrataciones públicas

El proyecto usa un entorno virtual de Python con `pip install -e ".[dev]"`, un `.env.example` que
documenta qué variables se necesitan (endpoint de la API, credenciales de base de datos) sin
exponer valores reales, y Git desde el inicio con un `.gitignore` que excluye datos generados y
el `.env` real.

### El resultado de esta etapa

Un entorno que cualquier persona nueva puede levantar siguiendo 3-4 comandos documentados en el
README, sin tener que preguntarte nada.

### El riesgo de saltarte este paso

Alguien (incluido tú mismo en el futuro) no puede reproducir el proyecto; se filtran credenciales
al subir el código a un repositorio público; una actualización silenciosa de una librería rompe
el proyecto sin aviso.

---

## 5. Ingesta (capa bronce)

La idea central: **la capa bronce es tu red de seguridad**. Si guardas el dato crudo tal cual
llegó, siempre puedes rehacer cualquier transformación posterior sin tener que volver a golpear la
fuente original (que puede caerse, cambiar, o tener límites de uso).

### Qué significa "ingesta en capa bronce" en concreto

* Mal hecho: procesar y transformar el dato en el mismo paso en que lo descargas, sin guardar el
  original.
* Bien hecho: guardar el dato exactamente como llega (JSON, CSV, lo que sea), sin tocarlo, en una
  carpeta de "crudos", y solo después, en un paso separado, leer esos archivos crudos para
  limpiarlos.

### Decisiones que debes tomar

* **¿Cómo se identifican los archivos crudos?** Con fecha o lote de descarga, para poder rastrear
  cuándo se obtuvo cada dato.
* **¿Qué pasa si la fuente falla a mitad de la descarga?** Diseñar reintentos y continuar desde
  donde se cortó, en vez de perder todo el progreso.
* **¿Se versiona o se sobrescribe el dato crudo?** Normalmente se acumula (nunca se borra ni se
  modifica una vez guardado), para poder auditar o reprocesar después.

### Ejemplo aplicado: contrataciones públicas

El cliente de la API del OECE pagina resultados por mes (`dataSegmentationID`), guarda cada página
cruda como un archivo JSON en `data/raw/api/`, con reintentos ante errores de red, y avisa si se
alcanzó el límite de páginas configurado sin haber llegado al final. Esto permite reprocesar los
datos crudos sin tener que volver a golpear la API si, por ejemplo, se encuentra un error en la
lógica de limpieza después.

### El resultado de esta etapa

Un conjunto de archivos crudos, fieles a la fuente, organizados y trazables, listos para ser leídos
por la siguiente capa sin necesidad de volver a consultar la fuente original.

### El riesgo de saltarte este paso

Si mezclas descarga y transformación, cualquier error en tu lógica de limpieza te obliga a volver a
descargar todo desde la fuente (que puede tener límites de uso, estar caída, o haber cambiado) solo
para poder reprocesar.

---

## 6. Limpieza y control de calidad (capa plata)

La idea central: **los datos de origen casi nunca están listos para analizar tal cual llegan**, y
"limpiar a ojo" sin medir sistemáticamente los problemas te deja ciego ante errores que después
invalidan todo el análisis.

### Qué significa "limpieza y calidad" en concreto

* Mal hecho: corregir algunos valores que "se ven mal" sin un criterio documentado ni medición de
  cuántos registros tenían el problema.
* Bien hecho: normalizar tipos y formatos de forma sistemática (fechas, montos, nombres), y además
  **medir y reportar** cuántos registros tenían cada tipo de problema (nulos, duplicados,
  inconsistencias), para que la calidad del dato sea visible, no una caja negra.

### Decisiones que debes tomar

* **¿Qué transformaciones son de limpieza y cuáles son de negocio?** La limpieza corrige formato
  (una fecha mal escrita sigue siendo la misma fecha); las reglas de negocio vienen en el paso 8 y
  no deben mezclarse aquí.
* **¿Qué hacer con los valores faltantes o inválidos?** Decidir, por campo, si se deja nulo, se
  infiere, o se descarta el registro — y documentar esa decisión.
* **¿Cómo se clasifican los problemas de calidad?** Por severidad (error que invalida el registro,
  advertencia que hay que revisar, informativo que solo documenta un patrón conocido).
* **¿Se corrige el dato en el momento, o solo se reporta el problema?** A veces es mejor dejar el
  problema visible en un reporte de calidad en vez de "arreglarlo" silenciosamente y esconder una
  señal importante.

### Ejemplo aplicado: contrataciones públicas

El proyecto tiene 27 reglas de calidad documentadas (con severidad ERROR/ADVERTENCIA/INFO), que
revisan cosas como: montos referenciales en cero, fechas de adjudicación anteriores a la
publicación, RUC con dígito verificador inválido, plazos de presentación no informados (inicio =
fin, un patrón real de la fuente, no un error — por eso es severidad INFO y no ERROR). Todo esto se
resume en un reporte de calidad exportado, no se "arregla" silenciosamente.

### El resultado de esta etapa

Datos limpios y consolidados, listos para el modelado, acompañados de un reporte explícito de
calidad que dice qué tan confiable es cada parte del dato.

### El riesgo de saltarte este paso

Construyes indicadores y reportes sobre datos con errores invisibles — fechas mal parseadas,
duplicados, montos en la moneda equivocada — y las conclusiones del análisis quedan comprometidas
sin que nadie lo note hasta que alguien pregunta por qué un número no tiene sentido.

---

## 7. Modelado analítico (capa oro)

La idea central: **un modelo pensado para el negocio es distinto de un modelo pensado para la
fuente de datos**. La capa oro traduce conceptos técnicos de la fuente (identificadores, campos
anidados) a conceptos que el usuario de negocio reconoce (entidades, proveedores, procesos,
montos).

### Qué significa "modelado analítico" en concreto

* Mal hecho: entregar las tablas limpias tal cual, con la misma estructura anidada o normalizada
  de la fuente, obligando a quien consuma el dato a hacer cruces complicados cada vez.
* Bien hecho: un modelo pensado para consultarse fácil, típicamente un **esquema estrella**: tablas
  de "hechos" (lo que pasó: un proceso, una adjudicación, un contrato) conectadas a tablas de
  "dimensiones" (quién, cuándo, con qué método), con identificadores simples (llaves surrogadas) en
  vez de los identificadores complejos de la fuente original.

### Decisiones que debes tomar

* **¿Qué es un "hecho" y qué es una "dimensión" en este negocio?** Los hechos son eventos o
  transacciones medibles (un proceso de compra); las dimensiones son el contexto que lo describe
  (la entidad compradora, la fecha, el método de contratación).
  * Si quieres, podemos profundizar en cómo decidir qué tabla es hecho y cuál es dimensión, con más
    ejemplos.
* **¿Qué granularidad tiene cada hecho?** Un registro por proceso, o por cada postor dentro de un
  proceso — cambia completamente las agregaciones posteriores.
* **¿Qué pasa con identificadores inconsistentes de la fuente?** Diseñar llaves propias
  (surrogadas) que no dependan de que la fuente tenga un identificador único y confiable para
  todo.
* **¿Qué agregaciones conviene precalcular?** Totales por año, por entidad, índices de
  concentración — si el usuario los va a pedir seguido, vale la pena calcularlos una vez en el
  pipeline, no cada vez que alguien abre el dashboard.

### Ejemplo aplicado: contrataciones públicas

El modelo gold tiene 13 tablas: dimensiones (fecha, entidad, proveedor, método, categoría,
indicador) y hechos (proceso, adjudicación, contrato, postor, sanción, alerta), más una tabla
agregada por entidad y año con el índice de concentración HHI. La llave de proveedor no es
simplemente el RUC (porque muchos proveedores reales no tienen uno publicado), sino una llave
propia que cae en cascada: RUC válido → código de la fuente → nombre normalizado — así, dos
registros del mismo proveedor sin RUC no se separan por error, pero tampoco se fusionan dos
proveedores distintos que casualmente no tienen RUC.

### El resultado de esta etapa

Un conjunto de tablas pensadas para responder las preguntas de negocio directamente, sin que quien
las consuma tenga que entender la estructura original de la fuente.

### El riesgo de saltarte este paso

Entregas datos técnicamente limpios pero difíciles de usar: el usuario de negocio (o tú mismo en
Power BI) tiene que hacer cruces complejos cada vez que quiere una respuesta simple, y los reportes
se vuelven lentos y propensos a error.

---

## 8. Reglas de negocio e indicadores

La idea central: **el conocimiento del dominio que vive solo en la cabeza de un experto no sirve
de nada si no se convierte en una regla ejecutable, configurable y documentada**.

### Qué significa "reglas de negocio e indicadores" en concreto

* Mal hecho: escribir directamente en el código cosas como `if dias < 15:` sin explicar de dónde
  sale ese número, y sin forma de ajustarlo sin tocar código.
* Bien hecho: los umbrales y criterios de negocio viven en un archivo de configuración aparte
  (editable sin programar), y el código solo lee esa configuración y aplica la lógica.

### Decisiones que debes tomar

* **¿Qué patrones de negocio hay que detectar?** Normalmente salen directo del paso 1 (qué
  significaba "raro", "riesgoso", "VIP", etc. en la pregunta original).
* **¿Los criterios son fijos o deben poder ajustarse sin tocar código?** Casi siempre lo segundo:
  los umbrales cambian con el tiempo o según quién los revise.
* **¿Cómo se combina más de una señal en un solo puntaje?** Si hay varios indicadores, hay que
  decidir cómo se pesan y se suman (o no) en un resultado único y priorizable.
* **¿Qué pasa cuando dos reglas se contradicen o se solapan?** Definir explícitamente la
  prioridad o la forma de combinarlas.

### Ejemplo aplicado: contrataciones públicas

Los 7 indicadores de riesgo (postor único, plazo corto, adjudicación cercana al 100% del
referencial, sobrecosto, contratación directa, proveedor sancionado, concentración
proveedor-entidad) tienen sus umbrales en un archivo YAML editable, cada uno con un peso, y se
suman en un puntaje de 0 a 100 con niveles (Sin alertas, Bajo, Medio, Alto). Uno de los
indicadores (el de plazo corto) incluso se puede configurar para evaluar uno de dos campos
distintos según qué tan confiable sea cada uno en los datos reales — ese ajuste se hace en
configuración, sin tocar el código.

### El resultado de esta etapa

El modelo de datos enriquecido con las reglas específicas del negocio, con los criterios visibles
y ajustables en configuración, no escondidos en el código.

### El riesgo de saltarte este paso

Cada vez que cambia un umbral de negocio hay que modificar y volver a desplegar código; nadie fuera
del equipo técnico puede entender ni ajustar los criterios; las reglas quedan dispersas y
duplicadas en distintas partes del proyecto.

---

## 9. Pruebas automatizadas

La idea central: **sin pruebas, cada cambio es un salto de fe**. En un proyecto que vas a mantener
en el tiempo (no uno de usar y tirar), las pruebas son lo que te permite cambiar código con
confianza en vez de miedo.

### Qué significa "pruebas automatizadas" en concreto

* Mal hecho: probar manualmente que "el pipeline corrió sin errores" mirando la consola, sin
  verificar que los números calculados sean correctos.
* Bien hecho: pruebas que verifican casos concretos y conocidos ("con esta entrada, el resultado
  debe ser exactamente este"), que corren automáticamente y que fallan de forma clara cuando algo
  se rompe.

### Decisiones que debes tomar

* **¿Qué se prueba a nivel de función individual?** Casos puntuales de cada transformación (una
  fecha mal formada, un RUC inválido, un valor nulo).
* **¿Qué se prueba a nivel de pipeline completo?** Que, de principio a fin, con datos de ejemplo,
  el resultado final sea el esperado.
* **¿Cómo se prueban las dependencias externas (APIs, bases de datos)?** Simulando sus respuestas,
  para que las pruebas no dependan de que la fuente esté disponible ni cambien si la fuente cambia
  sin que te enteres.
* **¿Qué casos "raros" de datos reales conviene fijar como prueba?** Cada particularidad extraña
  que descubras en el paso 2 merece su propia prueba, para que si alguien cambia el código sin
  saber de esa particularidad, la prueba avise.

### Ejemplo aplicado: contrataciones públicas

Hay un archivo de pruebas dedicado exclusivamente a las particularidades reales del OECE
descubiertas en el paso 2 (RUC en un campo secundario, plazos con inicio = fin, consorcios sin
RUC, postores solo en un campo alternativo). Si en el futuro alguien simplifica el código de
limpieza sin saber por qué esos casos están ahí, esas pruebas específicas van a fallar y van a
señalar exactamente qué se rompió.

### El resultado de esta etapa

Un conjunto de pruebas que corre en segundos y da confianza de que el pipeline sigue haciendo lo
que se espera, incluso después de meses sin tocarlo.

### El riesgo de saltarte este paso

Cada cambio de código es un riesgo silencioso: puedes romper un cálculo que ya funcionaba y no
enterarte hasta que alguien, meses después, encuentra un número que no tiene sentido.

---

## 10. Entrega al usuario final

La idea central: **el análisis más brillante no sirve de nada si no llega en el formato y canal
que la persona realmente va a usar**. Esto se decide en el paso 1 (quién consume, cómo), y aquí se
ejecuta.

### Qué significa "entrega" en concreto

* Mal hecho: entregar una tabla técnica o un archivo que el usuario final no sabe abrir ni
  interpretar.
* Bien hecho: el mismo modelo de datos alimentando el canal que la persona ya usa en su día a día
  — un dashboard interactivo para gerencia, un Excel con tablas ya armadas para un analista, una
  base de datos consultable para otro sistema.

### Decisiones que debes tomar

* **¿Qué canal(es) necesita el usuario?** Puede ser más de uno: un dashboard para revisión
  ejecutiva y, en paralelo, un Excel detallado para quien investiga caso por caso.
* **¿El entregable necesita explicación adicional?** Un reporte con indicadores de riesgo necesita
  dejar claro que son señales para priorizar revisión, no conclusiones definitivas.
* **¿Cómo se actualiza el entregable en el tiempo?** Si el análisis se repite, automatizar también
  la entrega (no solo el cálculo), para no depender de que alguien lo genere a mano cada vez.

### Ejemplo aplicado: contrataciones públicas

El mismo modelo gold alimenta tres salidas distintas desde un solo pipeline: archivos para Power BI
(para quien quiere explorar visualmente), un reporte Excel con tablas ya armadas (rankings,
alertas) para revisión directa, y una base de datos SQL con vistas y consultas predefinidas (para
quien prefiere consultar directamente). El reporte Excel incluye notas explícitas aclarando que las
alertas de riesgo son señales para priorizar revisión, no pruebas de irregularidad.

### El resultado de esta etapa

Un entregable que el usuario final puede abrir, entender y usar sin depender de que tú le
expliques cada vez cómo interpretarlo.

### El riesgo de saltarte este paso

Construyes un modelo de datos excelente que nadie usa porque llega en un formato que no es el que
la persona esperaba, o sin el contexto necesario para interpretarlo correctamente.

---

## 11. Documentación

La idea central: **un proyecto que solo tú entiendes no es un proyecto profesional, es una caja
negra con fecha de caducidad** — el día que te vayas de vacaciones, cambies de equipo, o vuelvas a
tocarlo en seis meses, la documentación es lo único que te salva.

### Qué significa "documentación" en concreto

* Mal hecho: comentarios sueltos en el código, si acaso, y ningún documento que explique el
  panorama general.
* Bien hecho: un README que explica propósito y cómo usar el proyecto, un diccionario de datos que
  explica qué significa cada tabla y columna, una explicación de cómo interpretar cada indicador, y
  un registro de cambios.

### Decisiones que debes tomar

* **¿Qué nivel de documentación necesita cada audiencia?** Alguien que solo va a usar el reporte
  final necesita mucho menos detalle que alguien que va a modificar el pipeline.
* **¿Qué debe vivir en el código (docstrings) y qué en documentos aparte?** El código documenta el
  "cómo"; los documentos aparte documentan el "qué" y el "por qué", que no siempre es obvio
  leyendo la implementación.
* **¿Cómo se mantiene la documentación actualizada?** Decidir que ningún cambio relevante se
  considera terminado hasta que la documentación también se actualiza.

### Ejemplo aplicado: contrataciones públicas

El proyecto tiene documentación separada por tema (arquitectura, fuentes de datos, modelo de
datos, calidad, indicadores de riesgo), incluyendo una sección específica dedicada únicamente a las
particularidades reales de la fuente de datos descubiertas en el paso 2 — para que la próxima
persona (o tú mismo en el futuro) no tenga que volver a descubrirlas desde cero revisando datos
crudos.

### El resultado de esta etapa

Un proyecto que otra persona (o tú mismo, meses después) puede entender y retomar sin tener que
preguntarte nada ni leer todo el código línea por línea.

### El riesgo de saltarte este paso

El conocimiento del proyecto vive solo en tu cabeza; cualquier ausencia tuya (vacaciones, cambio de
trabajo) deja al equipo sin forma de mantener o explicar lo que se construyó.

---

## 12. Mantenimiento y flujo de trabajo continuo

La idea central: **un proyecto de analítica real rara vez está "terminado"** — las fuentes
cambian, piden nuevos indicadores, aparecen casos nuevos de datos raros. El proyecto necesita un
proceso ordenado para evolucionar sin romperse cada vez.

### Qué significa "mantenimiento y flujo de trabajo" en concreto

* Mal hecho: cada cambio se hace directo sobre la versión en uso, sin revisión, sin pruebas previas,
  cruzando los dedos para que no se rompa nada.
* Bien hecho: cambios en ramas separadas, con pruebas corriendo automáticamente antes de
  integrarlos, y un proceso claro para agregar algo nuevo (una fuente, un indicador) sin tener que
  reinventar la estructura cada vez.

### Decisiones que debes tomar

* **¿Qué flujo de ramas se usa?** Una rama estable y ramas de trabajo por cambio, que se integran
  solo después de revisión y pruebas.
* **¿Se automatiza la verificación de cada cambio?** Integración continua que corre pruebas y
  revisa el estilo del código en cada cambio propuesto, antes de que se integre.
* **¿Cómo se documenta cada versión del proyecto?** Un registro de cambios que diga, en cada
  versión, qué se agregó, qué se corrigió y qué cambió de forma que pueda afectar a quien ya lo usa.
* **¿Qué pasa cuando aparece un caso nuevo de dato raro?** Tener un proceso claro: agregar primero
  la prueba que describe el caso, luego el código que lo maneja, luego la documentación — en ese
  orden.

### Ejemplo aplicado: contrataciones públicas

El proyecto tiene un flujo de Git documentado (rama por cambio, pruebas y estilo de código
verificados antes de integrar, mensajes de commit con un formato estándar) y una integración
continua que corre las pruebas con dos bases de datos distintas en cada cambio propuesto. La regla
explícita para extender el proyecto es: si aparece una particularidad nueva en datos reales, se
agrega primero como caso de prueba en el archivo dedicado a eso, y solo después se ajusta el código
— así el comportamiento quedó siempre documentado por una prueba, no solo por memoria de quien lo
escribió.

### El resultado de esta etapa

Un proyecto que puede evolucionar de forma segura: agregar un indicador nuevo, una fuente nueva, o
corregir un caso raro de datos, sin arriesgar romper silenciosamente lo que ya funcionaba.

### El riesgo de saltarte este paso

Cada cambio nuevo es una apuesta: puede romper algo que funcionaba sin que nadie lo note hasta que
el reporte le llega mal a alguien, y con el tiempo nadie se atreve a tocar el proyecto por miedo a
romperlo.
