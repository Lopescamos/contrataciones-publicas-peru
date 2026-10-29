"""Interfaz de línea de comandos: ``contrataciones <comando> [opciones]``.

Comandos:
    run        Ejecuta el pipeline completo (sample | bulk | api).
    download   Descarga archivos OCDS anuales del Registro de Datos de OCP.
    setup-db   Crea las tablas y vistas en la base de datos configurada.
    sample     Regenera los datos sintéticos de demostración.
    check-api  Diagnostica la conexión con la API del OECE y la del BCRP.
    query      Ejecuta un archivo .sql contra la base de datos y muestra/exporta el resultado.

Ejemplos:
    contrataciones run --source sample
    contrataciones download --year 2025
    contrataciones run --source bulk --year 2025 --limit 20000
    contrataciones run --source api --month 2025-09 --api-max-pages 5
    contrataciones query sql/queries/02_top_entidades_por_monto.sql --param anio=2025
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from contrataciones import __version__
from contrataciones.utils.config_loader import ConfigError, load_config, resolve_path
from contrataciones.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Utilidades
# -----------------------------------------------------------------------------
def _years(tokens: Sequence[str]) -> list[int]:
    """Convierte ['2023-2025', '2020'] en [2020, 2023, 2024, 2025]."""
    years: set[int] = set()
    for token in tokens:
        if "-" in str(token):
            first, last = (int(part) for part in str(token).split("-", 1))
            years.update(range(min(first, last), max(first, last) + 1))
        else:
            years.add(int(token))
    return sorted(years)


def _month(value: str) -> str:
    """Valida un mes AAAA-MM para argparse."""
    from contrataciones.ingestion.ocds_source import validate_segment

    try:
        return validate_segment(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _previous_month(today: date | None = None) -> str:
    first = (today or date.today()).replace(day=1)
    return f"{first - timedelta(days=1):%Y-%m}"


def _param(value: str) -> tuple[str, Any]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Use el formato clave=valor")
    key, raw = value.split("=", 1)
    for cast in (int, float):
        try:
            return key, cast(raw)
        except ValueError:
            continue
    return key, raw


def _print_result(result: Any) -> None:
    print("\n" + "=" * 72)
    print(f"Pipeline {result.run_id}  |  fuente: {result.source}  |  estado: {result.status}")
    print("=" * 72)
    print("Filas por capa:")
    print("  staging : " + ", ".join(f"{k}={v:,}" for k, v in result.staging_counts.items()))
    print("  silver  : " + ", ".join(f"{k}={v:,}" for k, v in result.silver_counts.items()))
    print("  gold    : " + ", ".join(f"{k}={v:,}" for k, v in result.gold_counts.items()))
    if result.db_counts:
        print(f"  base de datos: {sum(result.db_counts.values()):,} filas cargadas")
    q = result.quality
    if q:
        print(
            f"Calidad: {q['reglas']} reglas, {q['ok']} OK, {q['fallas']} con falla "
            f"({q['fallas_error']} de severidad ERROR)"
        )
    print("Salidas:")
    for name, path in result.outputs.items():
        print(f"  {name:<18} {path}")
    if result.warnings:
        print("Advertencias:")
        for warning in result.warnings:
            print(f"  - {warning}")
    total = sum(result.durations.values())
    print(f"Duración total: {total:.1f} s")


# -----------------------------------------------------------------------------
# Comandos
# -----------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    from contrataciones.pipeline import Pipeline, PipelineError, PipelineOptions

    date_from = date.fromisoformat(args.date_from) if args.date_from else None
    date_to = date.fromisoformat(args.date_to) if args.date_to else None
    if args.year:
        date_from = date_from or date(args.year, 1, 1)
        date_to = date_to or date(args.year, 12, 31)
    options = PipelineOptions(
        source=args.source,
        inputs=[Path(p) for p in args.input or []],
        sanctions=Path(args.sanctions) if args.sanctions else None,
        rates_file=Path(args.rates_file) if args.rates_file else None,
        date_from=date_from,
        date_to=date_to,
        limit=args.limit,
        api_max_pages=args.api_max_pages,
        api_segments=args.month,
        load_database=False if args.no_db else None,
        db_profile=args.db_profile,
        export_excel=False if args.no_excel else None,
        export_formats=args.formats.split(",") if args.formats else None,
        exchange_rate_source=args.rates,
        cutoff_date=date.fromisoformat(args.cutoff) if args.cutoff else None,
    )
    try:
        result = Pipeline(options).run()
    except (PipelineError, ConfigError, FileNotFoundError) as exc:
        logger.error("%s", exc)
        return 1
    _print_result(result)
    return 2 if result.status == "parcial" else 0


def cmd_download(args: argparse.Namespace) -> int:
    from contrataciones.ingestion.ocds_source import download_bulk

    api = load_config("api_config")["ocp_registry"]
    destination = resolve_path(args.dest or load_config("sources")["ocds"]["bulk_dir"])
    paths = download_bulk(
        _years(args.year),
        destination,
        api["download_url_template"],
        overwrite=args.overwrite,
        timeout=float(api.get("timeout_seconds", 900)),
    )
    for path in paths:
        print(f"Descargado: {path}")
    return 0


def cmd_setup_db(args: argparse.Namespace) -> int:
    from contrataciones.export.db_writer import create_views, ensure_tables
    from contrataciones.ingestion.db_connector import DatabaseConnector

    settings = load_config("settings")
    sql_dir = resolve_path(settings["paths"]["sql"])
    with DatabaseConnector(args.db_profile) as db:
        print(f"Base de datos: {db.masked_url}")
        ensure_tables(db, sql_dir / "ddl", drop=args.drop)
        create_views(db, sql_dir / "views")
        print("Tablas: " + ", ".join(db.list_tables()))
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    from contrataciones.sample_data import generate_sample_data

    output = resolve_path(args.output or load_config("settings")["paths"]["sample"])
    paths = generate_sample_data(output, n_processes=args.n, seed=args.seed)
    for name, path in paths.items():
        print(f"{name:<12} {path}")
    return 0


def cmd_check_api(args: argparse.Namespace) -> int:
    from contrataciones.ingestion.api_client import APIError
    from contrataciones.ingestion.bcrp_client import DEFAULT_BASE_URL, BCRPClient
    from contrataciones.ingestion.ocds_source import OCDSApiSource, extract_releases

    config = load_config("api_config")
    ok = True
    segment = args.month or _previous_month()
    oece_cfg = config["oece_ocds"]
    print(f"1) API OCDS del OECE ({oece_cfg['base_url']}/{oece_cfg.get('endpoint', 'records')})")
    source = OCDSApiSource(oece_cfg)
    try:
        try:
            year = int(segment[:4])
            months = source.available_months(year)
            listed = ", ".join(m[5:] for m in months) if months else "ninguno publicado aún"
            print(f"   Paquetes mensuales de {year} (endpoint files): {listed}")
        except APIError as exc:
            print(f"   (aviso) No se pudo consultar la lista de paquetes mensuales: {exc}")
        for page, payload in source.iter_pages(max_pages=1, segment=segment):
            releases = extract_releases(payload)
            keys = list(payload)[:8] if isinstance(payload, dict) else type(payload).__name__
            print(f"   OK  {segment}, página {page}: {len(releases)} procesos  (claves: {keys})")
            if releases:
                print(f"   Primer ocid: {releases[0].get('ocid')}")
            else:
                ok = False
                print(
                    f"   Sin procesos para {segment}: prueba otro mes con --month AAAA-MM o "
                    "revisa 'endpoint' y 'params' en config/api_config.yaml"
                )
    except APIError as exc:
        ok = False
        print(f"   FALLA: {exc}")
        if exc.status_code == 404:
            print(f"   El mes {segment} no tiene datos publicados: prueba otro con --month AAAA-MM")
        elif exc.status_code == 403:
            print(
                "   El servidor rechazó la conexión (posible bloqueo a clientes automatizados).\n"
                "   Usa la descarga masiva: contrataciones download --year 2025 && "
                "contrataciones run --source bulk"
            )
    finally:
        source.close()

    print("2) API del BCRP (tipo de cambio)")
    bcrp_cfg = config.get("bcrp", {})
    client = BCRPClient(
        bcrp_cfg.get("base_url") or DEFAULT_BASE_URL, language=bcrp_cfg.get("language", "esp")
    )
    try:
        end = date.today()
        rates = client.get_usd_pen(
            end - timedelta(days=15), end, series=bcrp_cfg.get("usd_series", "PD04638PD")
        )
        if rates.empty:
            ok = False
            print("   La API respondió sin datos para los últimos 15 días")
        else:
            last = rates.iloc[-1]
            fecha = f"{last['fecha']:%d/%m/%Y}"
            print(f"   OK  último tipo de cambio: {last['tipo_cambio']:.4f} ({fecha})")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"   FALLA: {exc}")
    finally:
        client.close()
    return 0 if ok else 1


def cmd_query(args: argparse.Namespace) -> int:
    from contrataciones.export.csv_exporter import export_csv
    from contrataciones.export.excel_exporter import export_to_excel
    from contrataciones.ingestion.db_connector import DatabaseConnector

    params = dict(args.param or [])
    with DatabaseConnector(args.db_profile) as db:
        frame = db.read_sql_file(args.sql_file, params=params or None)
    if args.output:
        output = Path(args.output)
        if output.suffix.lower() == ".xlsx":
            export_to_excel(frame, output, sheet_name=Path(args.sql_file).stem[:31])
        else:
            export_csv(frame, output)
        print(f"{len(frame):,} filas exportadas a {output}")
    else:
        import pandas as pd

        with pd.option_context("display.max_columns", 20, "display.width", 160):
            print(frame.head(args.rows).to_string(index=False))
        print(f"\n{len(frame):,} filas")
    return 0


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contrataciones",
        description="Pipeline de analítica de contrataciones públicas del Perú (OCDS - OECE).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING o ERROR")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Ejecuta el pipeline completo")
    run.add_argument(
        "--source",
        choices=["sample", "bulk", "api"],
        default="sample",
        help="sample = datos sintéticos, bulk = archivos descargados, api = API del OECE",
    )
    run.add_argument("--input", action="append", help="Archivo OCDS específico (repetible)")
    run.add_argument("--year", type=int, help="Filtra por año de convocatoria")
    run.add_argument("--date-from", help="Fecha inicial AAAA-MM-DD")
    run.add_argument("--date-to", help="Fecha final AAAA-MM-DD")
    run.add_argument("--limit", type=int, help="Máximo de procesos a procesar")
    run.add_argument(
        "--sanctions", help="Excel/CSV de sanciones (por defecto se busca en data/raw/excel)"
    )
    run.add_argument("--rates", choices=["bcrp", "file", "none"], help="Fuente del tipo de cambio")
    run.add_argument("--rates-file", help="CSV de tipo de cambio (con --rates file)")
    run.add_argument(
        "--month",
        action="append",
        type=_month,
        help="Mes AAAA-MM a consultar en la API (repetible; solo --source api)",
    )
    run.add_argument(
        "--api-max-pages", type=int, help="Máximo de páginas por mes en la API (source=api)"
    )
    run.add_argument("--db-profile", help="Perfil de config/db_config.yaml")
    run.add_argument("--no-db", action="store_true", help="No cargar la base de datos")
    run.add_argument("--no-excel", action="store_true", help="No generar el reporte Excel")
    run.add_argument("--formats", help="Formatos de exportación, p. ej. parquet,csv")
    run.add_argument("--cutoff", help="Fecha de corte AAAA-MM-DD para 'sanción vigente'")
    run.set_defaults(func=cmd_run)

    download = sub.add_parser("download", help="Descarga archivos OCDS anuales (OCP)")
    download.add_argument("--year", nargs="+", required=True, help="Años: 2025 o 2023-2025")
    download.add_argument("--dest", help="Carpeta destino (por defecto data/raw/ocds)")
    download.add_argument("--overwrite", action="store_true", help="Reemplaza archivos existentes")
    download.set_defaults(func=cmd_download)

    setup = sub.add_parser("setup-db", help="Crea tablas y vistas en la base de datos")
    setup.add_argument("--db-profile", help="Perfil de config/db_config.yaml")
    setup.add_argument("--drop", action="store_true", help="Elimina y recrea las tablas")
    setup.set_defaults(func=cmd_setup_db)

    sample = sub.add_parser("sample", help="Regenera los datos sintéticos de demostración")
    sample.add_argument("--n", type=int, default=1200, help="Cantidad de procesos")
    sample.add_argument("--seed", type=int, default=2026, help="Semilla aleatoria")
    sample.add_argument("--output", help="Carpeta destino (por defecto data/sample)")
    sample.set_defaults(func=cmd_sample)

    check = sub.add_parser("check-api", help="Diagnostica las APIs del OECE y del BCRP")
    check.add_argument(
        "--month", type=_month, help="Mes AAAA-MM a probar (por defecto, el mes anterior)"
    )
    check.set_defaults(func=cmd_check_api)

    query = sub.add_parser("query", help="Ejecuta un archivo .sql contra la base de datos")
    query.add_argument("sql_file", help="Ruta del archivo .sql")
    query.add_argument("--param", action="append", type=_param, help="Parámetro clave=valor")
    query.add_argument("--db-profile", help="Perfil de config/db_config.yaml")
    query.add_argument("--output", help="Exporta el resultado a .csv o .xlsx")
    query.add_argument("--rows", type=int, default=20, help="Filas a mostrar en pantalla")
    query.set_defaults(func=cmd_query)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_config("settings")
        log_cfg = settings.get("logging", {}) or {}
        setup_logging(
            level=args.log_level or log_cfg.get("level") or "INFO",
            log_file=resolve_path(log_cfg["file"]) if log_cfg.get("file") else None,
            max_bytes=int(log_cfg.get("max_bytes", 5_000_000)),
            backup_count=int(log_cfg.get("backup_count", 3)),
        )
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 1
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        logger.warning("Interrumpido por el usuario")
        return 130
    except ConfigError as exc:
        logger.error("Error de configuración: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
