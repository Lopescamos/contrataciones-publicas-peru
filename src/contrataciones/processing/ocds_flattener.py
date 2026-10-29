"""Aplanado de releases OCDS en tablas relacionales (capa staging).

Un release compilado es un JSON anidado. Este módulo lo descompone en cinco
tablas planas, una por entidad del estándar:

=================  ===========================================  ==================
Tabla              Grano (una fila por...)                       Origen OCDS
=================  ===========================================  ==================
procesos           proceso de contratación (``ocid``)            ``tender``, ``buyer``
partes             organización participante en un proceso       ``parties[]``
postores           postor (oferente) en un proceso               ``tender.tenderers[]``
adjudicaciones     proveedor adjudicado en una adjudicación      ``awards[].suppliers[]``
contratos          contrato                                      ``contracts[]``
=================  ===========================================  ==================

Para no agotar la memoria con archivos de cientos de MB, las filas se escriben
por bloques (``chunk_size``) en archivos Parquet con esquema fijo. Los tipos se
mantienen simples (texto, decimal y entero); la limpieza ocurre después.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from contrataciones.utils.helpers import safe_get
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

_S, _F, _I = pa.string(), pa.float64(), pa.int64()

STAGING_SCHEMAS: dict[str, pa.Schema] = {
    "procesos": pa.schema(
        [
            ("ocid", _S),
            ("release_id", _S),
            ("release_date", _S),
            ("tender_id", _S),
            ("tender_title", _S),
            ("tender_description", _S),
            ("tender_status", _S),
            ("procurement_method", _S),
            ("procurement_method_details", _S),
            ("main_category", _S),
            ("tender_value_amount", _F),
            ("tender_value_currency", _S),
            ("tender_value_amount_pen", _F),
            ("tender_date_published", _S),
            ("tender_period_start", _S),
            ("tender_period_end", _S),
            ("enquiry_period_start", _S),
            ("enquiry_period_end", _S),
            ("number_of_tenderers", _I),
            ("buyer_id", _S),
            ("buyer_name", _S),
            ("procuring_entity_id", _S),
            ("procuring_entity_name", _S),
            ("n_awards", _I),
            ("n_contracts", _I),
            ("n_items", _I),
        ]
    ),
    "partes": pa.schema(
        [
            ("ocid", _S),
            ("party_id", _S),
            ("party_name", _S),
            ("identifier_scheme", _S),
            ("identifier_id", _S),
            ("additional_ruc", _S),
            ("roles", _S),
            ("region", _S),
            ("locality", _S),
            ("country_name", _S),
        ]
    ),
    "postores": pa.schema([("ocid", _S), ("tenderer_id", _S), ("tenderer_name", _S)]),
    "adjudicaciones": pa.schema(
        [
            ("ocid", _S),
            ("award_id", _S),
            ("award_status", _S),
            ("award_date", _S),
            ("award_value_amount", _F),
            ("award_value_currency", _S),
            ("award_value_amount_pen", _F),
            ("supplier_id", _S),
            ("supplier_name", _S),
            ("n_suppliers", _I),
        ]
    ),
    "contratos": pa.schema(
        [
            ("ocid", _S),
            ("contract_id", _S),
            ("award_id", _S),
            ("contract_status", _S),
            ("date_signed", _S),
            ("contract_value_amount", _F),
            ("contract_value_currency", _S),
            ("contract_value_amount_pen", _F),
            ("period_start", _S),
            ("period_end", _S),
        ]
    ),
}
STAGING_TABLES = tuple(STAGING_SCHEMAS)


# ---------------------------------------------------------------------------
# Conversión de valores
# ---------------------------------------------------------------------------
def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        try:
            number = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None
    return None if number != number else number


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _region(address: Any) -> str | None:
    """Departamento de la dirección.

    En la publicación del OECE ``address.region`` puede contener la provincia
    (p. ej. "HUAYTARA") y ``address.department`` el departamento ("HUANCAVELICA"),
    por eso se prioriza ``department`` (extensión Department del publicador).
    """
    if not isinstance(address, dict):
        return None
    for key in ("department", "departamento", "region"):
        if _text(address.get(key)):
            return _text(address.get(key))
    return None


RUC_SCHEMES = frozenset({"PE-RUC"})


def _additional_ruc(party: dict[str, Any]) -> str | None:
    """RUC publicado en ``additionalIdentifiers`` (esquema ``PE-RUC``).

    El OECE identifica a las entidades con un código ``PE-CONSUCODE-<n>`` y
    publica su RUC como identificador adicional.
    """
    for identifier in _as_list(party.get("additionalIdentifiers")):
        if not isinstance(identifier, dict):
            continue
        if str(identifier.get("scheme") or "").strip().upper() in RUC_SCHEMES:
            value = _text(identifier.get("id"))
            if value:
                return value
    return None


# ---------------------------------------------------------------------------
# Aplanado de un release
# ---------------------------------------------------------------------------
def flatten_release(release: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Convierte un release OCDS en filas para cada tabla de staging."""
    ocid = _text(release.get("ocid"))
    tender = release.get("tender") if isinstance(release.get("tender"), dict) else {}
    buyer = release.get("buyer") if isinstance(release.get("buyer"), dict) else {}
    procuring = (
        tender.get("procuringEntity") if isinstance(tender.get("procuringEntity"), dict) else {}
    )
    awards = [a for a in _as_list(release.get("awards")) if isinstance(a, dict)]
    contracts = [c for c in _as_list(release.get("contracts")) if isinstance(c, dict)]

    proceso = {
        "ocid": ocid,
        "release_id": _text(release.get("id")),
        "release_date": _text(release.get("date")),
        "tender_id": _text(tender.get("id")),
        "tender_title": _text(tender.get("title")),
        "tender_description": _text(tender.get("description")),
        "tender_status": _text(tender.get("status")),
        "procurement_method": _text(tender.get("procurementMethod")),
        "procurement_method_details": _text(tender.get("procurementMethodDetails")),
        "main_category": _text(tender.get("mainProcurementCategory")),
        "tender_value_amount": _number(safe_get(tender, "value", "amount")),
        "tender_value_currency": _text(safe_get(tender, "value", "currency")),
        # Extensión del OECE: monto convertido a soles por el publicador.
        "tender_value_amount_pen": _number(safe_get(tender, "value", "amount_PEN")),
        "tender_date_published": _text(tender.get("datePublished")),
        "tender_period_start": _text(safe_get(tender, "tenderPeriod", "startDate")),
        "tender_period_end": _text(safe_get(tender, "tenderPeriod", "endDate")),
        "enquiry_period_start": _text(safe_get(tender, "enquiryPeriod", "startDate")),
        "enquiry_period_end": _text(safe_get(tender, "enquiryPeriod", "endDate")),
        "number_of_tenderers": _integer(tender.get("numberOfTenderers")),
        "buyer_id": _text(buyer.get("id")) or _text(procuring.get("id")),
        "buyer_name": _text(buyer.get("name")) or _text(procuring.get("name")),
        "procuring_entity_id": _text(procuring.get("id")),
        "procuring_entity_name": _text(procuring.get("name")),
        "n_awards": len(awards),
        "n_contracts": len(contracts),
        "n_items": len(_as_list(tender.get("items"))),
    }

    partes = []
    for party in _as_list(release.get("parties")):
        if not isinstance(party, dict):
            continue
        roles = sorted({str(r) for r in _as_list(party.get("roles")) if r})
        partes.append(
            {
                "ocid": ocid,
                "party_id": _text(party.get("id")),
                "party_name": _text(party.get("name")),
                "identifier_scheme": _text(safe_get(party, "identifier", "scheme")),
                "identifier_id": _text(safe_get(party, "identifier", "id")),
                "additional_ruc": _additional_ruc(party),
                "roles": "|".join(roles) or None,
                "region": _region(party.get("address")),
                "locality": _text(safe_get(party, "address", "locality")),
                "country_name": _text(safe_get(party, "address", "countryName")),
            }
        )

    tenderers = [t for t in _as_list(tender.get("tenderers")) if isinstance(t, dict)]
    if not tenderers:
        # Si tender.tenderers no viene informado, se usan las partes con rol "tenderer".
        tenderers = [
            p
            for p in _as_list(release.get("parties"))
            if isinstance(p, dict) and "tenderer" in _as_list(p.get("roles"))
        ]
    postores = [
        {"ocid": ocid, "tenderer_id": _text(t.get("id")), "tenderer_name": _text(t.get("name"))}
        for t in tenderers
    ]

    adjudicaciones = []
    for award in awards:
        suppliers = [s for s in _as_list(award.get("suppliers")) if isinstance(s, dict)] or [{}]
        for supplier in suppliers:
            adjudicaciones.append(
                {
                    "ocid": ocid,
                    "award_id": _text(award.get("id")),
                    "award_status": _text(award.get("status")),
                    "award_date": _text(award.get("date")),
                    "award_value_amount": _number(safe_get(award, "value", "amount")),
                    "award_value_currency": _text(safe_get(award, "value", "currency")),
                    "award_value_amount_pen": _number(safe_get(award, "value", "amount_PEN")),
                    "supplier_id": _text(supplier.get("id")),
                    "supplier_name": _text(supplier.get("name")),
                    "n_suppliers": len([s for s in suppliers if s]),
                }
            )

    contratos = [
        {
            "ocid": ocid,
            "contract_id": _text(contract.get("id")),
            "award_id": _text(contract.get("awardID")),
            "contract_status": _text(contract.get("status")),
            "date_signed": _text(contract.get("dateSigned")),
            "contract_value_amount": _number(safe_get(contract, "value", "amount")),
            "contract_value_currency": _text(safe_get(contract, "value", "currency")),
            "contract_value_amount_pen": _number(safe_get(contract, "value", "amount_PEN")),
            "period_start": _text(safe_get(contract, "period", "startDate")),
            "period_end": _text(safe_get(contract, "period", "endDate")),
        }
        for contract in contracts
    ]

    return {
        "procesos": [proceso],
        "partes": partes,
        "postores": postores,
        "adjudicaciones": adjudicaciones,
        "contratos": contratos,
    }


# ---------------------------------------------------------------------------
# Escritura por bloques
# ---------------------------------------------------------------------------
class StagingWriter:
    """Acumula filas por tabla y las escribe en Parquet por bloques."""

    def __init__(self, directory: str | Path, chunk_size: int = 20000) -> None:
        self.directory = Path(directory)
        self.chunk_size = max(1, int(chunk_size))
        self.buffers: dict[str, list[dict[str, Any]]] = {name: [] for name in STAGING_TABLES}
        self.parts: dict[str, int] = dict.fromkeys(STAGING_TABLES, 0)
        self.counts: dict[str, int] = dict.fromkeys(STAGING_TABLES, 0)
        if self.directory.exists():
            shutil.rmtree(self.directory)
        for name in STAGING_TABLES:
            (self.directory / name).mkdir(parents=True, exist_ok=True)

    def add(self, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
        for name, rows in rows_by_table.items():
            if not rows:
                continue
            self.buffers[name].extend(rows)
            self.counts[name] += len(rows)
            if len(self.buffers[name]) >= self.chunk_size:
                self._flush(name)

    def _flush(self, name: str) -> None:
        rows = self.buffers[name]
        if not rows and self.parts[name] > 0:
            return
        self.parts[name] += 1
        table = pa.Table.from_pylist(rows, schema=STAGING_SCHEMAS[name])
        pq.write_table(table, self.directory / name / f"part-{self.parts[name]:05d}.parquet")
        self.buffers[name] = []

    def close(self) -> dict[str, int]:
        """Escribe lo pendiente (y un archivo vacío si la tabla no tuvo filas)."""
        for name in STAGING_TABLES:
            if self.buffers[name] or self.parts[name] == 0:
                self._flush(name)
        return dict(self.counts)


def stage_releases(
    releases: Iterable[dict[str, Any]], directory: str | Path, chunk_size: int = 20000
) -> dict[str, int]:
    """Aplana todos los releases en ``directory/<tabla>/part-*.parquet``.

    Returns:
        Conteo de filas escritas por tabla.
    """
    writer = StagingWriter(directory, chunk_size=chunk_size)
    for processed, release in enumerate(releases, start=1):
        writer.add(flatten_release(release))
        if processed % 50000 == 0:
            logger.info("Procesos aplanados: %d", processed)
    counts = writer.close()
    logger.info("Staging listo: %s", ", ".join(f"{k}={v:,}" for k, v in counts.items()))
    return counts


def read_staging(directory: str | Path, table: str) -> pd.DataFrame:
    """Lee una tabla de staging (todas sus partes) como DataFrame."""
    path = Path(directory) / table
    if not path.exists():
        raise FileNotFoundError(f"No existe la tabla de staging '{table}' en {directory}")
    return pq.read_table(path, schema=STAGING_SCHEMAS[table]).to_pandas()
