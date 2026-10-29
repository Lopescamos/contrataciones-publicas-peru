"""Carga de configuración: archivos YAML de ``config/`` + variables de entorno.

Los YAML pueden usar marcadores ``${VARIABLE}`` o ``${VARIABLE:-defecto}``, que
se reemplazan con el valor de la variable de entorno (o del archivo ``.env``).

Ejemplo:
    >>> from contrataciones.utils.config_loader import load_config, get_path
    >>> settings = load_config("settings")
    >>> get_path("curated")
    PosixPath('/ruta/al/proyecto/data/curated')
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT_ENV_VAR = "CONTRATACIONES_HOME"
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_INT = re.compile(r"[+-]?\d+")
_FLOAT = re.compile(r"[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?")


class ConfigError(RuntimeError):
    """Error de configuración (archivo inexistente, clave faltante, etc.)."""


def get_project_root() -> Path:
    """Devuelve la carpeta raíz del proyecto.

    Orden de búsqueda:
        1. Variable de entorno ``CONTRATACIONES_HOME``.
        2. Directorio actual o alguno de sus padres que contenga
           ``pyproject.toml`` y ``config/settings.yaml``.
        3. Ubicación del paquete (instalación en modo editable).
    """
    env_root = os.environ.get(ROOT_ENV_VAR)
    if env_root:
        return Path(env_root).expanduser().resolve()
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "config" / "settings.yaml"
        ).is_file():
            return candidate
    return Path(__file__).resolve().parents[3]


def load_env(dotenv_path: str | Path | None = None, override: bool = False) -> bool:
    """Carga el archivo ``.env`` de la raíz del proyecto (si existe)."""
    path = Path(dotenv_path) if dotenv_path else get_project_root() / ".env"
    if path.is_file():
        return load_dotenv(path, override=override)
    return False


def _coerce(text: str) -> Any:
    """Convierte el texto de una variable de entorno al tipo más probable."""
    stripped = text.strip()
    if stripped == "":
        return None
    lowered = stripped.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if _INT.fullmatch(stripped):
        return int(stripped)
    if _FLOAT.fullmatch(stripped):
        return float(stripped)
    return stripped


def _env_value(name: str, default: str | None) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        return default if default is not None else ""
    return value


def interpolate_env(value: Any) -> Any:
    """Reemplaza recursivamente los marcadores ``${VAR:-defecto}``.

    Si el texto completo es un único marcador, el resultado se convierte al
    tipo correspondiente (entero, decimal, booleano o ``None`` si está vacío).
    """
    if isinstance(value, dict):
        return {key: interpolate_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [interpolate_env(item) for item in value]
    if not isinstance(value, str) or "${" not in value:
        return value
    full = _PLACEHOLDER.fullmatch(value.strip())
    if full:
        return _coerce(_env_value(full.group(1), full.group(2)))
    return _PLACEHOLDER.sub(lambda m: _env_value(m.group(1), m.group(2)), value)


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Lee un YAML y aplica la interpolación de variables de entorno."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"No existe el archivo de configuración: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"El archivo {path} debe contener un diccionario YAML.")
    return interpolate_env(data)


def load_config(name: str, root: Path | None = None) -> dict[str, Any]:
    """Carga ``config/<name>.yaml`` (después de cargar el ``.env``)."""
    load_env()
    base = root or get_project_root()
    return load_yaml(base / "config" / f"{name}.yaml")


def resolve_path(path: str | Path, root: Path | None = None) -> Path:
    """Convierte una ruta relativa a la raíz del proyecto en ruta absoluta."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (root or get_project_root()) / candidate


def get_path(key: str, settings: dict[str, Any] | None = None) -> Path:
    """Devuelve la ruta absoluta configurada en ``settings.paths.<key>``."""
    settings = settings or load_config("settings")
    try:
        return resolve_path(settings["paths"][key])
    except KeyError as exc:
        raise ConfigError(f"La ruta '{key}' no está definida en settings.yaml") from exc
