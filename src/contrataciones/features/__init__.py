"""Capa de features (Fase 2, machine learning): de la capa gold al dataset de modelado.

Módulos:
    catalog  Definición de las features y guardia contra la fuga de datos.
    dataset  Una fila por proceso con el objetivo, la población y las fechas de corte.
    builder  Transformaciones sin estado (logaritmo, mes, tipo de entidad).
    audit    Auditoría de disponibilidad de los datos (Fase 0) en la capa gold y la API.
"""
