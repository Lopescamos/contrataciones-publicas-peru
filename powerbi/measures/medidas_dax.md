# Medidas DAX

Todas las medidas se crean en una tabla vacía llamada **`_Medidas`** para tenerlas ordenadas:
`Home > Enter data` → nombre `_Medidas` → `Load`. Luego, con la tabla seleccionada,
`Modeling > New measure` y pega cada fórmula. Asigna la carpeta en
`Model view > Properties > Display folder`.

Convenciones:

* Los nombres de tablas y columnas son los del modelo (`fact_proceso`, `dim_fecha`, etc.).
* Los montos ya están en soles (`*_pen`); formato recomendado: `Currency` con símbolo `S/`.
* `DIVIDE` evita errores de división entre cero (devuelve vacío).

---

## 01 · Volumen

```dax
Procesos =
COUNTROWS ( fact_proceso )
```

```dax
Procesos adjudicados =
CALCULATE ( [Procesos], fact_proceso[n_adjudicaciones] > 0 )
```

```dax
Entidades =
DISTINCTCOUNT ( fact_proceso[entidad_key] )
```

```dax
Proveedores adjudicados =
CALCULATE (
    DISTINCTCOUNT ( fact_adjudicacion[proveedor_key] ),
    fact_adjudicacion[es_valida] = TRUE ()
)
```

```dax
Contratos =
COUNTROWS ( fact_contrato )
```

## 02 · Montos

```dax
Monto adjudicado =
SUM ( fact_proceso[monto_adjudicado_pen] )
```

```dax
Valor referencial =
SUM ( fact_proceso[valor_referencial_pen] )
```

```dax
Valor referencial de lo adjudicado =
CALCULATE (
    [Valor referencial],
    NOT ISBLANK ( fact_proceso[monto_adjudicado_pen] ),
    NOT ISBLANK ( fact_proceso[valor_referencial_pen] )
)
```

```dax
Diferencia vs referencial =
VAR Referencial = [Valor referencial de lo adjudicado]
VAR Adjudicado =
    CALCULATE (
        [Monto adjudicado],
        NOT ISBLANK ( fact_proceso[valor_referencial_pen] )
    )
RETURN
    Referencial - Adjudicado
```

```dax
% Diferencia vs referencial =
DIVIDE ( [Diferencia vs referencial], [Valor referencial de lo adjudicado] )
```

```dax
Monto promedio por proceso =
DIVIDE ( [Monto adjudicado], [Procesos adjudicados] )
```

```dax
Monto asignado a proveedores =
CALCULATE (
    SUM ( fact_adjudicacion[monto_asignado_pen] ),
    fact_adjudicacion[es_valida] = TRUE ()
)
```

## 03 · Tiempo (requiere `dim_fecha` marcada como tabla de fechas)

```dax
Monto adjudicado año anterior =
CALCULATE ( [Monto adjudicado], SAMEPERIODLASTYEAR ( dim_fecha[fecha] ) )
```

```dax
Variación interanual % =
DIVIDE (
    [Monto adjudicado] - [Monto adjudicado año anterior],
    [Monto adjudicado año anterior]
)
```

```dax
Monto acumulado del año =
TOTALYTD ( [Monto adjudicado], dim_fecha[fecha] )
```

## 04 · Competencia

```dax
Procesos competitivos =
CALCULATE (
    [Procesos],
    dim_metodo[es_competitivo] = TRUE (),
    NOT ( fact_proceso[estado] IN { "cancelled", "withdrawn" } )
)
```

```dax
Procesos con postor único =
CALCULATE ( [Procesos competitivos], fact_proceso[n_postores] = 1 )
```

```dax
% Postor único =
DIVIDE ( [Procesos con postor único], [Procesos competitivos] )
```

```dax
Postores promedio =
AVERAGE ( fact_proceso[n_postores] )
```

```dax
Plazo promedio (días) =
AVERAGE ( fact_proceso[plazo_presentacion_dias] )
```

```dax
Plazo promedio de consultas (días) =
AVERAGE ( fact_proceso[plazo_consultas_dias] )
```

```dax
% Procesos con plazo de presentación informado =
DIVIDE (
    CALCULATE ( [Procesos], NOT ISBLANK ( fact_proceso[plazo_presentacion_dias] ) ),
    [Procesos]
)
```

> En la publicación del OECE `tenderPeriod` suele traer inicio = fin, por lo que
> `plazo_presentacion_dias` queda vacío en muchos procesos. Muestra la medida de cobertura junto al
> plazo promedio, o usa el plazo de consultas.

```dax
Tasa de éxito del proveedor =
VAR Postulados = COUNTROWS ( fact_postor )
VAR Ganados = CALCULATE ( COUNTROWS ( fact_postor ), fact_postor[es_ganador] = TRUE () )
RETURN
    DIVIDE ( Ganados, Postulados )
```

## 05 · Riesgo

```dax
Procesos con alerta =
CALCULATE ( [Procesos], fact_proceso[n_alertas] > 0 )
```

```dax
% Procesos con alerta =
DIVIDE ( [Procesos con alerta], [Procesos] )
```

```dax
Procesos riesgo alto =
CALCULATE ( [Procesos], fact_proceso[nivel_riesgo] = "Alto" )
```

```dax
Monto en procesos de riesgo alto =
CALCULATE ( [Monto adjudicado], fact_proceso[nivel_riesgo] = "Alto" )
```

```dax
Alertas =
COUNTROWS ( fact_alerta )
```

```dax
Procesos con la alerta seleccionada =
-- Filtra los procesos usando la tabla de alertas (respeta el filtro de dim_indicador).
CALCULATE ( [Procesos], fact_alerta )
```

```dax
Puntaje de riesgo promedio =
AVERAGE ( fact_proceso[puntaje_riesgo] )
```

```dax
Adjudicaciones a inhabilitados =
CALCULATE (
    COUNTROWS ( fact_adjudicacion ),
    fact_adjudicacion[proveedor_inhabilitado] = TRUE (),
    fact_adjudicacion[es_valida] = TRUE ()
)
```

```dax
Sanciones vigentes =
CALCULATE ( COUNTROWS ( fact_sancion ), fact_sancion[vigente_a_fecha_corte] = TRUE () )
```

## 06 · Concentración

```dax
HHI promedio =
-- agg_entidad_anio no se relaciona con dim_fecha: el año se aplica con TREATAS.
CALCULATE (
    AVERAGE ( agg_entidad_anio[hhi] ),
    TREATAS ( VALUES ( dim_fecha[anio] ), agg_entidad_anio[anio] )
)
```

```dax
Participación del proveedor =
DIVIDE (
    [Monto asignado a proveedores],
    CALCULATE ( [Monto asignado a proveedores], ALL ( dim_proveedor ) )
)
```

```dax
Ranking de entidades por monto =
RANKX ( ALLSELECTED ( dim_entidad[nombre] ), [Monto adjudicado], , DESC, DENSE )
```

## 07 · Textos dinámicos

```dax
Título periodo =
VAR Anios = VALUES ( dim_fecha[anio] )
RETURN
    IF (
        COUNTROWS ( Anios ) = 1,
        "Año " & SELECTEDVALUE ( dim_fecha[anio] ),
        "Periodo " & MIN ( dim_fecha[anio] ) & " - " & MAX ( dim_fecha[anio] )
    )
```

```dax
Nota de alertas =
"Las alertas son señales para priorizar la revisión; no prueban irregularidades."
```

## 08 · Monto esperado (Fase 2, ML)

Requieren la tabla `pred_monto_esperado` (ver `power_query/03_predicciones_ml.pq`).

```dax
Procesos evaluados (ML) =
COUNTROWS ( pred_monto_esperado )
```

```dax
Procesos con sobrecosto inusual =
CALCULATE ( [Procesos evaluados (ML)], pred_monto_esperado[tipo_desviacion] = "Sobrecosto inusual" )
```

```dax
Procesos con subcosto inusual =
CALCULATE ( [Procesos evaluados (ML)], pred_monto_esperado[tipo_desviacion] = "Subcosto inusual" )
```

```dax
Procesos a revisar por datos =
CALCULATE ( [Procesos evaluados (ML)], pred_monto_esperado[tipo_desviacion] = "Revisar datos" )
```

```dax
% Montos atípicos =
DIVIDE (
    CALCULATE ( [Procesos evaluados (ML)], pred_monto_esperado[es_atipico] = TRUE () ),
    [Procesos evaluados (ML)]
)
```

```dax
Monto esperado =
SUM ( pred_monto_esperado[monto_esperado_pen] )
```

```dax
Monto sobre lo esperado =
SUMX (
    FILTER ( pred_monto_esperado, pred_monto_esperado[tipo_desviacion] = "Sobrecosto inusual" ),
    pred_monto_esperado[monto_adjudicado_pen] - pred_monto_esperado[monto_esperado_pen]
)
```

```dax
Desviación mediana =
MEDIAN ( pred_monto_esperado[pct_desviacion] )
```

```dax
Estado del modelo =
IF (
    SELECTEDVALUE ( pred_monto_esperado[modelo_aceptado] ) = TRUE (),
    "Modelo " & SELECTEDVALUE ( pred_monto_esperado[modelo_version] ) & ": aceptado",
    "Modelo no aceptado (no supera a la línea base): interpreta los atípicos con cautela"
)
```

```dax
Nota de montos atípicos =
"Un monto atípico no prueba una irregularidad: señala un proceso que conviene revisar."
```

---

### Formatos sugeridos

| Medida | Formato |
| --- | --- |
| Montos (`Monto ...`, `Valor ...`, `Diferencia ...`) | Moneda `S/`, 0 decimales; en tarjetas, unidades en millones |
| `% ...`, `Participación ...`, `Tasa ...` | Porcentaje, 1 decimal |
| `Procesos ...`, `Alertas`, conteos | Número entero con separador de miles |
| `HHI promedio` | Número entero |
| `Postores promedio`, `Plazo promedio` | Decimal, 1 decimal |
| `Monto esperado`, `Monto sobre lo esperado` | Moneda `S/`, 0 decimales |
| `% Montos atípicos`, `Desviación mediana` | Porcentaje, 1 decimal |
