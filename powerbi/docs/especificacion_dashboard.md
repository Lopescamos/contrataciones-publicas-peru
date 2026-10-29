# Especificación del dashboard

Reporte de Power BI de 5 páginas + 1 página de detalle (*drill-through*). Esta especificación
dice **qué** construir; `powerbi/README.md` explica **cómo**.

## Lineamientos de diseño

* **Lienzo:** 16:9 (1280 × 720), fondo blanco, márgenes de 24 px y una cuadrícula de 12 columnas.
* **Tema:** `powerbi/theme/tema_contrataciones.json` (azules sobrios, un acento ocre y un rojo
  ladrillo reservado para riesgo). Sin degradados, sombras ni efectos 3D.
* **Tipografía:** Segoe UI; títulos de visual en 12 pt, etiquetas en 10 pt.
* **Jerarquía:** fila superior de tarjetas (KPIs), al centro el visual principal y abajo el detalle.
* **Íconos:** solo los de navegación nativos de Power BI; sin emojis ni imágenes decorativas.
* **Colores de riesgo** (usar siempre los mismos): Sin alertas `#C8CFD8`, Bajo `#7FA7C2`,
  Medio `#C9A227`, Alto `#B5533C`.
* **Encabezado de cada página:** título a la izquierda y a la derecha la medida `Título periodo`.
* **Panel de filtros** común (sincronizado con `View > Sync slicers`): Año, Departamento,
  Categoría y Procedimiento.

---

## Página 1 · Resumen ejecutivo

**Pregunta:** ¿cuánto se contrata, en qué y con cuánta competencia?

| Zona | Visual | Campos / medidas |
| --- | --- | --- |
| Fila de KPIs | 6 × `Card` | `Procesos`, `Monto adjudicado`, `% Diferencia vs referencial`, `% Postor único`, `% Procesos con alerta`, `Procesos riesgo alto` |
| Centro izquierda | `Line chart` | Eje X: `dim_fecha[anio_mes]`; Y: `Monto adjudicado`; línea secundaria opcional: `Procesos` |
| Centro derecha | `Clustered bar chart` | Eje Y: `dim_categoria[categoria]`; X: `Monto adjudicado` |
| Abajo | `Stacked bar chart` (100 %) | Eje Y: `dim_metodo[metodo_detalle]`; X: `Procesos`; Leyenda: `fact_proceso[nivel_riesgo]` |

## Página 2 · Entidades

**Pregunta:** ¿quién compra, dónde y con qué nivel de competencia?

| Zona | Visual | Campos / medidas |
| --- | --- | --- |
| Izquierda | `Azure Map` (o `Filled map`) | Ubicación: `dim_entidad[departamento]`; tamaño/color: `Monto adjudicado` |
| Derecha | `Clustered bar chart` (Top 10) | Eje Y: `dim_entidad[nombre]`; X: `Monto adjudicado`; filtro de visual *Top N* = 10 por `Monto adjudicado` |
| Abajo izquierda | `Scatter chart` | X: `% Postor único`; Y: `Monto adjudicado`; tamaño: `Procesos`; detalle: `dim_entidad[nombre]` |
| Abajo derecha | `Table` | `dim_entidad[nombre]`, `dim_entidad[departamento]`, `Procesos`, `Monto adjudicado`, `% Postor único`, `HHI promedio`, `Procesos riesgo alto` |

## Página 3 · Proveedores

**Pregunta:** ¿quién vende, a cuántas entidades y con qué antecedentes?

| Zona | Visual | Campos / medidas |
| --- | --- | --- |
| Fila de KPIs | 3 × `Card` | `Proveedores adjudicados`, `Adjudicaciones a inhabilitados`, `Sanciones vigentes` |
| Centro | `Clustered bar chart` (Top 10) | Eje Y: `dim_proveedor[nombre]`; X: `Monto asignado a proveedores` |
| Derecha | `Clustered bar chart` | Eje Y: `dim_proveedor[tipo_persona]`; X: `Monto asignado a proveedores` |
| Abajo | `Table` | `dim_proveedor[nombre]`, `dim_proveedor[ruc]`, `Monto asignado a proveedores`, `Participación del proveedor`, `Tasa de éxito del proveedor`, `dim_proveedor[tiene_sancion]` |

Formato condicional: en la tabla, ícono o color de fondo rojo ladrillo cuando `tiene_sancion` = Verdadero.

## Página 4 · Competencia

**Pregunta:** ¿qué tan competidos son los procesos?

| Zona | Visual | Campos / medidas |
| --- | --- | --- |
| Izquierda | `Clustered bar chart` | Eje Y: `dim_metodo[metodo_detalle]`; X: `% Postor único` |
| Derecha | `Line chart` | Eje X: `dim_fecha[anio_mes]`; Y: `Postores promedio` |
| Abajo izquierda | `Column chart` | Eje X: `fact_proceso[n_postores]` (clic derecho > `New group` para agrupar 10 o más); Y: `Procesos` |
| Abajo derecha | `Clustered bar chart` | Eje Y: `dim_metodo[metodo_detalle]`; X: `Plazo promedio (días)` o `Plazo promedio de consultas (días)`; en el *tooltip*, `% Procesos con plazo de presentación informado` |

## Página 5 · Alertas de riesgo

**Pregunta:** ¿qué procesos conviene revisar primero?

Incluye siempre un cuadro de texto con la medida `Nota de alertas`.

| Zona | Visual | Campos / medidas |
| --- | --- | --- |
| Fila de KPIs | 4 × `Card` | `Procesos con alerta`, `Procesos riesgo alto`, `Monto en procesos de riesgo alto`, `Puntaje de riesgo promedio` |
| Izquierda | `Clustered bar chart` | Eje Y: `dim_indicador[nombre]`; X: `Procesos con la alerta seleccionada` |
| Derecha | `Slicer` (botones) | `dim_indicador[codigo]` |
| Abajo | `Table` | `fact_proceso[ocid]`, `fact_proceso[nomenclatura]`, `dim_entidad[nombre]`, `dim_metodo[metodo_detalle]`, `Valor referencial`, `fact_proceso[n_postores]`, `fact_proceso[puntaje_riesgo]`, `fact_proceso[nivel_riesgo]` ordenada por puntaje descendente |

Formato condicional: escala de color en `puntaje_riesgo` (blanco → `#B5533C`).

## Página 6 · Detalle del proceso (*drill-through*)

`Page information > Page type: Drill through`, campo de drill-through: `fact_proceso[ocid]`.
Desde la tabla de la página 5: clic derecho → `Drill through > Detalle del proceso`.

| Zona | Visual | Contenido |
| --- | --- | --- |
| Encabezado | `Multi-row card` | ocid, nomenclatura, descripción, entidad, procedimiento, categoría, estado |
| Montos | 3 × `Card` | `Valor referencial`, `Monto adjudicado`, `% Diferencia vs referencial` |
| Alertas | `Table` | `dim_indicador[codigo]`, `dim_indicador[nombre]`, `fact_alerta[detalle]` |
| Postores | `Table` | `dim_proveedor[nombre]`, `dim_proveedor[ruc]`, `fact_postor[es_ganador]` |
| Adjudicación y contrato | `Table` | `fact_adjudicacion[award_id]`, `fact_adjudicacion[monto_asignado_pen]`, `fact_contrato[contract_id]`, `fact_contrato[estado]` |

## Página opcional · Calidad y metodología

Cuadros de texto con: fuente de datos y licencia (CC BY 4.0), fecha de corte, alcance (la
publicación no incluye contrataciones sin procedimiento de selección, como las menores a 3, 8 o
9 UIT) y advertencia de interpretación de alertas. Puede incluir el
archivo `data/processed/reporte_calidad.csv` importado como tabla.

## Checklist antes de publicar

- [ ] Relaciones según `docs/modelo_de_datos.md`, sin relaciones ambiguas ni inactivas no usadas.
- [ ] `dim_fecha` marcada como tabla de fechas.
- [ ] Columnas `*_key` ocultas; medidas en la tabla `_Medidas` con carpetas.
- [ ] Ordenamientos: `nombre_mes`, `nombre_dia`, `nivel_riesgo`.
- [ ] Tema aplicado y colores de riesgo consistentes en todas las páginas.
- [ ] Títulos de visuales en español y sin abreviaturas ambiguas.
- [ ] Nota de interpretación de alertas visible en la página 5.
- [ ] Probado con filtros extremos (un solo año, un departamento sin datos).
