# Hoja de ruta

## Fase 1 · Analítica de datos (versión actual, 1.0.0)

- [x] Ingesta: descarga masiva OCDS, API del OECE, Excel de sanciones, API del BCRP
- [x] Limpieza y validación con reporte de calidad
- [x] Modelo estrella e indicadores de riesgo basados en reglas
- [x] Exportación a Parquet, CSV, Excel y base de datos (SQLite / PostgreSQL local y nube)
- [x] Vistas y consultas SQL de negocio
- [x] Notebooks de análisis y guía completa de Power BI
- [x] Pruebas automatizadas e integración continua

## Fase 1.1 · Mejoras de analítica

- [ ] Construir y publicar el dashboard de Power BI con datos reales de 2024-2025
- [ ] Calibrar umbrales de RF02 por procedimiento según el Reglamento vigente (plazo de
      presentación y de consultas)
- [ ] Descarga mensual desde el endpoint `file/{source}/{tipo}/{año}/{mes}` del OECE como
      alternativa a la API paginada
- [ ] Integrantes de los consorcios (no vienen en OCDS) para extender el cruce de sanciones (RF06)
- [ ] Indicadores adicionales de la guía OCP: fraccionamiento (varios procesos pequeños del mismo
      objeto), proveedor nuevo que gana un monto alto, adjudicación tras pocos días del cierre
- [ ] Carga incremental por año (en lugar de *full refresh* completo)
- [ ] Orquestación con Prefect o Airflow; transformaciones SQL con dbt

## Fase 2 · Machine learning

### 2.0 · Modelo de monto esperado (en curso)

Detalle en [Machine learning](11_machine_learning.md).

- [x] Infraestructura: extra `ml`, `config/model_config.yaml`, carpetas y notebooks `ml/`
- [x] Features ex ante con guardia contra la fuga de datos y canario en las pruebas
- [x] División temporal con corte por disponibilidad y madurez; predicción fuera de muestra
- [x] Línea base B1, Ridge e HistGradientBoosting; métricas por segmento e importancia
- [x] Montos atípicos con escala robusta; tabla, vista y consulta SQL; reporte Excel
- [x] Comando `contrataciones-ml`, scripts, CI y página de Power BI especificada
- [ ] Fase 0: auditoría de fuga de datos con datos reales (`notebooks/ml/01_...`)
- [ ] Entrenamiento con datos reales y reporte de métricas
- [ ] Decidir la integración como RF08 (requiere validar el modelo con datos reales)

### Estructura

La capa gold es la entrada de los modelos, sin modificar el pipeline:

```
data/
├── features/          Variables para entrenar (por proceso, proveedor y entidad)
└── predictions/       Resultados de los modelos
models/
├── trained/           Modelos serializados
└── metadata/          Catálogo de modelos y métricas
src/contrataciones/
├── features/          Construcción y selección de variables
└── models/            Entrenamiento, evaluación y predicción
notebooks/ml/          Experimentos
config/model_config.yaml
```

Casos de uso candidatos:

| Caso | Tipo | Variable objetivo / salida |
| --- | --- | --- |
| Predecir procesos con postor único antes de la convocatoria | Clasificación | `n_postores = 1` |
| Detección de procesos atípicos sin etiquetas | Detección de anomalías (Isolation Forest) | Puntaje de anomalía |
| Predecir si un proveedor será sancionado | Clasificación | Aparición en el registro de sanciones |
| Segmentación de proveedores | Clustering | Perfiles de proveedor |
| Estimar el monto adjudicado esperado (**en curso**, 2.0) | Regresión | `log(monto adjudicado / valor referencial)` |

Principios: validación temporal (entrenar con el pasado, evaluar con el futuro), métricas
reportadas por segmento y la misma advertencia de uso responsable que los indicadores.
