"""Orquestación del pipeline de punta a punta.

Flujo (arquitectura medallion)::

    Fuente OCDS ──> [1] extracción + aplanado ──> staging (Parquet)
    Excel sanciones ─> [2] carga y mapeo de columnas
                       [3] limpieza ─────────────> silver (data/processed)
    API BCRP ────────> [4] conversión a soles
                       [5] calidad de datos ─────> reporte_calidad.csv
                       [6] modelo estrella + alertas > gold (data/curated)
                       [7] exportación Parquet/CSV (Power BI)
                       [8] carga a base de datos (SQLite / PostgreSQL)
                       [9] reporte Excel ejecutivo

Uso desde Python::

    from contrataciones.pipeline import Pipeline, PipelineOptions
    result = Pipeline(PipelineOptions(source="sample")).run()
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from contrataciones.export.csv_exporter import export_parquet, export_tables
from contrataciones.export.db_writer import create_views, ensure_tables, load_tables
from contrataciones.export.excel_exporter import ExcelStyle, build_report
from contrataciones.ingestion.bcrp_client import (
    DEFAULT_BASE_URL,
    BCRPClient,
    load_rates_file,
    update_rates_cache,
)
from contrataciones.ingestion.db_connector import DatabaseConnector
from contrataciones.ingestion.excel_loader import apply_column_mapping, load_tabular
from contrataciones.ingestion.ocds_source import (
    OCDSApiSource,
    compile_releases,
    filter_releases,
    find_ocds_files,
    iter_releases_from_files,
    month_segments,
    validate_segment,
)
from contrataciones.processing.cleaner import (
    EMPTY_SANCIONES,
    clean_adjudicaciones,
    clean_contratos,
    clean_partes,
    clean_postores,
    clean_procesos,
    clean_sanciones,
)
from contrataciones.processing.currency import (
    EMPTY_RATES,
    convert_to_pen,
    foreign_with_source_pen,
    prepare_rates,
)
from contrataciones.processing.ocds_flattener import STAGING_TABLES, read_staging, stage_releases
from contrataciones.processing.transformer import build_gold
from contrataciones.processing.validator import (
    profile_dataframe,
    run_quality_suite,
    summarize_quality,
)
from contrataciones.utils.config_loader import load_config, resolve_path
from contrataciones.utils.constants import BASE_CURRENCY
from contrataciones.utils.helpers import StepTimer, ensure_dir
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

SOURCES = ("sample", "bulk", "api")

# Columna de fecha y columna con el monto en soles publicado por la fuente, por tabla.
CURRENCY_COLUMNS: dict[str, tuple[str, str, str]] = {
    "procesos": ("valor_referencial", "fecha_publicacion", "valor_referencial_pen_fuente"),
    "adjudicaciones": ("monto", "fecha_adjudicacion", "monto_pen_fuente"),
    "contratos": ("monto", "fecha_firma", "monto_pen_fuente"),
}


class PipelineError(RuntimeError):
    """Error que detiene el pipeline."""


@dataclass
class PipelineOptions:
    """Parámetros de una ejecución. Los valores ``None`` toman lo definido en settings.yaml."""

    source: str = "sample"
    inputs: list[Path] = field(default_factory=list)
    sanctions: Path | None = None
    rates_file: Path | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int | None = None
    api_max_pages: int | None = None
    api_segments: list[str] | None = None
    load_database: bool | None = None
    db_profile: str | None = None
    export_excel: bool | None = None
    export_formats: list[str] | None = None
    exchange_rate_source: str | None = None
    cutoff_date: date | None = None


@dataclass
class PipelineResult:
    run_id: str
    source: str
    status: str = "ok"
    started_at: str = ""
    finished_at: str = ""
    durations: dict[str, float] = field(default_factory=dict)
    staging_counts: dict[str, int] = field(default_factory=dict)
    silver_counts: dict[str, int] = field(default_factory=dict)
    gold_counts: dict[str, int] = field(default_factory=dict)
    db_counts: dict[str, int] = field(default_factory=dict)
    quality: dict[str, int] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class Pipeline:
    """Ejecuta el pipeline completo con la configuración del proyecto."""

    def __init__(
        self,
        options: PipelineOptions | None = None,
        *,
        settings: dict[str, Any] | None = None,
        sources: dict[str, Any] | None = None,
        api_config: dict[str, Any] | None = None,
        risk_rules: dict[str, Any] | None = None,
        export_config: dict[str, Any] | None = None,
        db_config: dict[str, Any] | None = None,
    ) -> None:
        self.options = options or PipelineOptions()
        if self.options.source not in SOURCES:
            raise PipelineError(f"Fuente desconocida '{self.options.source}'. Use {SOURCES}.")
        self.settings = settings or load_config("settings")
        self.sources = sources or load_config("sources")
        self.api_config = api_config or load_config("api_config")
        self.risk_rules = risk_rules or load_config("risk_rules")
        self.export_config = export_config or load_config("export_config")
        self._db_config = db_config
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        self.result = PipelineResult(run_id=self.run_id, source=self.options.source)
        self.paths = {key: resolve_path(value) for key, value in self.settings["paths"].items()}
        pipeline_cfg = self.settings.get("pipeline", {}) or {}
        self.limit = (
            self.options.limit if self.options.limit is not None else pipeline_cfg.get("limit")
        )
        self.date_from = self.options.date_from or _parse_date(pipeline_cfg.get("date_from"))
        self.date_to = self.options.date_to or _parse_date(pipeline_cfg.get("date_to"))
        self.cutoff = self.options.cutoff_date or _parse_date(pipeline_cfg.get("cutoff_date"))

    # ------------------------------------------------------------------ utilidades
    def _setting(self, option: Any, key: str, default: Any) -> Any:
        if option is not None:
            return option
        return (self.settings.get("pipeline", {}) or {}).get(key, default)

    def _warn(self, message: str) -> None:
        logger.warning(message)
        self.result.warnings.append(message)

    # ------------------------------------------------------------------ extracción
    def _iter_source_releases(self) -> Iterator[dict[str, Any]]:
        source = self.options.source
        if source == "sample":
            files = [resolve_path(self.sources["ocds"]["sample_file"])]
        elif source == "bulk":
            files = [Path(p) for p in self.options.inputs] or find_ocds_files(
                resolve_path(self.sources["ocds"]["bulk_dir"]),
                self.sources["ocds"]["file_patterns"],
            )
            if not files:
                raise PipelineError(
                    "No hay archivos OCDS en data/raw/ocds. Descárgalos con: "
                    "contrataciones download --year 2025"
                )
        else:
            api = OCDSApiSource(self.api_config["oece_ocds"])
            raw_dir = self.paths["raw_api"] / self.run_id
            segments = self._api_segments()
            try:
                releases = list(
                    api.iter_releases(
                        max_pages=self.options.api_max_pages, raw_dir=raw_dir, segments=segments
                    )
                )
            finally:
                api.close()
            if api.truncated:
                self._warn(
                    "API: se alcanzó el límite de páginas en "
                    f"{', '.join(api.truncated)}; los datos pueden estar incompletos "
                    "(aumenta --api-max-pages o usa la descarga masiva)."
                )
            if not releases:
                raise PipelineError(
                    "La API del OECE no devolvió releases. Ejecuta 'contrataciones check-api'."
                )
            compiled = compile_releases(releases)
            logger.info("API: %d releases -> %d procesos compilados", len(releases), len(compiled))
            self.result.outputs["raw_api"] = str(raw_dir)
            yield from filter_releases(
                compiled, date_from=self.date_from, date_to=self.date_to, limit=self.limit
            )
            return
        missing = [str(f) for f in files if not Path(f).is_file()]
        if missing:
            raise PipelineError(f"No existen los archivos: {missing}")
        yield from filter_releases(
            iter_releases_from_files(files),
            date_from=self.date_from,
            date_to=self.date_to,
            limit=self.limit,
        )

    def _api_segments(self) -> list[str] | None:
        """Meses (AAAA-MM) a consultar en la API.

        Prioridad: ``api_segments`` explícitos > rango de fechas (``--year``,
        ``--date-from``/``--date-to``) > últimos meses según ``months_back``.
        """
        if self.options.api_segments:
            return [validate_segment(segment) for segment in self.options.api_segments]
        if self.date_from or self.date_to:
            today = date.today()
            start = self.date_from or self.date_to
            end = min(self.date_to or today, today)
            return month_segments(start, max(start, end))
        return None

    # ------------------------------------------------------------------ sanciones
    def _sanctions_path(self) -> Path | None:
        cfg = self.sources["sanciones"]
        if self.options.sanctions:
            return Path(self.options.sanctions)
        if self.options.source == "sample":
            return resolve_path(cfg["sample_file"])
        search_dir = resolve_path(cfg["search_dir"])
        candidates: list[Path] = []
        for pattern in cfg.get("file_patterns", []):
            candidates.extend(search_dir.glob(pattern))
        return sorted(set(candidates))[-1] if candidates else None

    def _load_sanctions(self) -> pd.DataFrame:
        path = self._sanctions_path()
        if path is None or not path.is_file():
            self._warn(
                "No se encontró archivo de sanciones: el indicador RF06 no se calculará. "
                "Coloca el Excel/CSV en data/raw/excel (ver docs/04_fuentes_de_datos.md)."
            )
            return EMPTY_SANCIONES.copy()
        cfg = self.sources["sanciones"]
        raw = load_tabular(
            path,
            sheet=cfg.get("sheet", 0),
            header_row=cfg.get("header_row", "auto"),
            aliases=cfg["columns"],
        )
        mapped = apply_column_mapping(raw, cfg["columns"], required=cfg.get("required", []))
        sanciones = clean_sanciones(mapped)
        logger.info("Sanciones cargadas desde %s: %d registros", path.name, len(sanciones))
        self.result.outputs["sanciones_origen"] = str(path)
        return sanciones

    # ------------------------------------------------------------------ tipo de cambio
    def _exchange_rates(self, silver: dict[str, pd.DataFrame]) -> pd.DataFrame:
        source = self.options.exchange_rate_source or self.settings["currency"].get(
            "exchange_rate_source", "bcrp"
        )
        if self.options.source == "sample" and self.options.exchange_rate_source is None:
            source = "file"
        foreign_dates = []
        for table, (_, date_col, source_pen_col) in CURRENCY_COLUMNS.items():
            frame = silver[table]
            is_foreign = frame["moneda"].notna() & frame["moneda"].ne(BASE_CURRENCY)
            # Los montos que ya traen su equivalente en soles no necesitan tipo de cambio.
            is_foreign &= ~foreign_with_source_pen(frame, "moneda", source_pen_col)
            foreign_dates.append(frame.loc[is_foreign, date_col].dropna())
        dates = pd.concat(foreign_dates) if foreign_dates else pd.Series(dtype="datetime64[ns]")
        if dates.empty or source == "none":
            return EMPTY_RATES.copy()

        if source == "file":
            if self.options.rates_file:
                path = Path(self.options.rates_file)
            elif self.options.source == "sample":
                path = resolve_path(self.sources["tipo_cambio"]["sample_file"])
            else:
                path = resolve_path(self.sources["tipo_cambio"]["file"])
            if not path.is_file():
                self._warn(
                    f"No existe el archivo de tipo de cambio {path}; "
                    "los montos en moneda extranjera quedan sin convertir."
                )
                return EMPTY_RATES.copy()
            return load_rates_file(path)

        cache = resolve_path(self.sources["tipo_cambio"]["cache_file"])
        cfg = self.api_config.get("bcrp", {})
        start = (dates.min() - timedelta(days=15)).date()
        end = dates.max().date()
        client = BCRPClient(
            cfg.get("base_url") or DEFAULT_BASE_URL,
            language=cfg.get("language", "esp"),
            timeout=float(cfg.get("timeout_seconds", 60)),
        )
        try:
            rates = client.get_usd_pen(start, end, series=cfg.get("usd_series", "PD04638PD"))
            return update_rates_cache(rates, cache)
        except Exception as exc:  # noqa: BLE001 - se informa y se continúa con la caché
            self._warn(f"No se pudo consultar el BCRP ({exc}). Se usa la caché local si existe.")
            return load_rates_file(cache) if cache.is_file() else EMPTY_RATES.copy()
        finally:
            client.close()

    def _convert_currency(self, silver: dict[str, pd.DataFrame], rates: pd.DataFrame) -> None:
        gap = int(self.settings["currency"].get("max_rate_gap_days", 10))
        procesos = convert_to_pen(
            silver["procesos"],
            "valor_referencial",
            "moneda",
            "fecha_publicacion",
            rates,
            "valor_referencial_pen",
            gap,
            source_pen_col="valor_referencial_pen_fuente",
        )
        silver["procesos"] = procesos

        adjudicaciones = silver["adjudicaciones"].copy()
        published = procesos.drop_duplicates("ocid").set_index("ocid")["fecha_publicacion"]
        adjudicaciones["_fecha_tc"] = adjudicaciones["fecha_adjudicacion"].fillna(
            adjudicaciones["ocid"].map(published)
        )
        adjudicaciones = convert_to_pen(
            adjudicaciones,
            "monto",
            "moneda",
            "_fecha_tc",
            rates,
            "monto_pen",
            gap,
            source_pen_col="monto_pen_fuente",
        )
        divisor = (
            adjudicaciones["n_proveedores_adjudicacion"]
            .astype("float64")
            .where(lambda s: s > 0, 1.0)
        )
        adjudicaciones["monto_asignado_pen"] = adjudicaciones["monto_pen"] / divisor
        silver["adjudicaciones"] = adjudicaciones.drop(columns="_fecha_tc")

        silver["contratos"] = convert_to_pen(
            silver["contratos"],
            "monto",
            "moneda",
            "fecha_firma",
            rates,
            "monto_pen",
            gap,
            source_pen_col="monto_pen_fuente",
        )
        silver["tipo_cambio"] = prepare_rates(rates)

    # ------------------------------------------------------------------ ejecución
    def run(self) -> PipelineResult:
        timer = StepTimer()
        result = self.result
        result.started_at = datetime.now().isoformat(timespec="seconds")
        logger.info("Pipeline %s iniciado (fuente: %s)", self.run_id, self.options.source)
        chunk_size = int(self._setting(None, "chunk_size", 20000))
        staging_dir = self.paths["staging"]

        with timer.step("1_extraccion_y_aplanado"):
            result.staging_counts = stage_releases(
                self._iter_source_releases(), staging_dir, chunk_size
            )
            if result.staging_counts.get("procesos", 0) == 0:
                raise PipelineError("No se encontraron procesos con los filtros indicados.")

        with timer.step("2_sanciones"):
            sanciones = self._load_sanctions()

        with timer.step("3_limpieza"):
            staging = {name: read_staging(staging_dir, name) for name in STAGING_TABLES}
            stats = {
                "valor_no_positivo": int((staging["procesos"]["tender_value_amount"] <= 0).sum())
            }
            silver: dict[str, pd.DataFrame] = {}
            silver["procesos"] = clean_procesos(
                staging["procesos"],
                competitive_methods=self.risk_rules.get(
                    "competitive_methods_ocds", ["open", "selective"]
                ),
                non_competitive_keywords=self.risk_rules.get(
                    "non_competitive_keywords", ["DIRECTA"]
                ),
            )
            silver["partes"] = clean_partes(staging["partes"])
            silver["postores"], stats["postores_duplicados"] = clean_postores(
                staging["postores"], silver["partes"]
            )
            silver["adjudicaciones"] = clean_adjudicaciones(
                staging["adjudicaciones"],
                silver["partes"],
                invalid_status=self.risk_rules.get(
                    "invalid_award_status", ["cancelled", "unsuccessful"]
                ),
            )
            silver["contratos"] = clean_contratos(staging["contratos"])
            silver["sanciones"] = sanciones
            del staging

        with timer.step("4_tipo_de_cambio"):
            rates = self._exchange_rates(silver)
            self._convert_currency(silver, rates)
            processed = ensure_dir(self.paths["processed"])
            for name, frame in silver.items():
                export_parquet(frame, processed / f"{name}.parquet")
            result.silver_counts = {name: len(frame) for name, frame in silver.items()}

        with timer.step("5_calidad_de_datos"):
            quality = run_quality_suite(silver, stats)
            quality.to_csv(processed / "reporte_calidad.csv", index=False, encoding="utf-8-sig")
            profile = pd.concat(
                [profile_dataframe(frame, name) for name, frame in silver.items()],
                ignore_index=True,
            )
            profile.to_csv(processed / "perfil_columnas.csv", index=False, encoding="utf-8-sig")
            result.quality = summarize_quality(quality)
            result.outputs["reporte_calidad"] = str(processed / "reporte_calidad.csv")
            logger.info("Calidad: %s", result.quality)
            fail_on_error = bool((self.settings.get("quality") or {}).get("fail_on_error", False))
            if fail_on_error and result.quality["fallas_error"] > 0:
                raise PipelineError("Fallaron reglas de calidad de severidad ERROR (ver reporte).")

        with timer.step("6_modelo_gold"):
            gold = build_gold(silver, self.risk_rules, cutoff_date=self.cutoff)
            result.gold_counts = {name: len(frame) for name, frame in gold.items()}

        with timer.step("7_exportacion"):
            formats = self.options.export_formats or self._setting(
                None, "export_formats", ["parquet", "csv"]
            )
            csv_cfg = self.export_config.get("csv", {}) or {}
            export_tables(
                gold,
                parquet_dir=self.paths["curated"],
                csv_dir=self.paths["powerbi_exports"],
                formats=formats,
                csv_options={
                    "separator": csv_cfg.get("separator", ","),
                    "decimal": csv_cfg.get("decimal", "."),
                    "encoding": csv_cfg.get("encoding", "utf-8-sig"),
                },
                compression=(self.export_config.get("parquet") or {}).get("compression", "snappy"),
            )
            result.outputs["curated"] = str(self.paths["curated"])
            if "csv" in formats:
                result.outputs["powerbi_csv"] = str(self.paths["powerbi_exports"])

        if self._setting(self.options.load_database, "load_database", True):
            with timer.step("8_base_de_datos"):
                self._load_database(gold)

        if self._setting(self.options.export_excel, "export_excel", True):
            with timer.step("9_reporte_excel"):
                excel_cfg = self.export_config.get("excel", {}) or {}
                path = (
                    self.paths["exports"]
                    / f"{excel_cfg.get('report_name', 'reporte_contrataciones')}.xlsx"
                )
                build_report(
                    gold,
                    quality,
                    path,
                    top_n=int(excel_cfg.get("top_n", 20)),
                    max_alerts=int(excel_cfg.get("max_alert_rows", 1000)),
                    style=ExcelStyle.from_config(excel_cfg),
                    source_label=f"OECE OCDS ({self.options.source})",
                )
                result.outputs["reporte_excel"] = str(path)

        result.durations = timer.durations
        result.finished_at = datetime.now().isoformat(timespec="seconds")
        if result.warnings and result.status == "ok":
            result.status = "ok_con_advertencias"
        manifest = self.paths["curated"] / "_manifest.json"
        manifest.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        result.outputs["manifest"] = str(manifest)
        logger.info("Pipeline %s terminado: %s", self.run_id, result.status)
        return result

    def _load_database(self, gold: dict[str, pd.DataFrame]) -> None:
        db_cfg = load_config("db_config") if self._db_config is None else self._db_config
        try:
            connector = DatabaseConnector(self.options.db_profile, config=db_cfg)
        except Exception as exc:  # noqa: BLE001
            self.result.status = "parcial"
            self._warn(f"Configuración de base de datos inválida: {exc}")
            return
        mode = (db_cfg.get("load") or {}).get("mode", "full_refresh")
        chunksize = int((db_cfg.get("load") or {}).get("chunksize", 10000))
        try:
            ensure_tables(connector, self.paths["sql"] / "ddl")
            self.result.db_counts = load_tables(connector, gold, mode=mode, chunksize=chunksize)
            create_views(connector, self.paths["sql"] / "views")
            self.result.outputs["base_de_datos"] = connector.masked_url
        except Exception as exc:  # noqa: BLE001 - los archivos ya se exportaron
            self.result.status = "parcial"
            self._warn(f"No se pudo cargar la base de datos ({connector.masked_url}): {exc}")
        finally:
            connector.dispose()


def run_pipeline(**kwargs: Any) -> PipelineResult:
    """Atajo: ``run_pipeline(source="sample", limit=100)``."""
    return Pipeline(PipelineOptions(**kwargs)).run()
