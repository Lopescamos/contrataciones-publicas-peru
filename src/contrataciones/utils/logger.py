"""Logging centralizado del proyecto.

Todos los módulos obtienen su logger con :func:`get_logger`, que cuelga del
logger raíz ``contrataciones``. La CLI llama a :func:`setup_logging` una vez
para enviar los mensajes a consola y a un archivo rotativo.

Formato:  [2026-10-19 14:30:00] [INFO] [contrataciones.ingestion] mensaje
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "contrataciones"
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_HANDLER_FLAG = "_contrataciones_handler"


def get_logger(name: str | None = None) -> logging.Logger:
    """Devuelve un logger hijo de ``contrataciones``."""
    if not name:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def setup_logging(
    level: str | int = "INFO",
    log_file: str | Path | None = None,
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
) -> logging.Logger:
    """Configura consola + archivo rotativo. Es idempotente."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper() if isinstance(level, str) else level)

    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            logger.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    setattr(console, _HANDLER_FLAG, True)
    logger.addHandler(console)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        setattr(file_handler, _HANDLER_FLAG, True)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger
