"""Capa de ingesta: trae datos de cualquier fuente sin transformarlos.

Módulos:
    api_client     Cliente HTTP genérico (reintentos, pausas, paginación, descargas).
    ocds_source    Lectura de datos OCDS: archivos .jsonl(.gz), API del OECE y
                   descargas masivas del Registro de Datos de OCP.
    bcrp_client    Tipo de cambio desde la API de series del BCRP.
    excel_loader   Lectura de Excel/CSV con mapeo de columnas por alias.
    file_detector  Detección de formato y carga automática de archivos tabulares.
    db_connector   Conexión a SQLite / PostgreSQL (local o nube) con SQLAlchemy.
"""
