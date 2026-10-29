"""Contrataciones Públicas Perú.

Pipeline de analítica de datos sobre las contrataciones públicas del Perú,
publicadas por el OECE (ex OSCE) bajo el estándar Open Contracting Data
Standard (OCDS).

Capas del paquete:
    utils       Configuración, logging, constantes y utilidades transversales.
    ingestion   Lectura de fuentes: archivos OCDS, API del OECE, API del BCRP,
                Excel/CSV y bases de datos.
    processing  Aplanado OCDS, limpieza, calidad de datos, conversión de
                moneda, modelo dimensional e indicadores de riesgo.
    export      Salidas: Parquet/CSV, reporte Excel y carga a base de datos.
    pipeline    Orquestación de punta a punta.
    cli         Interfaz de línea de comandos (comando ``contrataciones``).
    features    [ML] Dataset de modelado, features y guardia contra la fuga de datos.
    models      [ML] Modelo de monto esperado y montos atípicos (``contrataciones-ml``).
"""

__version__ = "1.0.0"
