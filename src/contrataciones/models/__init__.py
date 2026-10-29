"""Capa de modelos (Fase 2, machine learning): modelo de monto esperado.

Estima cuánto debería costar un proceso según su perfil y marca como atípicos los
montos adjudicados que se alejan mucho de lo esperado. No es un detector de fraude.

Módulos:
    trainer    División temporal, línea base, candidatos y predicción fuera de muestra.
    evaluator  Métricas (escala log y soles), mejora frente a la línea base, segmentos.
    anomaly    Escala robusta de los residuos y clasificación de las desviaciones.
    registry   Guardado, carga y catálogo de modelos versionados (carpeta models/).
    predictor  Puntaje de los procesos y exportación (Parquet, CSV, base de datos).
    report     Reporte Excel de montos atípicos.
    workflow   Orquestación de punta a punta (entrenar y predecir).
    cli        Comando ``contrataciones-ml``.
"""
