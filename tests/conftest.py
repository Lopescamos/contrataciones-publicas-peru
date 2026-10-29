"""Fixtures compartidas por las pruebas."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from contrataciones.utils.config_loader import load_yaml

ROOT = Path(__file__).resolve().parents[1]
SUNAT_RUC = "20131312955"  # RUC público de la SUNAT (dígito verificador válido)


def ruc_for(number: int) -> str:
    from contrataciones.sample_data import demo_ruc

    return demo_ruc(number)


def make_release(
    ocid: str,
    *,
    buyer_ruc: str = "20999000011",
    buyer_name: str = "MUNICIPALIDAD DEMO 01",
    region: str = "LIMA",
    method: str = "open",
    details: str = "Licitación Pública",
    category: str = "goods",
    value: float | None = 100_000.0,
    currency: str = "PEN",
    start: str = "2025-03-01T09:00:00-05:00",
    end: str = "2025-03-25T18:00:00-05:00",
    tenderers: list[tuple[str, str]] | None = None,
    awards: list[dict[str, Any]] | None = None,
    contracts: list[dict[str, Any]] | None = None,
    status: str = "complete",
) -> dict[str, Any]:
    """Construye un release OCDS mínimo y controlado para las pruebas."""
    tenderers = tenderers if tenderers is not None else [(ruc_for(1001), "PROVEEDOR A")]
    tender: dict[str, Any] = {
        "id": ocid.split("-")[-1],
        "title": f"LP-SM-1-2025-{ocid[-3:]}",
        "description": "ADQUISICIÓN DE PRUEBA",
        "status": status,
        "procurementMethod": method,
        "procurementMethodDetails": details,
        "mainProcurementCategory": category,
        "datePublished": start,
        "tenderers": [{"id": f"PE-RUC-{r}", "name": n} for r, n in tenderers],
    }
    if value is not None:
        tender["value"] = {"amount": value, "currency": currency}
    if start and end:
        tender["tenderPeriod"] = {"startDate": start, "endDate": end}
    parties = [
        {
            "id": f"PE-RUC-{buyer_ruc}",
            "name": buyer_name,
            "identifier": {"scheme": "PE-RUC", "id": buyer_ruc},
            "roles": ["buyer", "procuringEntity"],
            "address": {"region": region},
        }
    ]
    for ruc, name in tenderers:
        parties.append(
            {
                "id": f"PE-RUC-{ruc}",
                "name": name,
                "identifier": {"scheme": "PE-RUC", "id": ruc},
                "roles": ["tenderer"],
            }
        )
    release: dict[str, Any] = {
        "ocid": ocid,
        "id": f"{ocid}-1",
        "date": "2025-04-30T10:00:00-05:00",
        "buyer": {"id": f"PE-RUC-{buyer_ruc}", "name": buyer_name},
        "parties": parties,
        "tender": tender,
    }
    if awards is not None:
        release["awards"] = awards
    if contracts is not None:
        release["contracts"] = contracts
    return release


def award(
    award_id: str,
    amount: float,
    suppliers: list[tuple[str, str]],
    *,
    date: str = "2025-04-05T12:00:00-05:00",
    status: str = "active",
    currency: str = "PEN",
) -> dict[str, Any]:
    return {
        "id": award_id,
        "status": status,
        "date": date,
        "value": {"amount": amount, "currency": currency},
        "suppliers": [{"id": f"PE-RUC-{r}", "name": n} for r, n in suppliers],
    }


CONSORTIUM_ID = "PE-RUC-1509611"  # los consorcios usan un código interno de 7 dígitos


def make_oece_release(
    ocid: str = "ocds-dgv273-seacev3-2024-1984-7",
    *,
    entity_code: str = "1984",
    entity_ruc: str | None = SUNAT_RUC,
    department: str = "HUANCAVELICA",
    region: str = "HUAYTARA",
    convocatoria: str = "2024-04-17T00:00:00-05:00",
    enquiry: tuple[str, str] | None = ("2024-04-18T00:01:00-05:00", "2024-05-02T23:59:00-05:00"),
    value: float = 168_000.0,
    currency: str = "PEN",
    amount_pen: float | None = None,
    consortium: bool = True,
) -> dict[str, Any]:
    """Release compilado con la forma real de la publicación del OECE.

    * Entidad identificada con ``PE-CONSUCODE`` y RUC en ``additionalIdentifiers``.
    * ``address.region`` con la provincia y ``address.department`` con el departamento.
    * ``tenderPeriod`` con inicio = fin; el plazo real está en ``enquiryPeriod``.
    * Estados vacíos, ``value.amount_PEN`` y postores solo en ``parties``.
    * Ganador: un consorcio con código interno (no RUC).
    """
    name = "MUNICIPALIDAD DISTRITAL DEMO"
    buyer: dict[str, Any] = {
        "id": f"PE-CONSUCODE-{entity_code}",
        "name": name,
        "identifier": {"id": entity_code, "scheme": "PE-CONSUCODE", "legalName": name},
        "address": {
            "locality": "DISTRITO DEMO",
            "region": region,
            "department": department,
            "countryName": "PERU",
        },
        "roles": ["buyer", "procuringEntity"],
    }
    if entity_ruc:
        buyer["additionalIdentifiers"] = [{"id": entity_ruc, "scheme": "PE-RUC", "legalName": name}]
    if consortium:
        winner_id, winner_name = CONSORTIUM_ID, "CONSORCIO DEMO"
    else:
        winner_id, winner_name = f"PE-RUC-{ruc_for(1001)}", "PROVEEDOR A S.A.C."
    other = ruc_for(1002)
    winner: dict[str, Any] = {
        "id": winner_id,
        "name": winner_name,
        "identifier": {"scheme": "PE-RUC", "id": winner_id.rsplit("-", 1)[-1]},
        "roles": ["tenderer", "supplier"],
    }
    if consortium:
        winner["address"] = {"countryName": "PERU"}  # sin departamento, como en la fuente
    parties = [
        buyer,
        winner,
        {
            "id": f"PE-RUC-{other}",
            "name": "PROVEEDOR B S.A.C.",
            "identifier": {"scheme": "PE-RUC", "id": other},
            "roles": ["tenderer"],
        },
    ]
    tender: dict[str, Any] = {
        "id": "999959",
        "title": "AS-SM-1-2024-MDD-1",
        "procuringEntity": {"id": buyer["id"], "name": name},
        "datePublished": "2024-04-17T14:57:00-05:00",
        "procurementMethod": "open",
        "procurementMethodDetails": "Adjudicación Simplificada",
        "mainProcurementCategory": "services",
        "value": {
            "amount": value,
            "currency": currency,
            "amount_PEN": value if amount_pen is None else amount_pen,
        },
        "tenderPeriod": {"startDate": convocatoria, "endDate": convocatoria},
    }
    if enquiry:
        tender["enquiryPeriod"] = {"startDate": enquiry[0], "endDate": enquiry[1]}
    award_id = f"999959-{winner_id.rsplit('-', 1)[-1]}"
    return {
        "ocid": ocid,
        "id": f"{ocid}-2024-09-12T10:15:30-05:00",
        "date": "2024-09-12T10:15:30-05:00",
        "tag": ["compiled"],
        "buyer": {"id": buyer["id"], "name": name},
        "parties": parties,
        "tender": tender,
        "awards": [
            {
                "id": award_id,
                "value": {"amount": 160_000.0, "currency": currency},
                "date": "2024-04-24T00:00:00-05:00",
                "suppliers": [{"id": winner_id, "name": winner_name}],
            }
        ],
        "contracts": [
            {
                "id": "2257286",
                "awardID": award_id,
                "value": {"amount": 160_000.0, "currency": currency},
                "dateSigned": "2024-05-16T00:00:00-05:00",
                "period": {
                    "startDate": "2024-05-17T00:00:00-05:00",
                    "endDate": "2024-06-16T00:00:00-05:00",
                    "durationInDays": 30,
                },
            }
        ],
        "dataSegmentation": {"id": "2024-04"},
    }


@pytest.fixture
def risk_rules() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "risk_rules.yaml")


@pytest.fixture
def sample_dir() -> Path:
    return ROOT / "data" / "sample"


@pytest.fixture
def tmp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Copia mínima del proyecto en una carpeta temporal (no ensucia el repositorio)."""
    project = tmp_path / "proyecto"
    shutil.copytree(ROOT / "config", project / "config")
    shutil.copytree(ROOT / "sql", project / "sql")
    shutil.copytree(ROOT / "data" / "sample", project / "data" / "sample")
    (project / "pyproject.toml").write_text("[project]\nname='tmp'\n", encoding="utf-8")
    monkeypatch.setenv("CONTRATACIONES_HOME", str(project))
    monkeypatch.setenv("DB_PROFILE", "local_sqlite")
    return project
