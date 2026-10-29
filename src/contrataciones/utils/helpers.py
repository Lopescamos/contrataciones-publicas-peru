"""Funciones auxiliares de uso general."""

from __future__ import annotations

import functools
import math
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd

from contrataciones.utils.logger import get_logger

T = TypeVar("T")
logger = get_logger(__name__)


def safe_get(data: Any, *path: str | int, default: Any = None) -> Any:
    """Acceso seguro a estructuras anidadas.

    >>> safe_get({"tender": {"value": {"amount": 10}}}, "tender", "value", "amount")
    10
    >>> safe_get({"tender": None}, "tender", "value", default=0)
    0
    """
    current = data
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        elif (
            isinstance(current, list)
            and isinstance(key, int)
            and -len(current) <= key < len(current)
        ):
            current = current[key]
        else:
            return default
        if current is None:
            return default
    return current


def is_missing(value: Any) -> bool:
    """True si el valor es None, NaN, NaT o pd.NA."""
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    return isinstance(value, float) and math.isnan(value)


def ensure_dir(path: str | Path) -> Path:
    """Crea el directorio (y sus padres) si no existe y lo devuelve."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def timestamp(fmt: str = "%Y%m%d_%H%M%S") -> str:
    """Marca de tiempo para nombres de archivo, p. ej. ``20261019_143000``."""
    return datetime.now().strftime(fmt)


def memory_usage(df: pd.DataFrame) -> str:
    """Memoria aproximada de un DataFrame en formato legible."""
    size = float(df.memory_usage(deep=True).sum())
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} GB"


def chunked(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    """Agrupa un iterable en listas de ``size`` elementos."""
    if size <= 0:
        raise ValueError("size debe ser mayor que cero")
    batch: list[T] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def timer(func: Callable[..., T]) -> Callable[..., T]:
    """Decorador que registra en el log la duración de la función."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            logger.debug("%s terminó en %.2f s", func.__qualname__, time.perf_counter() - start)

    return wrapper


class StepTimer:
    """Mide la duración de los pasos del pipeline.

    >>> timer = StepTimer()
    >>> with timer.step("extraccion"):
    ...     pass
    >>> "extraccion" in timer.durations
    True
    """

    def __init__(self) -> None:
        self.durations: dict[str, float] = {}

    def step(self, name: str) -> _Step:
        return _Step(self, name)


class _Step:
    def __init__(self, owner: StepTimer, name: str) -> None:
        self.owner, self.name, self.start = owner, name, 0.0

    def __enter__(self) -> _Step:
        self.start = time.perf_counter()
        logger.info("Paso '%s' iniciado", self.name)
        return self

    def __exit__(self, *exc_info: object) -> None:
        elapsed = time.perf_counter() - self.start
        self.owner.durations[self.name] = round(elapsed, 3)
        logger.info("Paso '%s' terminado en %.2f s", self.name, elapsed)
