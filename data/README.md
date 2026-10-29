# Datos

Organización por capas (**arquitectura medallion**). Los datos fluyen solo hacia abajo: ninguna
capa modifica a la anterior, de modo que todo se puede regenerar desde `raw/`.

| Carpeta | Capa | Contenido | ¿Se versiona en Git? |
| --- | --- | --- | --- |
| `raw/ocds/` | Bronze | Archivos OCDS anuales (`oece_2025.jsonl.gz`) | No (pesados; se descargan) |
| `raw/api/` | Bronze | Páginas JSON de la API del OECE, una carpeta por ejecución | No |
| `raw/excel/` | Bronze | Excel/CSV de terceros (sanciones) | No |
| `processed/_staging/` | Staging | JSON aplanado por bloques | No (se regenera) |
| `processed/` | Silver | Tablas limpias + `reporte_calidad.csv` + `perfil_columnas.csv` | No (se regenera) |
| `curated/` | Gold | Modelo estrella para Power BI + `_manifest.json` de la ejecución | No (se regenera) |
| `features/` | ML | Dataset de modelado: una fila por proceso con features, objetivo y partición | No (se regenera) |
| `predictions/` | ML | Monto esperado y montos atípicos por proceso | No (se regenera) |
| `exports/` | Entrega | `reporte_contrataciones.xlsx` y `powerbi/*.csv` | No (se regenera) |
| `external/` | Referencia | Caché de tipo de cambio del BCRP | No |
| `db/` | Base de datos | `contrataciones.db` (SQLite) | No |
| `sample/` | Demostración | Datos **sintéticos** para pruebas y demo | **Sí** |

Reglas:

1. **Nunca edites a mano** los archivos de `raw/`. Si una fuente trae errores, corrígelos en el
   código de limpieza para que la corrección quede documentada y sea reproducible.
2. Todo lo que no sea `raw/` y `sample/` se puede borrar sin riesgo: `make clean` y vuelve a
   ejecutar el pipeline.
3. Los archivos pesados no se suben a Git (ver `.gitignore`).
