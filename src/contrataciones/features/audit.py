"""Auditoría de disponibilidad de los datos (Fase 0 del modelo de monto esperado).

Responde con datos qué se sabía de cada proceso al convocarlo:

* En la capa gold: cuántos adjudicados tienen un monto igual al referencial al
  céntimo, si los postores aparecen solo en procesos con resultado y qué columnas
  candidatas vienen vacías.
* En las páginas crudas de la API del OECE (``data/raw/api``): la marca de
  información protegida por ley frente al valor referencial y la adjudicación.
* En la historia de versiones de la API (opcional, requiere conexión): si el valor
  referencial y los postores ya estaban publicados antes de la buena pro.

La interpretación y la decisión (por ejemplo, excluir métodos en
``population.exclude_methods``) se documentan en
``notebooks/ml/01_auditoria_fuga_de_datos.ipynb``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from contrataciones.features.dataset import EQUAL_AMOUNT_TOLERANCE
from contrataciones.ingestion.api_client import APIClient, APIError
from contrataciones.utils.helpers import safe_get
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

DIAGNOSIS_NO_HISTORY = "Sin versión previa a la buena pro"
DIAGNOSIS_REVEALED = "Valor revelado con la buena pro"
DIAGNOSIS_STABLE = "Valor estable"
DIAGNOSIS_CHANGED = "Valor cambia"
DIAGNOSIS_ERROR = "Error al consultar"

AUDITED_COLUMNS: tuple[str, ...] = (
    "valor_referencial_pen",
    "plazo_presentacion_dias",
    "plazo_consultas_dias",
    "n_postores",
)


# -----------------------------------------------------------------------------
# Capa gold
# -----------------------------------------------------------------------------
def equality_by_segment(
    table: pd.DataFrame,
    by: Sequence[str] = ("dim_metodo.metodo_detalle", "dim_categoria.categoria"),
) -> pd.DataFrame:
    """Procesos de la población cuyo monto adjudicado es igual al referencial, por segmento."""
    population = table[table["es_poblacion"]]
    grouped = population.groupby(list(by), dropna=False)["es_adjudicado_igual_referencial"]
    result = grouped.agg(n_procesos="size", n_igual_referencial="sum").reset_index()
    result["pct_igual_referencial"] = result["n_igual_referencial"] / result["n_procesos"]
    result.columns = [str(c).split(".")[-1] for c in result.columns]
    return result.sort_values("n_procesos", ascending=False, ignore_index=True)


def bidders_by_outcome(fact_proceso: pd.DataFrame) -> pd.DataFrame:
    """Procesos con postores publicados según tengan o no adjudicación.

    Si los postores solo aparecen en procesos con resultado (buena pro o desierto),
    el número de postores es información posterior a la convocatoria.
    """
    has_award = pd.to_numeric(fact_proceso["monto_adjudicado_pen"], errors="coerce").gt(0)
    has_bidders = pd.to_numeric(fact_proceso["n_postores"], errors="coerce").gt(0)
    frame = pd.DataFrame(
        {
            "tiene_adjudicacion": has_award.map(
                {True: "Con adjudicación", False: "Sin adjudicación"}
            ),
            "tiene_postores": has_bidders.map({True: "Con postores", False: "Sin postores"}),
        }
    )
    return pd.crosstab(frame["tiene_adjudicacion"], frame["tiene_postores"], margins=True)


def missing_shares(
    fact_proceso: pd.DataFrame, columns: Iterable[str] = AUDITED_COLUMNS
) -> pd.DataFrame:
    """Porcentaje de vacíos de las columnas candidatas, en total y entre los adjudicados."""
    awarded = pd.to_numeric(fact_proceso["monto_adjudicado_pen"], errors="coerce").gt(0)
    rows = []
    for column in columns:
        values = pd.to_numeric(fact_proceso[column], errors="coerce")
        empty = values.isna() | values.le(0) if column == "valor_referencial_pen" else values.isna()
        rows.append(
            {
                "columna": column,
                "pct_vacios": float(empty.mean()) if len(empty) else float("nan"),
                "pct_vacios_adjudicados": float(empty[awarded].mean())
                if awarded.any()
                else float("nan"),
            }
        )
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Páginas crudas de la API (data/raw/api)
# -----------------------------------------------------------------------------
def iter_raw_records(raw_api_dir: str | Path) -> Iterator[dict[str, Any]]:
    """Records OCDS guardados por las corridas con ``--source api`` (todas las carpetas)."""
    for path in sorted(Path(raw_api_dir).glob("**/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("No se pudo leer %s: %s", path, exc)
            continue
        records = payload.get("records") if isinstance(payload, dict) else None
        for record in records or []:
            if isinstance(record, dict) and isinstance(record.get("compiledRelease"), dict):
                yield record


def _award_total(release: Mapping[str, Any]) -> float | None:
    amounts = [safe_get(award, "value", "amount") for award in release.get("awards") or []]
    values = [float(a) for a in amounts if isinstance(a, int | float)]
    return sum(values) if values else None


def _tender_value(release: Mapping[str, Any]) -> float | None:
    value = safe_get(release, "tender", "value", "amount")
    return float(value) if isinstance(value, int | float) else None


def _bidder_count(release: Mapping[str, Any]) -> int:
    tenderers = safe_get(release, "tender", "tenderers") or []
    if tenderers:
        return len(tenderers)
    parties = release.get("parties") or []
    return sum(1 for p in parties if "tenderer" in (p.get("roles") or []))


def raw_record_flags(records: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Una fila por record con lo que muestra su versión compilada."""
    rows = []
    for record in records:
        compiled = record["compiledRelease"]
        value = _tender_value(compiled)
        award = _award_total(compiled)
        releases = record.get("releases") or []
        rows.append(
            {
                "ocid": record.get("ocid") or compiled.get("ocid"),
                "metodo": safe_get(compiled, "tender", "procurementMethodDetails"),
                "categoria": safe_get(compiled, "tender", "mainProcurementCategory"),
                "informacion_protegida": safe_get(
                    compiled, "tender", "hasTenderInformationProtectedByLaw"
                ),
                "tiene_valor_referencial": bool(value and value > 0),
                "tiene_adjudicacion": award is not None,
                "adjudicado_igual_referencial": bool(
                    value and award is not None and abs(award - value) < EQUAL_AMOUNT_TOLERANCE
                ),
                "n_postores": _bidder_count(compiled),
                "n_versiones": len(releases),
            }
        )
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Historia de versiones (requiere conexión a la API)
# -----------------------------------------------------------------------------
def client_from_config(oece_config: Mapping[str, Any]) -> APIClient:
    """Cliente HTTP con los encabezados, tiempos y pausas de ``api_config.yaml``."""
    retries = oece_config.get("retries") or {}
    return APIClient(
        headers=dict(oece_config.get("headers") or {}),
        timeout=float(oece_config.get("timeout_seconds", 60)),
        max_retries=int(retries.get("total", 3)),
        backoff_factor=float(retries.get("backoff_factor", 1.0)),
        min_interval=float(oece_config.get("min_interval_seconds", 0.5)),
    )


def diagnose(value_before: float | None, value_after: float | None) -> str:
    """Compara el valor referencial antes y después de la buena pro."""
    before = value_before if value_before and value_before > 0 else None
    after = value_after if value_after and value_after > 0 else None
    if before is None and after is not None:
        return DIAGNOSIS_REVEALED
    if before is not None and after is not None and abs(before - after) < EQUAL_AMOUNT_TOLERANCE:
        return DIAGNOSIS_STABLE
    return DIAGNOSIS_CHANGED


def _release_from_payload(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("releases"), list):
        return payload["releases"][0] if payload["releases"] else {}
    return payload if isinstance(payload, dict) else {}


def release_history_check(
    records: Iterable[Mapping[str, Any]], client: APIClient, *, limit: int = 200
) -> pd.DataFrame:
    """Valor referencial y postores en la última versión anterior a la buena pro.

    Solo revisa records adjudicados (hasta ``limit`` consultas a la API). La historia
    de la API empieza cuando el proceso entra a la plataforma, así que muchos procesos
    no tienen una versión anterior a la buena pro: se informan sin consultar.
    """
    rows = []
    queries = 0
    for record in records:
        compiled = record["compiledRelease"]
        award = _award_total(compiled)
        if award is None:
            continue
        releases = sorted(record.get("releases") or [], key=lambda r: str(r.get("date")))
        first_award = next(
            (i for i, r in enumerate(releases) if "award" in (r.get("tag") or [])), 0
        )
        row: dict[str, Any] = {
            "ocid": record.get("ocid") or compiled.get("ocid"),
            "metodo": safe_get(compiled, "tender", "procurementMethodDetails"),
            "valor_final": _tender_value(compiled),
            "monto_adjudicado": award,
            "valor_previo": None,
            "postores_previos": None,
        }
        if first_award == 0:
            row["diagnostico"] = DIAGNOSIS_NO_HISTORY
        elif queries >= limit:
            break
        else:
            queries += 1
            try:
                previous = _release_from_payload(client.get_json(releases[first_award - 1]["url"]))
            except (APIError, KeyError) as exc:
                logger.warning("No se pudo leer la versión previa de %s: %s", row["ocid"], exc)
                row["diagnostico"] = DIAGNOSIS_ERROR
            else:
                row["valor_previo"] = _tender_value(previous)
                row["postores_previos"] = _bidder_count(previous)
                row["diagnostico"] = diagnose(row["valor_previo"], row["valor_final"])
        row["final_igual_adjudicado"] = bool(
            row["valor_final"] and abs(row["valor_final"] - award) < EQUAL_AMOUNT_TOLERANCE
        )
        rows.append(row)
    logger.info("Historia de versiones: %d procesos, %d consultas a la API", len(rows), queries)
    return pd.DataFrame(rows)
