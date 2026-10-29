"""Detección del formato de un archivo y carga automática a DataFrame."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from contrataciones.ingestion.excel_loader import load_csv, load_excel

_MAGIC = {
    b"PAR1": "parquet",
    b"PK\x03\x04": "xlsx",  # ZIP (formato Office Open XML)
    b"\xd0\xcf\x11\xe0": "xls",  # Office 97-2003
    b"\x1f\x8b": "gzip",
}
_SUFFIXES = {
    ".csv": "csv",
    ".txt": "csv",
    ".tsv": "csv",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xls": "xls",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
}


def detect_format(path: str | Path) -> str:
    """Devuelve ``csv | xlsx | xls | parquet | json | jsonl | gzip | unknown``.

    Usa primero la firma binaria (magic bytes) y luego la extensión.
    """
    path = Path(path)
    with path.open("rb") as handle:
        head = handle.read(4)
    for magic, kind in _MAGIC.items():
        if head.startswith(magic):
            if kind == "gzip":
                inner = Path(path.stem).suffix.lower()
                return _SUFFIXES.get(inner, "gzip")
            return kind
    return _SUFFIXES.get(path.suffix.lower(), "unknown")


def auto_load(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    """Carga cualquier archivo tabular soportado como DataFrame."""
    kind = detect_format(path)
    if kind == "csv":
        return load_csv(path, **kwargs)
    if kind in {"xlsx", "xls"}:
        return load_excel(path, **kwargs)
    if kind == "parquet":
        return pd.read_parquet(path)
    if kind == "jsonl":
        return pd.read_json(path, lines=True, compression="infer")
    if kind == "json":
        return pd.read_json(path, compression="infer")
    raise ValueError(f"No se reconoce el formato de {path} (detectado: {kind})")
