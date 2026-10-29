"""Exportación a Parquet y CSV."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)


def dates_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas de fecha sin hora -> tipo ``date`` (Power BI las reconoce como Fecha)."""
    result = df
    for column in df.columns:
        series = df[column]
        if not pd.api.types.is_datetime64_any_dtype(series) or isinstance(
            series.dtype, pd.DatetimeTZDtype
        ):
            continue
        non_null = series.dropna()
        if not non_null.empty and (non_null == non_null.dt.normalize()).all():
            if result is df:
                result = df.copy()
            result[column] = pd.Series(
                [v.date() if pd.notna(v) else None for v in series], index=df.index, dtype=object
            )
    return result


def export_parquet(df: pd.DataFrame, path: str | Path, compression: str = "snappy") -> Path:
    """Guarda un DataFrame en Parquet (columnar, tipado y comprimido).

    Las marcas de tiempo se escriben en microsegundos (compatibles con Power BI,
    BigQuery y Spark) y las fechas sin hora como tipo ``date``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dates_for_parquet(df).to_parquet(
        path,
        index=False,
        compression=compression,
        coerce_timestamps="us",
        allow_truncated_timestamps=True,
    )
    return path


def export_csv(
    df: pd.DataFrame,
    path: str | Path,
    separator: str = ",",
    decimal: str = ".",
    encoding: str = "utf-8-sig",
) -> Path:
    """Guarda un CSV. ``utf-8-sig`` agrega BOM para que Excel lea bien las tildes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(
        path, index=False, sep=separator, decimal=decimal, encoding=encoding, date_format="%Y-%m-%d"
    )
    return path


def export_tables(
    tables: dict[str, pd.DataFrame],
    parquet_dir: str | Path | None = None,
    csv_dir: str | Path | None = None,
    formats: Iterable[str] = ("parquet", "csv"),
    csv_options: dict | None = None,
    compression: str = "snappy",
) -> dict[str, list[Path]]:
    """Exporta varias tablas. Devuelve las rutas generadas por formato."""
    formats = set(formats)
    written: dict[str, list[Path]] = {"parquet": [], "csv": []}
    for name, frame in tables.items():
        if "parquet" in formats and parquet_dir is not None:
            written["parquet"].append(
                export_parquet(frame, Path(parquet_dir) / f"{name}.parquet", compression)
            )
        if "csv" in formats and csv_dir is not None:
            written["csv"].append(
                export_csv(frame, Path(csv_dir) / f"{name}.csv", **(csv_options or {}))
            )
    for kind, paths in written.items():
        if paths:
            logger.info("Exportados %d archivos %s", len(paths), kind.upper())
    return written
