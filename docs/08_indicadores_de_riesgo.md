# 8. Indicadores de riesgo (red flags)

## Propósito y uso responsable

Los indicadores de riesgo señalan procesos con características que la literatura y la práctica
internacional asocian a mayor riesgo de ineficiencia, baja competencia o irregularidades. Sirven
para **priorizar la revisión humana**.

> **Una alerta no es evidencia de corrupción ni de una falta.** Muchas tienen explicaciones
> legítimas (un mercado con pocos proveedores, una urgencia declarada, un plazo legal corto). Al
> presentar resultados: no atribuyas conductas a entidades o personas, explica la metodología y
> sus límites, y verifica cada caso en la fuente oficial (SEACE) antes de cualquier conclusión.

## Base metodológica

* **Open Contracting Partnership (2024).** *Red Flags in Public Procurement: A guide to using
  data to detect and mitigate risks.* Revisa 73 indicadores, con definiciones y fórmulas mapeadas
  a OCDS.
  [Enlace](https://www.open-contracting.org/es/resources/red-flags-in-public-procurement-a-guide-to-using-data-to-detect-and-mitigate-risks/)
* **Cardinal** (OCP): librería de código abierto que calcula *red flags* sobre datos OCDS. Los
  indicadores RF01 y RF02 replican sus definiciones R018 y R003.
  [Documentación](https://cardinal.readthedocs.io/)

## Reglas generales

* Se excluyen de todos los indicadores los procesos **cancelados o retirados**
  (`excluded_tender_status`), igual que en Cardinal.
* **Procedimiento competitivo:** `tender.procurementMethod` en `open` o `selective` y que el
  procedimiento no sea una contratación directa (`competitive_methods_ocds`,
  `non_competitive_keywords`).
* **Adjudicación válida:** estado distinto de `cancelled` y `unsuccessful` (en la publicación del
  OECE el estado suele venir vacío; una adjudicación sin estado se considera válida).
* Un indicador solo evalúa los procesos que tienen el dato que necesita (por ejemplo, RF02 ignora
  los procesos sin plazo informado): **la ausencia de alerta no equivale a ausencia de riesgo**.
* Todos los umbrales y pesos están en `config/risk_rules.yaml`.

## Catálogo

### RF01 · Postor único

| | |
| --- | --- |
| **Definición** | Procedimiento competitivo en el que se registró un solo postor |
| **Fórmula** | `es_competitivo` y `n_postores = 1` |
| **Por qué importa** | En un procedimiento abierto, la falta de competencia puede indicar barreras de entrada, requisitos dirigidos o un mercado poco atractivo |
| **Falsos positivos** | Mercados con pocos proveedores especializados; zonas remotas |
| **Referencia** | Cardinal R018 (*Single bid received*) |
| **Peso** | 25 |

### RF02 · Plazo de presentación corto

| | |
| --- | --- |
| **Definición** | En un procedimiento competitivo, el plazo evaluado es menor al umbral |
| **Fórmula** | `plazo_presentacion_dias < umbral` (por defecto 15 días; configurable por procedimiento). Con `period: consultas`: `plazo_consultas_dias < umbral` |
| **Por qué importa** | Un plazo muy corto reduce la cantidad de ofertas y puede favorecer a quien conocía el proceso de antemano |
| **Falsos positivos** | Procedimientos con plazos legales cortos (por ejemplo, simplificados). **Ajusta `threshold_by_method` a los plazos mínimos del Reglamento vigente** para evitarlos |
| **Referencia** | Cardinal R003 (*Short submission period*), umbral por defecto de 15 días |
| **Peso** | 15 |

**Plazo evaluado (`period`).** En la publicación del OECE, `tenderPeriod` suele traer inicio = fin
(solo la fecha de convocatoria): en ese caso el plazo de presentación queda nulo y el proceso no se
evalúa. El reporte de calidad lo cuantifica en la regla *plazo de presentación no informado*. Si
afecta a la mayoría de procesos, hay dos caminos:

1. Mantener `period: presentacion` e informar que RF02 cubre solo los procesos con plazo publicado.
2. Usar `period: consultas`, que evalúa `tender.enquiryPeriod` (formulación de consultas y
   observaciones). Es un plazo distinto y más corto, así que **los umbrales deben definirse por
   procedimiento** con los mínimos del Reglamento vigente:

```yaml
RF02:
  period: consultas
  threshold_days: 5                       # umbral general (ejemplo)
  threshold_by_method:
    "Licitación Pública": <días>
    "Adjudicación Simplificada": <días>
```

El detalle de cada alerta indica qué plazo se evaluó ("Plazo de consultas de 3 días (umbral 5)").

### RF03 · Adjudicación cercana al valor referencial

| | |
| --- | --- |
| **Definición** | En un procedimiento competitivo, lo adjudicado es al menos el 98 % del valor referencial |
| **Fórmula** | `0,98 ≤ monto_adjudicado_pen / valor_referencial_pen ≤ 1` |
| **Por qué importa** | Con competencia efectiva se esperan descuentos; adjudicar casi al tope sugiere poca presión sobre el precio |
| **Falsos positivos** | Valores referenciales bien estimados en mercados de precios regulados |
| **Referencia** | Indicador del proyecto, inspirado en la guía de OCP |
| **Peso** | 15 |

### RF04 · Adjudicación supera el valor referencial

| | |
| --- | --- |
| **Definición** | El monto adjudicado total supera el valor referencial |
| **Fórmula** | `monto_adjudicado_pen / valor_referencial_pen > 1 + tolerancia` (tolerancia 0 por defecto) |
| **Por qué importa** | Señala posibles sobrecostos o un valor referencial mal estimado |
| **Falsos positivos** | Supuestos legales que permiten superar el valor estimado; procesos por ítems con valores parciales |
| **Peso** | 10 |

### RF05 · Contratación directa

| | |
| --- | --- |
| **Definición** | El procedimiento es una contratación directa (no competitiva) |
| **Fórmula** | `es_contratacion_directa` |
| **Por qué importa** | Sin competencia, el riesgo de precios altos o selección discrecional es mayor |
| **Falsos positivos** | Muchos supuestos de contratación directa son legales (emergencias, proveedor único, etc.). Es un indicador **informativo**, por eso tiene peso bajo |
| **Peso** | 10 |

### RF06 · Proveedor inhabilitado al adjudicarse

| | |
| --- | --- |
| **Definición** | El proveedor tenía una sanción de inhabilitación vigente en la fecha de adjudicación |
| **Fórmula** | `fecha_inicio ≤ fecha_adjudicacion ≤ fecha_fin` (fin vacío = definitiva), cruzando por RUC válido y solo para sanciones cuyo tipo contiene "INHABILIT" (`sanction_type_keywords`) |
| **Por qué importa** | Un proveedor inhabilitado no puede contratar con el Estado |
| **Falsos positivos** | Errores de fecha en la fuente, sanciones suspendidas por medida judicial o cruce con un RUC mal registrado. **Verifica siempre en el RNP** |
| **Falsos negativos** | Los consorcios no tienen RUC propio en la publicación del OECE y no se publica quiénes los integran: una empresa sancionada que gana dentro de un consorcio no se detecta |
| **Requisito** | Archivo de sanciones en `data/raw/excel` |
| **Peso** | 30 |

### RF07 · Concentración proveedor-entidad

| | |
| --- | --- |
| **Definición** | Un proveedor concentra al menos el 50 % del monto adjudicado por una entidad en un año |
| **Fórmula** | `monto del proveedor en la entidad-año / monto total de la entidad-año ≥ 0,5`, solo si la entidad tuvo al menos 5 procesos adjudicados ese año |
| **Por qué importa** | La dependencia de un proveedor reduce la competencia y puede indicar favorecimiento |
| **Falsos positivos** | Entidades con pocas compras grandes; proveedores únicos de un bien especializado |
| **Peso** | 15 |

## Puntaje y niveles

```
puntaje_riesgo = min(100, suma de los pesos de las alertas activas)
```

| Nivel | Puntaje | Ejemplo |
| --- | --- | --- |
| Sin alertas | 0 | — |
| Bajo | 1 a 24 | Solo contratación directa (10) |
| Medio | 25 a 49 | Postor único (25), o plazo corto + precio cercano (30) |
| Alto | 50 o más | Postor único + plazo corto + precio cercano (55); proveedor inhabilitado + postor único (55) |

Los límites de cada nivel están en `scoring.levels` de `risk_rules.yaml`.

## Indicador complementario: HHI

El **índice Herfindahl-Hirschman** mide la concentración de proveedores por entidad y año:

```
HHI = Σ (participación de cada proveedor en el monto de la entidad × 100)²
```

Va de casi 0 (muchos proveedores pequeños) a 10 000 (un solo proveedor). Como referencia se usan
los umbrales de las guías de fusiones horizontales del DOJ/FTC de EE. UU. (2010): menor a 1 500
baja concentración, entre 1 500 y 2 500 moderada y mayor a 2 500 alta. (La versión 2023 de esas
guías redujo a 1 800 el umbral de alta concentración.) Se calcula en `agg_entidad_anio.hhi` y en la
vista `vw_resumen_entidad_anio`.

## Calibración

1. Ejecuta el pipeline con datos reales y revisa `08_alertas_por_indicador.sql` o la hoja
   "Indicadores" del Excel.
2. Si un indicador marca una proporción muy alta (por ejemplo, RF02 en procedimientos
   simplificados), ajusta su umbral por procedimiento en `risk_rules.yaml`. Si marca muy pocos,
   revisa primero en el reporte de calidad si el dato que necesita está informado.
3. Toma una muestra de procesos marcados, revísalos en el SEACE y anota cuántos eran falsos
   positivos. Ajusta y repite.
4. Documenta los cambios de umbrales en `CHANGELOG.md`.

## Agregar un indicador nuevo

1. Escribe una función `flag_...` en `processing/risk_indicators.py` que devuelva un DataFrame
   con columnas `ocid`, `codigo`, `detalle`.
2. Agrégala al diccionario `CATALOG` y al mapa de funciones de `compute_flags`.
3. Agrega su configuración (`enabled`, `weight` y umbrales) en `risk_rules.yaml`.
4. Escribe pruebas en `tests/test_processing/test_risk_indicators.py`.
5. Documenta su ficha en este archivo.
