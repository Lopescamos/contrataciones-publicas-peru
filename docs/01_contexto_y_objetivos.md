# 1. Contexto y objetivos

## El problema

Las entidades públicas del Perú compran bienes, servicios y obras mediante procedimientos de
selección registrados en el **SEACE** (Sistema Electrónico de Contrataciones del Estado). Desde
el 22 de abril de 2025 rige la **Ley N.° 32069**, Ley General de Contrataciones Públicas, y el
organismo rector pasó a ser el **OECE** (Organismo Especializado para las Contrataciones Públicas
Eficientes), que reemplazó al OSCE.

Según información oficial difundida al aprobarse el reglamento de organización del OECE, más de
3 200 entidades movilizan alrededor de S/ 86 mil millones al año en contrataciones, cerca del
36 % del presupuesto nacional, con más de 1,8 millones de proveedores inscritos
([Andina, 2025](https://andina.pe/agencia/noticia-aprueban-reglamento-organizacion-y-funciones-del-oece-1025829.aspx)).

El OECE publica estos procesos como **datos abiertos** en el estándar internacional **OCDS**
(*Open Contracting Data Standard*). Los datos son ricos pero difíciles de usar: vienen en JSON
anidado, en archivos de cientos de megabytes, con problemas de calidad documentados y sin
indicadores listos para el análisis.

## Qué hace este proyecto

Construye un **pipeline de analítica de datos en Python** que:

1. **Ingiere** datos de varias fuentes: archivos OCDS (descarga masiva), la API del OECE, un
   Excel de sanciones del Tribunal y la API del BCRP (tipo de cambio).
2. **Limpia y valida** los datos con reglas de calidad explícitas y un reporte auditable.
3. **Modela** la información en un esquema estrella listo para Power BI.
4. **Calcula indicadores de riesgo** (*red flags*) transparentes y configurables.
5. **Entrega** los resultados en Parquet, CSV, Excel formateado y una base de datos SQL
   (SQLite, PostgreSQL local o PostgreSQL en la nube).

## Preguntas de negocio

| # | Pregunta | Dónde se responde |
| --- | --- | --- |
| P1 | ¿Cuánto se adjudica, en qué periodos y en qué categorías (bienes, servicios, obras)? | Notebook 03, Power BI pág. 1 |
| P2 | ¿Qué entidades concentran el gasto y en qué departamentos? | Notebook 03, Power BI pág. 2 |
| P3 | ¿Qué proveedores reciben más adjudicaciones y en cuántas entidades? | Notebook 03, Power BI pág. 3 |
| P4 | ¿Qué tan competidos son los procesos? (postores por proceso, postor único, plazos) | Notebook 04, Power BI pág. 4 |
| P5 | ¿Qué procesos muestran señales de riesgo y conviene revisar primero? | Notebook 04, Power BI pág. 5 |
| P6 | ¿Se adjudicó a proveedores con sanción de inhabilitación vigente? | Consulta SQL 05, indicador RF06 |
| P7 | ¿Qué entidades dependen de pocos proveedores (concentración)? | Consulta SQL 06, indicador RF07 |

## Usuarios

| Usuario | Qué necesita | Producto |
| --- | --- | --- |
| Gerencia / tomador de decisiones | Vista ejecutiva y tendencias | Dashboard Power BI, reporte Excel |
| Analista de datos | Datos limpios y documentados | Capa gold (Parquet), notebooks |
| Auditor / periodista de datos | Procesos priorizados con su justificación | Hoja "Alertas", vista `vw_alertas` |
| Ingeniero de datos | Pipeline reproducible y probado | Código, pruebas, CLI, CI |

## KPIs principales

| KPI | Definición |
| --- | --- |
| Monto adjudicado (S/) | Suma de adjudicaciones válidas, convertidas a soles |
| % Diferencia vs referencial | (Valor referencial − adjudicado) / valor referencial, en procesos adjudicados |
| % Postor único | Procesos competitivos con un solo postor / procesos competitivos |
| Postores promedio | Promedio de postores por proceso |
| % Procesos con alerta | Procesos con al menos una alerta / total de procesos |
| HHI por entidad | Índice Herfindahl-Hirschman de concentración de proveedores (0-10 000) |

## Alcance

**Incluye:** procedimientos de selección publicados en el portal de contrataciones abiertas
(licitación pública, concurso público, adjudicación simplificada, subasta inversa electrónica,
selección de consultores individuales, comparación de precios, contratación directa y concurso
de proyecto de arquitectura), sus partes, postores, adjudicaciones y contratos.

**No incluye:**

* Contrataciones sin procedimiento de selección, como las menores a 3, 8 o 9 UIT: no están en la
  publicación OCDS.
* Ejecución contractual detallada (pagos, entregables): la publicación no trae transacciones.
* Modelos de machine learning: se plantean como segunda fase en la [hoja de ruta](roadmap.md).

## Supuestos y limitaciones

* Los montos sin moneda se asumen en soles (PEN), que es la moneda de la gran mayoría de procesos.
* Un valor referencial igual a 0 o negativo se trata como **no informado**.
* La calidad del análisis depende de la calidad de la fuente; los problemas conocidos se miden
  en cada ejecución (ver [Calidad de datos](07_calidad_de_datos.md)).
* **Las alertas de riesgo no prueban irregularidades.** Son señales para priorizar la revisión
  humana (ver [Indicadores de riesgo](08_indicadores_de_riesgo.md)).
* Los datos de `data/sample` son **sintéticos** y solo sirven para probar el pipeline.
