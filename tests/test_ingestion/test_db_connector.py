"""Pruebas del conector de base de datos."""

import pytest

from contrataciones.ingestion.db_connector import DatabaseConnector, build_url, split_sql_statements
from contrataciones.utils.config_loader import ConfigError


def sqlite_config(path):
    return {
        "active_profile": "local_sqlite",
        "profiles": {"local_sqlite": {"dialect": "sqlite", "database": str(path)}},
    }


def test_split_sql_statements_removes_comment_lines():
    script = "-- comentario\nCREATE TABLE a (x INTEGER);\n\n-- otro\nINSERT INTO a VALUES (1);\n"
    assert split_sql_statements(script) == [
        "CREATE TABLE a (x INTEGER)",
        "INSERT INTO a VALUES (1)",
    ]


def test_sqlite_roundtrip(tmp_path):
    with DatabaseConnector(config=sqlite_config(tmp_path / "db" / "prueba.db")) as db:
        assert db.dialect == "sqlite"
        assert db.test_connection()
        db.execute_script(
            "CREATE TABLE t (id INTEGER PRIMARY KEY, nombre TEXT); "
            "INSERT INTO t VALUES (1, 'a'); INSERT INTO t VALUES (2, 'b');"
        )
        assert db.table_exists("t")
        assert db.list_tables() == ["t"]
        assert db.table_columns("t") == ["id", "nombre"]
        frame = db.read_query("SELECT nombre FROM t WHERE id = :id", {"id": 2})
        assert frame["nombre"].tolist() == ["b"]
        assert len(db.read_table("t")) == 2
        with pytest.raises(ValueError):
            db.read_table("t; DROP TABLE t")


def test_sqlite_enforces_foreign_keys(tmp_path):
    with DatabaseConnector(config=sqlite_config(tmp_path / "fk.db")) as db:
        db.execute_script(
            "CREATE TABLE p (id INTEGER PRIMARY KEY);"
            "CREATE TABLE h (id INTEGER PRIMARY KEY, p_id INTEGER REFERENCES p (id));"
        )
        with pytest.raises(Exception, match="FOREIGN KEY"):
            db.execute("INSERT INTO h VALUES (1, 99)")


def test_build_url_postgres_with_ssl_and_masked_password():
    profile = {
        "dialect": "postgresql+psycopg2",
        "host": "db.supabase.co",
        "port": "6543",
        "database": "postgres",
        "username": "user",
        "password": "secreto",
        "query": {"sslmode": "require"},
    }
    url = build_url(profile)
    assert url.port == 6543
    assert url.query["sslmode"] == "require"
    connector = DatabaseConnector(config={"profiles": {"nube": profile}}, profile="nube")
    assert "secreto" not in connector.masked_url
    assert connector.dialect == "postgresql"


def test_missing_host_raises_config_error():
    with pytest.raises(ConfigError, match="host"):
        build_url({"dialect": "postgresql+psycopg2", "host": None})


def test_unknown_profile_raises():
    with pytest.raises(ConfigError, match="desconocido"):
        DatabaseConnector("no_existe", config={"profiles": {"a": {"url": "sqlite://"}}})


def test_custom_url_profile():
    connector = DatabaseConnector("custom", config={"profiles": {"custom": {"url": "sqlite://"}}})
    assert connector.test_connection()
