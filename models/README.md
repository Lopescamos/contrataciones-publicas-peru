# Modelos

Artefactos del modelo de monto esperado (Fase 2, machine learning). Se generan al entrenar y
no se versionan en Git: solo este archivo y los `.gitkeep`.

| Carpeta | Contenido |
| --- | --- |
| `trained/` | Modelos serializados con joblib, incluido su preprocesamiento (`monto_esperado_<versión>.joblib`) |
| `metadata/` | `model_catalog.yaml`: versión, fecha, corrida de la capa gold usada (`run_id`), fuente de datos, features y métricas |
| `logs/` | Un JSON por experimento: parámetros, particiones y métricas por segmento |

Un modelo entrenado con los datos sintéticos (`--source sample`) queda marcado como tal en
sus metadatos: sirve para probar el flujo, pero sus métricas no dicen nada de la calidad del
modelo. Configuración: `config/model_config.yaml`.
