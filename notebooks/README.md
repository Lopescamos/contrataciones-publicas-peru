# Notebooks

Análisis exploratorio y explicativo sobre las salidas del pipeline. La lógica reutilizable vive en
`src/contrataciones`; los notebooks solo la usan y explican resultados.

| Notebook | Objetivo | Entradas |
| --- | --- | --- |
| `01_exploracion_ocds.ipynb` | Entender la estructura OCDS y cómo se aplana | Archivo OCDS (`data/sample` o `data/raw/ocds`) |
| `02_calidad_de_datos.ipynb` | Revisar reglas de calidad y problemas conocidos | `data/processed/reporte_calidad.csv`, `perfil_columnas.csv` |
| `03_analisis_del_gasto.ipynb` | Gasto por tiempo, categoría, procedimiento, entidad y proveedor | `data/curated/*.parquet` |
| `04_indicadores_de_riesgo.ipynb` | Alertas, competencia, concentración y priorización | `data/curated/*.parquet` |

## Cómo usarlos

```bash
contrataciones run --source sample     # 1. genera los datos que leen los notebooks
jupyter lab                            # 2. abre la carpeta notebooks/
```

En VS Code: abre el `.ipynb` y elige el intérprete de `.venv` como kernel.

## Buenas prácticas

* Ejecuta las celdas en orden (`Run > Run All Cells`) para evitar estados inconsistentes.
* Antes de hacer *commit*, limpia las salidas (`Edit > Clear Outputs of All Cells`): el
  repositorio guarda los notebooks sin resultados para que los diffs sean legibles.
* Si una lógica se repite en dos notebooks, muévela a `src/contrataciones` y agrégale pruebas.
