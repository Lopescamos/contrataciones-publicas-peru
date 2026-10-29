"""Lectura de datos OCDS (Open Contracting Data Standard) del OECE.

Tres formas de obtener los datos, todas producen *releases* OCDS (diccionarios):

1. **Archivos** ``.jsonl`` / ``.jsonl.gz`` / ``.json``: cada línea es un release
   compilado (formato del Registro de Datos de OCP) o un paquete de releases.
2. **Descarga masiva** desde el Registro de Datos de Open Contracting
   Partnership (publicación 135, un archivo por año). Es la vía recomendada.
3. **API** del Portal de Contrataciones Abiertas del OECE: endpoint ``records``
   consultado por mes (``dataSegmentationID=AAAA-MM``) y paginado por
   ``links.next``. Útil para traer lo más reciente; puede ser inestable.

El módulo no transforma los datos: solo los lee (capa bronze).
"""

from __future__ import annotations

import copy
import gzip
import io
import json
import re
from collections.abc import Iterable, Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

from contrataciones.ingestion.api_client import APIClient, APIError, default_next_link
from contrataciones.utils.helpers import safe_get
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

GZIP_MAGIC = b"\x1f\x8b"
OCDS_FILE_PATTERNS: tuple[str, ...] = ("*.jsonl", "*.jsonl.gz", "*.json", "*.json.gz")


# ---------------------------------------------------------------------------
# Paquetes y releases
# ---------------------------------------------------------------------------
def extract_releases(payload: Any) -> list[dict[str, Any]]:
    """Extrae los releases de cualquier forma de respuesta OCDS.

    Soporta: release suelto, *release package* (``releases``), *record package*
    (``records[].compiledRelease`` o ``records[].releases``) y listas de ellos.
    """
    if isinstance(payload, list):
        releases: list[dict[str, Any]] = []
        for element in payload:
            releases.extend(extract_releases(element))
        return releases
    if not isinstance(payload, dict):
        return []
    if "ocid" in payload and ("tender" in payload or "parties" in payload or "awards" in payload):
        return [payload]
    if isinstance(payload.get("releases"), list):
        return [r for r in payload["releases"] if isinstance(r, dict)]
    if isinstance(payload.get("records"), list):
        releases = []
        for record in payload["records"]:
            if not isinstance(record, dict):
                continue
            compiled = record.get("compiledRelease")
            if isinstance(compiled, dict):
                releases.append(compiled)
            elif isinstance(record.get("releases"), list):
                # Solo releases embebidos: los "linked releases" (url + date) no traen datos.
                releases.extend(
                    r for r in record["releases"] if isinstance(r, dict) and r.get("ocid")
                )
        return releases
    if isinstance(payload.get("compiledRelease"), dict):
        return [payload["compiledRelease"]]
    return []


def _is_identifiable_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(item, dict) and "id" in item for item in value)
    )


def _merge_objects(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Fusiona ``source`` sobre ``target`` siguiendo las reglas de OCDS.

    * Objetos: se fusionan campo por campo (recursivo).
    * Listas de objetos con ``id``: se fusionan elemento a elemento por ``id``.
    * Otras listas y valores simples: el valor más reciente reemplaza al anterior.
    """
    merged = dict(target)
    for key, value in source.items():
        if value is None:
            continue
        previous = merged.get(key)
        if isinstance(value, dict) and isinstance(previous, dict):
            merged[key] = _merge_objects(previous, value)
        elif _is_identifiable_list(value) and isinstance(previous, list):
            by_id = {str(item.get("id")): item for item in previous if isinstance(item, dict)}
            order = list(by_id)
            for item in value:
                item_id = str(item.get("id"))
                if item_id in by_id:
                    by_id[item_id] = _merge_objects(by_id[item_id], item)
                else:
                    by_id[item_id] = copy.deepcopy(item)
                    order.append(item_id)
            merged[key] = [by_id[item_id] for item_id in order]
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def compile_releases(releases: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compila varios releases del mismo ``ocid`` en un solo release.

    La API puede devolver un release por etapa (convocatoria, adjudicación,
    contrato). Para el análisis se necesita la foto completa del proceso.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for release in releases:
        ocid = release.get("ocid")
        if not ocid:
            continue
        groups.setdefault(str(ocid), []).append(release)
    compiled: list[dict[str, Any]] = []
    for items in groups.values():
        if len(items) == 1:
            compiled.append(items[0])
            continue
        items = sorted(items, key=lambda r: str(r.get("date") or ""))
        result: dict[str, Any] = {}
        for item in items:
            result = _merge_objects(result, item)
        compiled.append(result)
    return compiled


# ---------------------------------------------------------------------------
# Archivos
# ---------------------------------------------------------------------------
def _open_text(path: Path) -> io.TextIOBase:
    with path.open("rb") as probe:
        magic = probe.read(2)
    if magic == GZIP_MAGIC:
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")  # type: ignore[return-value]
    return path.open("r", encoding="utf-8", errors="replace")


def _is_line_delimited(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".jsonl", ".jsonl.gz", ".ndjson", ".ndjson.gz"))


def iter_json_records(path: str | Path) -> Iterator[Any]:
    """Lee un archivo JSON o JSON Lines (opcionalmente comprimido en gzip)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo OCDS: {path}")
    with _open_text(path) as handle:
        if not _is_line_delimited(path):
            yield json.load(handle)
            return
        invalid = 0
        for line_number, line in enumerate(handle, start=1):
            text = line.strip().rstrip(",")
            if not text or text in {"[", "]"}:
                continue
            try:
                yield json.loads(text)
            except json.JSONDecodeError:
                invalid += 1
                if invalid <= 5:
                    logger.warning("Línea %d inválida en %s (se omite)", line_number, path.name)
        if invalid:
            logger.warning("%d líneas inválidas omitidas en %s", invalid, path.name)


def find_ocds_files(
    directory: str | Path, patterns: Iterable[str] = OCDS_FILE_PATTERNS
) -> list[Path]:
    """Lista los archivos OCDS de una carpeta (sin duplicados, ordenados)."""
    directory = Path(directory)
    found: set[Path] = set()
    for pattern in patterns:
        found.update(p for p in directory.glob(pattern) if p.is_file())
    return sorted(found)


def iter_releases_from_files(paths: Iterable[str | Path]) -> Iterator[dict[str, Any]]:
    """Entrega uno a uno los releases contenidos en una lista de archivos."""
    for path in paths:
        logger.info("Leyendo archivo OCDS: %s", path)
        for record in iter_json_records(path):
            yield from extract_releases(record)


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
def _parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def release_reference_date(release: dict[str, Any]) -> date | None:
    """Fecha de referencia del proceso: inicio de presentación, publicación o release."""
    for path in (("tender", "tenderPeriod", "startDate"), ("tender", "datePublished"), ("date",)):
        found = _parse_iso_date(safe_get(release, *path))
        if found:
            return found
    return None


def filter_releases(
    releases: Iterable[dict[str, Any]],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Filtra por rango de fechas (inclusive) y corta al alcanzar ``limit``."""
    emitted = 0
    for release in releases:
        if limit is not None and emitted >= limit:
            return
        if date_from or date_to:
            reference = release_reference_date(release)
            if reference is None:
                continue
            if date_from and reference < date_from:
                continue
            if date_to and reference > date_to:
                continue
        emitted += 1
        yield release


# ---------------------------------------------------------------------------
# Descargas masivas (Registro de Datos de OCP)
# ---------------------------------------------------------------------------
def bulk_download_url(name: str | int, template: str) -> str:
    """URL de descarga de un archivo anual. ``name`` puede ser 2025 o '2025.jsonl.gz'."""
    file_name = f"{name}.jsonl.gz" if str(name).isdigit() else str(name)
    return template.format(name=file_name)


def download_bulk(
    years: Iterable[int | str],
    destination_dir: str | Path,
    template: str,
    *,
    client: APIClient | None = None,
    overwrite: bool = False,
    timeout: float = 900,
) -> list[Path]:
    """Descarga los archivos anuales ``<año>.jsonl.gz`` de la publicación del OECE."""
    destination_dir = Path(destination_dir)
    own_client = client is None
    client = client or APIClient(timeout=timeout, max_retries=3)
    paths: list[Path] = []
    try:
        for year in years:
            url = bulk_download_url(year, template)
            target = destination_dir / f"oece_{year}.jsonl.gz"
            logger.info("Descargando %s -> %s", url, target)
            paths.append(client.download(url, target, overwrite=overwrite, timeout=timeout))
    finally:
        if own_client:
            client.close()
    return paths


# ---------------------------------------------------------------------------
# API del OECE
# ---------------------------------------------------------------------------
_SEGMENT_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def validate_segment(value: str) -> str:
    """Valida un segmento mensual ``AAAA-MM`` (``dataSegmentationID`` del OECE)."""
    text = str(value).strip()
    if not _SEGMENT_PATTERN.match(text):
        raise ValueError(f"Mes inválido '{value}': use el formato AAAA-MM (p. ej. 2025-03)")
    return text


def month_segments(start: date, end: date) -> list[str]:
    """Meses ``AAAA-MM`` entre dos fechas, ambos incluidos, en orden cronológico."""
    if end < start:
        start, end = end, start
    segments: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        segments.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return segments


def recent_segments(months_back: int, today: date | None = None) -> list[str]:
    """Los últimos ``months_back`` meses, incluido el actual (del más antiguo al más reciente)."""
    today = today or date.today()
    index = today.year * 12 + (today.month - 1) - (max(1, int(months_back)) - 1)
    return month_segments(date(index // 12, index % 12 + 1, 1), today)


class OCDSApiSource:
    """Lee procesos desde la API del Portal de Contrataciones Abiertas del OECE.

    Por defecto consulta ``records?sourceId=seace_v3&dataSegmentationID=AAAA-MM``
    (un paquete de *records* por mes de convocatoria, 20 por página) y sigue el
    enlace ``links.next``. Cada página recibida se guarda tal cual en ``raw_dir``
    (capa bronze), lo que permite reprocesar sin volver a llamar a la API.

    ``max_pages`` se aplica por segmento. Si se alcanza y aún hay páginas, el
    segmento queda registrado en :attr:`truncated`.
    """

    def __init__(self, config: dict[str, Any], client: APIClient | None = None) -> None:
        self.config = config
        retries = config.get("retries", {}) or {}
        self.endpoint = str(config.get("endpoint") or "records")
        self.segment_param = config.get("segment_param") or None
        self.truncated: list[str] = []
        self.client = client or APIClient(
            config["base_url"],
            headers=config.get("headers") or {},
            timeout=float(config.get("timeout_seconds", 60)),
            max_retries=int(retries.get("total", 5)),
            backoff_factor=float(retries.get("backoff_factor", 1.0)),
            status_forcelist=retries.get("status_forcelist", [429, 500, 502, 503, 504]),
            min_interval=float(config.get("min_interval_seconds", 0.5)),
        )

    # -- parámetros ---------------------------------------------------------------
    def default_segments(self, today: date | None = None) -> list[str]:
        """Segmentos por defecto: los últimos ``months_back`` meses."""
        if not self.segment_param:
            return []
        return recent_segments(int(self.config.get("months_back", 2)), today)

    def _params(self, segment: str | None = None) -> dict[str, Any]:
        params = {k: v for k, v in (self.config.get("params") or {}).items() if v not in (None, "")}
        if segment and self.segment_param:
            params[self.segment_param] = validate_segment(segment)
        return params

    def _max_pages(self, max_pages: int | None) -> int | None:
        value = max_pages if max_pages is not None else self.config.get("max_pages")
        return int(value) if value not in (None, "") else None

    # -- lectura ----------------------------------------------------------------------
    def iter_pages(
        self, max_pages: int | None = None, segment: str | None = None
    ) -> Iterator[tuple[int, Any]]:
        """Páginas ``(n, payload)`` de un segmento (o de la consulta sin segmento)."""
        yield from self.client.iter_pages(
            self.endpoint,
            params=self._params(segment) or None,
            max_pages=self._max_pages(max_pages),
        )

    def iter_releases(
        self,
        max_pages: int | None = None,
        raw_dir: str | Path | None = None,
        segments: Iterable[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Releases de los segmentos indicados (por defecto, los últimos meses)."""
        raw_path = Path(raw_dir) if raw_dir else None
        if raw_path:
            raw_path.mkdir(parents=True, exist_ok=True)
        targets: list[str | None] = list(segments or []) or list(self.default_segments())
        if not targets:
            targets = [None]
        limit = self._max_pages(max_pages)
        self.truncated = []
        for segment in targets:
            label = segment or "todo"
            pages = releases_count = 0
            payload: Any = None
            try:
                for page, payload in self.iter_pages(max_pages=limit, segment=segment):
                    pages = page
                    if raw_path:
                        name = f"{segment or 'consulta'}_page_{page:05d}.json"
                        (raw_path / name).write_text(
                            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                        )
                    releases = extract_releases(payload)
                    if not releases:
                        if page == 1:
                            keys = list(payload)[:10] if isinstance(payload, dict) else payload
                            logger.warning("API OECE: %s sin datos (claves: %s)", label, keys)
                        payload = None
                        break
                    releases_count += len(releases)
                    yield from releases
            except APIError as exc:
                if exc.status_code != 404:
                    raise
                logger.warning("API OECE: %s no encontrado (HTTP 404); se omite", label)
                continue
            if limit and pages >= limit and payload is not None and default_next_link(payload):
                self.truncated.append(label)
                logger.warning(
                    "API OECE: %s tiene más de %d páginas; se leyeron solo %d", label, limit, limit
                )
            logger.info("API OECE: %s -> %d páginas, %d procesos", label, pages, releases_count)

    def available_months(self, year: int) -> list[str]:
        """Meses con paquete de descarga masiva publicado (endpoint ``files``).

        El OECE publica estos paquetes con retraso: una lista vacía para el año
        en curso no significa que la API ``records`` no tenga datos.
        """
        endpoint = self.config.get("files_endpoint")
        if not endpoint:
            return []
        source = (self.config.get("params") or {}).get("sourceId", "seace_v3")
        payload = self.client.get_json(endpoint, params={"year": int(year), "source": source})
        results = payload.get("results") if isinstance(payload, dict) else payload
        months: set[str] = set()
        for item in results or []:
            month = str(item.get("month", "")).strip() if isinstance(item, dict) else ""
            if month.isdigit() and 1 <= int(month) <= 12:
                months.add(f"{int(year):04d}-{int(month):02d}")
        return sorted(months)

    def close(self) -> None:
        self.client.close()
