"""Registro de modelos: guardado, carga, catálogo y bitácora de experimentos.

Estructura de ``models/``:

* ``trained/<versión>.joblib``: el artefacto completo (modelo final con su
  preprocesamiento, features, configuración, escalas de atípicos y predicciones
  fuera de muestra del histórico).
* ``metadata/model_catalog.yaml``: una entrada por modelo entrenado.
* ``logs/experimento_<versión>.json``: parámetros, particiones y métricas.

Los artefactos se serializan con joblib (pickle): carga solo modelos generados por
este proyecto, nunca archivos de terceros.
"""

from __future__ import annotations

import json
import math
import platform
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import yaml

from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

CATALOG_FILE = "model_catalog.yaml"
ARTIFACT_SUFFIX = ".joblib"


def library_versions() -> dict[str, str]:
    """Versiones de las librerías que afectan la serialización y los resultados."""
    import numpy
    import sklearn

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "pandas": pd.__version__,
        "scikit-learn": sklearn.__version__,
    }


def new_version(model_name: str, now: datetime | None = None) -> str:
    """Identificador de versión: ``<modelo>_<AAAAMMDD>_<HHMMSS>``."""
    return f"{model_name}_{(now or datetime.now()):%Y%m%d_%H%M%S}"


def artifact_path(models_dir: str | Path, version: str) -> Path:
    return Path(models_dir) / "trained" / f"{version}{ARTIFACT_SUFFIX}"


def save_model(artifact: Mapping[str, Any], models_dir: str | Path) -> Path:
    """Guarda el artefacto en ``models/trained/<versión>.joblib``."""
    path = artifact_path(models_dir, str(artifact["version"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(dict(artifact), path, compress=3)
    logger.info("Modelo guardado: %s", path)
    return path


def available_versions(models_dir: str | Path, model_name: str | None = None) -> list[str]:
    """Versiones con artefacto en disco, de la más antigua a la más reciente."""
    trained = Path(models_dir) / "trained"
    pattern = f"{model_name}_*{ARTIFACT_SUFFIX}" if model_name else f"*{ARTIFACT_SUFFIX}"
    return sorted(path.stem for path in trained.glob(pattern))


def load_model(
    models_dir: str | Path, version: str | None = None, model_name: str | None = None
) -> dict[str, Any]:
    """Carga una versión (por defecto, la más reciente)."""
    if version is None:
        versions = available_versions(models_dir, model_name)
        if not versions:
            raise FileNotFoundError(
                f"No hay modelos entrenados en {Path(models_dir) / 'trained'}. "
                "Entrena uno con: contrataciones-ml train"
            )
        version = versions[-1]
    path = artifact_path(models_dir, version)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el modelo {version} ({path}).")
    artifact = joblib.load(path)
    saved = (artifact.get("library_versions") or {}).get("scikit-learn")
    current = library_versions()["scikit-learn"]
    if saved and saved != current:
        logger.warning(
            "El modelo %s se entrenó con scikit-learn %s y se carga con %s: si falla o "
            "cambian los resultados, vuelve a entrenarlo.",
            version,
            saved,
            current,
        )
    return artifact


def _plain(value: Any) -> Any:
    """Convierte tipos de numpy/pandas a tipos de Python (YAML y JSON legibles)."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, date):  # incluye datetime y pd.Timestamp
        return value.isoformat()
    if hasattr(value, "item") and not isinstance(value, str | bytes):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def read_catalog(models_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(models_dir) / "metadata" / CATALOG_FILE
    if not path.is_file():
        return []
    return list(yaml.safe_load(path.read_text(encoding="utf-8")) or [])


def append_to_catalog(models_dir: str | Path, entry: Mapping[str, Any]) -> Path:
    """Agrega una entrada al catálogo de modelos."""
    path = Path(models_dir) / "metadata" / CATALOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = read_catalog(models_dir) + [_plain(dict(entry))]
    text = yaml.safe_dump(entries, allow_unicode=True, sort_keys=False)
    path.write_text(
        "# Catálogo de modelos entrenados (generado por contrataciones-ml train).\n" + text,
        encoding="utf-8",
        newline="\n",
    )
    return path


def list_models(models_dir: str | Path) -> pd.DataFrame:
    """Catálogo como tabla, indicando si el artefacto sigue en disco."""
    catalog = pd.DataFrame(read_catalog(models_dir))
    if catalog.empty:
        return catalog
    on_disk = set(available_versions(models_dir))
    catalog["en_disco"] = catalog["version"].isin(on_disk)
    return catalog


def write_experiment_log(models_dir: str | Path, version: str, payload: Mapping[str, Any]) -> Path:
    """Escribe la bitácora del experimento en ``models/logs/experimento_<versión>.json``."""
    path = Path(models_dir) / "logs" / f"experimento_{version}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_plain(dict(payload)), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return path
