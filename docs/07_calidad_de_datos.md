# 7. Calidad de datos

La calidad no se asume: se **mide en cada ejecución** y queda registrada en
`data/processed/reporte_calidad.csv` y en la hoja "Calidad de datos" del reporte Excel.

## Dimensiones evaluadas

| Dimensión | Pregunta | Ejemplo de regla |
| --- | --- | --- |
| Completitud | ¿Están los datos que necesito? | `fecha_publicacion` no nula |
| Unicidad | ¿Hay registros repetidos? | `ocid` único |
| Validez | ¿Los valores tienen el formato y rango correctos? | RUC con dígito verificador válido; monto > 0 |
| Consistencia | ¿Los datos son coherentes entre sí? | Fin de presentación ≥ inicio |
| Integridad referencial | ¿Las relaciones apuntan a registros existentes? | Toda adjudicación pertenece a un proceso |

## Severidades

| Severidad | Significado | Acción |
| --- | --- | --- |
| **ERROR** | El dato no es confiable para el análisis | Investigar antes de publicar; con `quality.fail_on_error: true` detiene el pipeline |
| **ADVERTENCIA** | El análisis es posible, pero con sesgo o menor cobertura | Mencionar la limitación al presentar resultados |
| **INFO** | Característica conocida de la fuente, ya manejada por el pipeline | Documentar |

Cada regla tiene un **umbral** (% máximo de filas con problema). Si el porcentaje lo supera, el
estado es `FALLA`; si no, `OK`.

## Catálogo de reglas

| Tabla | Regla | Dimensión | Severidad | Umbral |
| --- | --- | --- | --- | --- |
| procesos | `ocid` no nulo | Completitud | ERROR | 0 % |
| procesos | `ocid` único | Unicidad | ERROR | 0 % |
| procesos | Entidad compradora informada | Completitud | ADVERTENCIA | 1 % |
| procesos | Fecha de publicación informada | Completitud | ADVERTENCIA | 5 % |
| procesos | Valor referencial informado | Completitud | ADVERTENCIA | 20 % |
| procesos | Fin de presentación ≥ inicio | Consistencia | ADVERTENCIA | 1 % |
| procesos | Moneda en {PEN, USD, EUR} | Validez | INFO | 1 % |
| procesos | Procedimiento informado | Completitud | ADVERTENCIA | 5 % |
| procesos | Valor referencial convertido a soles | Completitud | ADVERTENCIA | 0,5 % |
| procesos | Valores referenciales ≤ 0 tratados como nulos | Validez | INFO | — |
| procesos | Plazo de presentación no informado (inicio = fin) | Completitud | INFO | — |
| partes (compradores) | RUC válido | Validez | ADVERTENCIA | 10 % |
| partes (compradores) | Departamento informado | Completitud | ADVERTENCIA | 10 % |
| postores | RUC válido | Validez | ADVERTENCIA | 10 % |
| postores | Postores duplicados eliminados | Unicidad | INFO | — |
| adjudicaciones | Pertenece a un proceso existente | Integridad referencial | ERROR | 0 % |
| adjudicaciones | Monto > 0 | Validez | ADVERTENCIA | 1 % |
| adjudicaciones | RUC válido | Validez | ADVERTENCIA | 10 % |
| adjudicaciones | Proveedor identificado | Completitud | ADVERTENCIA | 2 % |
| adjudicaciones | Fecha de adjudicación ≥ publicación | Consistencia | ADVERTENCIA | 1 % |
| adjudicaciones | Adjudicaciones sin contrato vinculado | Integridad referencial | INFO | — |
| contratos | Contratos sin estado | Completitud | INFO | — |
| contratos | Contratos sin adjudicación vinculada | Integridad referencial | INFO | — |
| contratos | Fin ≥ inicio de vigencia | Consistencia | ADVERTENCIA | 1 % |
| sanciones | RUC válido | Validez | ADVERTENCIA | 5 % |
| sanciones | Fecha de inicio informada | Completitud | ADVERTENCIA | 1 % |
| sanciones | Fin ≥ inicio | Consistencia | ADVERTENCIA | 1 % |

## Problemas conocidos de la fuente y cómo se manejan

| Problema (según el Registro de Datos de OCP) | Tratamiento en el pipeline |
| --- | --- |
| Postores con identificadores duplicados | Se deduplican por proceso y RUC; se informa cuántos se eliminaron |
| Contratos sin estado | Se marcan como `sin_estado`; se informa la cantidad |
| `tenderPeriod` con inicio = fin (observado en records de la API) | El plazo queda nulo y se informa; RF02 puede evaluar `enquiryPeriod` (ver [Indicadores](08_indicadores_de_riesgo.md)) |
| Valor referencial en 0 | Se trata como no informado; se informa la cantidad |
| Adjudicaciones sin contrato y contratos sin adjudicación | Se conservan; `fact_contrato.tiene_adjudicacion_vinculada` lo indica |
| Códigos de `documentType` no documentados | No afecta: el proyecto no usa documentos |

## Cómo leer el reporte

```
tabla,regla,dimension,severidad,estado,filas_evaluadas,filas_con_problema,pct_problema,umbral_pct,...
postores,postores duplicados eliminados,Unicidad,INFO,OK,3320,26,0.7831,100.0,...
sanciones,ruc con dígito verificador válido,Validez,ADVERTENCIA,FALLA,14,1,7.1429,5.0,...
```

* `filas_evaluadas`: filas sobre las que aplica la regla (por ejemplo, solo las que tienen valor).
* `pct_problema`: porcentaje con problema; se compara con `umbral_pct`.
* En los datos de demostración, la regla de RUC de sanciones falla **a propósito**: el archivo de
  ejemplo incluye un RUC con dígito verificador incorrecto para mostrar la validación.

## Perfil de columnas

`perfil_columnas.csv` describe cada columna de la capa silver: tipo, filas, nulos, % de nulos,
valores únicos y un ejemplo. Es el punto de partida del notebook `02_calidad_de_datos.ipynb`.

## Agregar una regla nueva

1. Usa una función existente de `processing/validator.py` (`check_not_null`, `check_unique`,
   `check_range`, `check_allowed_values`, `check_valid_ruc`, `check_referential`,
   `check_date_order`) o `check_mask` con una máscara booleana propia.
2. Agrégala en `run_quality_suite` con su severidad y umbral.
3. Agrega una prueba en `tests/test_processing/test_validator.py`.
4. Documéntala en la tabla de este archivo.
