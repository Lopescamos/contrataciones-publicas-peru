"""Conexión a bases de datos con SQLAlchemy.

Soporta los perfiles de ``config/db_config.yaml``:

* ``local_sqlite``   archivo SQLite local (sin instalación).
* ``local_postgres`` PostgreSQL local (por ejemplo con ``docker compose``).
* ``cloud_postgres`` PostgreSQL administrado (Supabase, Neon, Cloud SQL, RDS...).
* ``custom_url``     cualquier URL compatible con SQLAlchemy.

Ejemplo:
    >>> with DatabaseConnector("local_sqlite") as db:
    ...     df = db.read_query("SELECT COUNT(*) AS n FROM fact_proceso")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import URL, create_engine, event, inspect, make_url, text
from sqlalchemy.engine import Engine

from contrataciones.utils.config_loader import ConfigError, load_config, resolve_path
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

_COMMENT_LINE = re.compile(r"^\s*--.*$", re.MULTILINE)


def build_url(profile: dict[str, Any]) -> URL:
    """Construye la URL de SQLAlchemy a partir de un perfil de configuración."""
    if profile.get("url"):
        return make_url(str(profile["url"]))
    dialect = profile.get("dialect")
    if not dialect:
        raise ConfigError("El perfil de base de datos no define 'dialect' ni 'url'.")
    if dialect.startswith("sqlite"):
        database = str(profile.get("database") or ":memory:")
        if database != ":memory:":
            path = resolve_path(database)
            path.parent.mkdir(parents=True, exist_ok=True)
            database = str(path)
        return URL.create(dialect, database=database)
    if not profile.get("host"):
        raise ConfigError(
            f"El perfil '{dialect}' no tiene host. Revisa las variables del archivo .env."
        )
    port = profile.get("port")
    query = {k: str(v) for k, v in (profile.get("query") or {}).items() if v not in (None, "")}
    return URL.create(
        dialect,
        username=profile.get("username") or None,
        password=profile.get("password") or None,
        host=str(profile["host"]),
        port=int(port) if port not in (None, "") else None,
        database=profile.get("database") or None,
        query=query,
    )


def split_sql_statements(script: str) -> list[str]:
    """Divide un script SQL en sentencias (sin comentarios de línea ``--``)."""
    cleaned = _COMMENT_LINE.sub("", script)
    return [statement.strip() for statement in cleaned.split(";") if statement.strip()]


class DatabaseConnector:
    """Fachada sobre un ``Engine`` de SQLAlchemy con utilidades para análisis."""

    def __init__(self, profile: str | None = None, config: dict[str, Any] | None = None) -> None:
        self.config = config if config is not None else load_config("db_config")
        self.profile_name = profile or self.config.get("active_profile") or "local_sqlite"
        profiles = self.config.get("profiles", {})
        if self.profile_name not in profiles:
            raise ConfigError(
                f"Perfil de base de datos desconocido: '{self.profile_name}'. "
                f"Opciones: {sorted(profiles)}"
            )
        self.profile: dict[str, Any] = profiles[self.profile_name] or {}
        self.url = build_url(self.profile)
        self.schema: str | None = self.profile.get("schema") or None
        self.use_copy: bool = bool(self.profile.get("use_copy", False))
        self._engine: Engine | None = None

    # -- motor ------------------------------------------------------------------
    @property
    def dialect(self) -> str:
        return self.url.get_backend_name()

    @property
    def masked_url(self) -> str:
        return self.url.render_as_string(hide_password=True)

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            options = self.config.get("engine", {}) or {}
            connect_args: dict[str, Any] = {}
            if self.dialect == "postgresql" and self.schema and self.schema != "public":
                connect_args["options"] = f"-csearch_path={self.schema},public"
            self._engine = create_engine(
                self.url,
                pool_pre_ping=bool(options.get("pool_pre_ping", True)),
                echo=bool(options.get("echo", False)),
                connect_args=connect_args,
            )
            if self.dialect == "sqlite":
                event.listen(self._engine, "connect", _enable_sqlite_foreign_keys)
            logger.info("Conectado a %s (perfil %s)", self.masked_url, self.profile_name)
        return self._engine

    # -- consultas -----------------------------------------------------------------
    def test_connection(self) -> bool:
        """Ejecuta ``SELECT 1``. Devuelve True si la conexión funciona."""
        with self.engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar() == 1

    def read_query(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        """Ejecuta una consulta y devuelve un DataFrame. Use ``:param`` para parámetros."""
        with self.engine.connect() as connection:
            return pd.read_sql_query(text(sql), connection, params=params)

    def read_sql_file(self, path: str | Path, params: dict[str, Any] | None = None) -> pd.DataFrame:
        """Lee un archivo ``.sql`` con una sola consulta SELECT y la ejecuta."""
        statements = split_sql_statements(Path(path).read_text(encoding="utf-8"))
        if len(statements) != 1:
            raise ValueError(f"{path} debe contener exactamente una consulta")
        return self.read_query(statements[0], params=params)

    def read_table(self, table: str) -> pd.DataFrame:
        """Lee una tabla completa."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError(f"Nombre de tabla inválido: {table}")
        return self.read_query(f"SELECT * FROM {table}")

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        """Ejecuta una sentencia (DDL o DML) dentro de una transacción."""
        with self.engine.begin() as connection:
            connection.execute(text(sql), params or {})

    def execute_script(self, script: str) -> int:
        """Ejecuta un script con varias sentencias. Devuelve cuántas ejecutó."""
        statements = split_sql_statements(script)
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
        return len(statements)

    # -- metadatos -------------------------------------------------------------
    def list_tables(self) -> list[str]:
        return sorted(inspect(self.engine).get_table_names(schema=self._inspect_schema))

    def table_exists(self, table: str) -> bool:
        return inspect(self.engine).has_table(table, schema=self._inspect_schema)

    def table_columns(self, table: str) -> list[str]:
        columns = inspect(self.engine).get_columns(table, schema=self._inspect_schema)
        return [column["name"] for column in columns]

    @property
    def _inspect_schema(self) -> str | None:
        return self.schema if self.dialect == "postgresql" else None

    def ensure_schema(self) -> None:
        """Crea el esquema de PostgreSQL configurado si no existe."""
        if self.dialect == "postgresql" and self.schema and self.schema != "public":
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.schema):
                raise ConfigError(f"Nombre de esquema inválido: {self.schema}")
            self.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")

    # -- ciclo de vida -------------------------------------------------------------
    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> DatabaseConnector:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.dispose()


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
