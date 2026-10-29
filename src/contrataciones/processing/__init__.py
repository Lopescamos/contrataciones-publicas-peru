"""Capa de procesamiento: de datos crudos a datos listos para el análisis.

Módulos:
    ocds_flattener   JSON OCDS anidado -> tablas planas (staging en Parquet).
    cleaner          Limpieza genérica y de dominio (RUC, fechas, textos) -> silver.
    currency         Conversión de montos a soles (PEN) con tipo de cambio.
    validator        Reglas de calidad de datos y perfilado de tablas.
    risk_indicators  Indicadores de riesgo (red flags) basados en reglas.
    transformer      Modelo dimensional (estrella) para Power BI -> gold.
"""
