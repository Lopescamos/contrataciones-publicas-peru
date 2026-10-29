"""Carga de DataFrames a la base de datos.

Estrategias:
    full_refresh  Borra el contenido de las tablas y las vuelve a cargar dentro de
                  una sola transacción (si algo falla, no se pierde nada).
    append        Agrega filas sin borrar.
    upsert        Inserta o actualiza por llave (SQLite y PostgreSQL).

En PostgreSQL se usa ``COPY`` para la carga masiva cuando el perfil tiene
``use_copy: true`` (decenas de veces más rápido que ``INSERT`` fila a fila).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import MetaData, Table, text
from sqlalchemy.engine import Connection

from contrataciones.ingestion.db_connector import DatabaseConnector
from contrataciones.utils.constants import GOLD_LOAD_ORDER
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)


def prepare_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    """Ajusta tipos para la base de datos.

    * Fechas sin hora -> ``date`` (columnas DATE).
    * Tipos *nullable* de pandas (Int64, boolean, string) -> objetos con ``None``.
    """
    result = df.copy()
    for column in result.columns:
        series = result[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            values = series.dt.tz_localize(None) if getattr(series.dt, "tz", None) else series
            non_null = values.dropna()
            if non_null.empty or (non_null == non_null.dt.normalize()).all():
                result[column] = [v.date() if pd.notna(v) else None for v in values]
            else:
                result[column] = [v.to_pydatetime() if pd.notna(v) else None for v in values]
        elif pd.api.types.is_extension_array_dtype(series.dtype):
            result[column] = series.astype(object).where(series.notna(), None)
    return result


def psql_insert_copy(
    table: Any, conn: Connection, keys: Sequence[str], data_iter: Iterator[Sequence[Any]]
) -> int:
    """Método de inserción para ``DataFrame.to_sql`` que usa ``COPY ... FROM STDIN``."""
    dbapi_connection = conn.connection
    with dbapi_connection.cursor() as cursor:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        rows = 0
        for row in data_iter:
            writer.writerow(row)
            rows += 1
        buffer.seek(0)
        columns = ", ".join(f'"{key}"' for key in keys)
        name = f'"{table.schema}"."{table.name}"' if table.schema else f'"{table.name}"'
        cursor.copy_expert(f"COPY {name} ({columns}) FROM STDIN WITH (FORMAT csv)", buffer)
    return rows


def write_table(
    con: Connection,
    df: pd.DataFrame,
    table: str,
    *,
    schema: str | None = None,
    if_exists: str = "append",
    chunksize: int = 10000,
    use_copy: bool = False,
) -> int:
    """Escribe un DataFrame en una tabla y devuelve la cantidad de filas."""
    if df.empty:
        return 0
    method = psql_insert_copy if use_copy and con.dialect.name == "postgresql" else None
    prepared = prepare_for_sql(df)
    prepared.to_sql(
        table,
        con=con,
        schema=schema,
        if_exists=if_exists,
        index=False,
        chunksize=chunksize,
        method=method,
    )
    return len(prepared)


def _align_columns(df: pd.DataFrame, table: str, db_columns: list[str]) -> pd.DataFrame:
    extra = [c for c in df.columns if c not in db_columns]
    missing = [c for c in db_columns if c not in df.columns]
    if extra:
        logger.warning(
            "Tabla %s: columnas no definidas en la BD (se omiten): %s. Si actualizaste el "
            "modelo, recrea las tablas con: contrataciones setup-db --drop",
            table,
            extra,
        )
    if missing:
        logger.warning("Tabla %s: columnas de la BD sin datos (quedan nulas): %s", table, missing)
    return df[[c for c in db_columns if c in df.columns]]


def load_tables(
    connector: DatabaseConnector,
    tables: dict[str, pd.DataFrame],
    *,
    mode: str = "full_refresh",
    order: Iterable[str] = GOLD_LOAD_ORDER,
    chunksize: int = 10000,
) -> dict[str, int]:
    """Carga varias tablas respetando el orden de las llaves foráneas.

    Las tablas deben existir (``contrataciones setup-db`` o :func:`ensure_tables`).
    """
    if mode not in {"full_refresh", "append"}:
        raise ValueError("mode debe ser 'full_refresh' o 'append'")
    order = [name for name in order if name in tables] + [n for n in tables if n not in order]
    missing = [name for name in order if not connector.table_exists(name)]
    if missing:
        raise RuntimeError(
            f"Faltan tablas en la base de datos: {missing}. Ejecuta 'contrataciones setup-db'."
        )
    schema = connector.schema if connector.dialect == "postgresql" else None
    counts: dict[str, int] = {}
    with connector.engine.begin() as connection:
        if mode == "full_refresh":
            for name in reversed(order):
                qualified = f"{schema}.{name}" if schema else name
                connection.execute(text(f"DELETE FROM {qualified}"))
        for name in order:
            frame = _align_columns(tables[name], name, connector.table_columns(name))
            counts[name] = write_table(
                connection,
                frame,
                name,
                schema=schema,
                chunksize=chunksize,
                use_copy=connector.use_copy,
            )
            logger.info("BD %-18s %8d filas cargadas", name, counts[name])
    return counts


def upsert(
    connector: DatabaseConnector, df: pd.DataFrame, table: str, key_columns: Sequence[str]
) -> int:
    """Inserta o actualiza filas por llave (requiere una restricción UNIQUE/PK en la llave)."""
    if df.empty:
        return 0
    dialect = connector.dialect
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise NotImplementedError(f"upsert no soportado para {dialect}")
    schema = connector.schema if dialect == "postgresql" else None
    table_obj = Table(table, MetaData(), autoload_with=connector.engine, schema=schema)
    records = prepare_for_sql(df).to_dict(orient="records")
    statement = insert(table_obj).values(records)
    updates = {
        c.name: statement.excluded[c.name]
        for c in table_obj.columns
        if c.name not in key_columns and c.name in df.columns
    }
    statement = statement.on_conflict_do_update(index_elements=list(key_columns), set_=updates)
    with connector.engine.begin() as connection:
        connection.execute(statement)
    return len(records)


def ensure_tables(
    connector: DatabaseConnector, ddl_dir: str | Path, *, drop: bool = False
) -> list[str]:
    """Ejecuta los scripts DDL (``*.sql`` en orden alfabético). Es idempotente."""
    ddl_dir = Path(ddl_dir)
    connector.ensure_schema()
    executed: list[str] = []
    if drop:
        # En PostgreSQL, CASCADE elimina también las vistas dependientes (se recrean luego).
        cascade = " CASCADE" if connector.dialect == "postgresql" else ""
        with connector.engine.begin() as connection:
            for name in reversed(GOLD_LOAD_ORDER):
                connection.execute(text(f"DROP TABLE IF EXISTS {name}{cascade}"))
        logger.warning("Tablas eliminadas por --drop")
    for script in sorted(ddl_dir.glob("*.sql")):
        statements = connector.execute_script(script.read_text(encoding="utf-8"))
        executed.append(script.name)
        logger.info("DDL ejecutado: %s (%d sentencias)", script.name, statements)
    return executed


def create_views(connector: DatabaseConnector, views_dir: str | Path) -> list[str]:
    """(Re)crea las vistas SQL (``DROP VIEW IF EXISTS`` + ``CREATE VIEW``)."""
    created: list[str] = []
    for script in sorted(Path(views_dir).glob("*.sql")):
        connector.execute_script(script.read_text(encoding="utf-8"))
        created.append(script.stem)
    if created:
        logger.info("Vistas creadas: %s", ", ".join(created))
    return created
