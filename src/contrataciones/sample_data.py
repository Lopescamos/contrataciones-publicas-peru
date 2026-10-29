"""Generador de datos SINTÉTICOS de demostración.

Produce archivos con la misma estructura que las fuentes reales para que el
pipeline, las pruebas y los notebooks funcionen sin conexión:

* ``ocds_sample.jsonl``      releases compilados OCDS (un proceso por línea).
* ``sanciones_sample.xlsx``  registro de sanciones con títulos sobre la tabla.
* ``tipo_cambio_sample.csv`` tipo de cambio diario S/ por US$.

Todo es ficticio: entidades y proveedores se llaman "DEMO", los OCID usan el
prefijo ``ocds-demo00`` y los RUC el rango ``20999xxxxxx``. Las cifras no
representan la realidad y no deben usarse para conclusiones.

La estructura imita la publicación real del OECE: entidades con código
``PE-CONSUCODE`` y RUC en ``additionalIdentifiers``, ``tenderPeriod`` con
inicio = fin en parte de los procesos, ``enquiryPeriod``, estados vacíos,
consorcios con código interno de 7 dígitos, valores referenciales en 0 y el
monto en soles publicado (``amount_PEN``).
"""

from __future__ import annotations

import csv
import json
import math
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from contrataciones.utils.constants import DEPARTAMENTOS, RUC_CHECK_WEIGHTS
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

OCID_PREFIX = "ocds-demo00"
_LIMA_OFFSET = "-05:00"
CURRENCY_NAMES = {"PEN": "Soles", "USD": "Dólares americanos"}
_SEGMENTATION_CRITERIA = ["añoInicioConvocatoria", "mesInicioConvocatoria"]

# (detalle, procurementMethod OCDS, sigla, peso, mediana S/, días de presentación,
#  días de consultas, postores)
METHODS: list[
    tuple[str, str, str, float, float, tuple[int, int], tuple[int, int], tuple[int, int]]
] = [
    ("Adjudicación Simplificada", "open", "AS", 0.38, 180_000, (10, 26), (2, 8), (1, 6)),
    ("Subasta Inversa Electrónica", "open", "SIE", 0.12, 420_000, (9, 22), (1, 4), (1, 7)),
    ("Licitación Pública", "open", "LP", 0.09, 3_200_000, (18, 40), (8, 15), (1, 8)),
    ("Concurso Público", "open", "CP", 0.08, 1_600_000, (16, 35), (8, 15), (1, 6)),
    ("Comparación de Precios", "open", "COMPRE", 0.12, 70_000, (7, 18), (1, 3), (1, 4)),
    ("Selección de Consultores Individuales", "open", "SCI", 0.10, 45_000, (8, 20), (2, 6), (1, 4)),
    ("Contratación Directa", "direct", "CD", 0.11, 650_000, (0, 0), (0, 0), (1, 1)),
]
CATEGORIES_BY_METHOD: dict[str, list[str]] = {
    "AS": ["goods", "services", "works"],
    "SIE": ["goods"],
    "LP": ["goods", "works"],
    "CP": ["services"],
    "COMPRE": ["goods", "services"],
    "SCI": ["services"],
    "CD": ["goods", "services", "works"],
}
OBJECTS: dict[str, list[str]] = {
    "goods": [
        "ADQUISICIÓN DE MEDICAMENTOS",
        "ADQUISICIÓN DE EQUIPOS DE CÓMPUTO",
        "ADQUISICIÓN DE MOBILIARIO ESCOLAR",
        "ADQUISICIÓN DE COMBUSTIBLE",
        "ADQUISICIÓN DE MATERIAL MÉDICO",
        "ADQUISICIÓN DE ALIMENTOS",
    ],
    "services": [
        "SERVICIO DE LIMPIEZA",
        "SERVICIO DE VIGILANCIA",
        "SERVICIO DE MANTENIMIENTO DE VEHÍCULOS",
        "SERVICIO DE CONSULTORÍA",
        "SERVICIO DE SOPORTE INFORMÁTICO",
        "SERVICIO DE TRANSPORTE",
    ],
    "works": [
        "EJECUCIÓN DE LA OBRA MEJORAMIENTO DE PISTAS",
        "EJECUCIÓN DE LA OBRA CONSTRUCCIÓN DE AULAS",
        "EJECUCIÓN DE LA OBRA AMPLIACIÓN DE AGUA POTABLE",
        "EJECUCIÓN DE LA OBRA REHABILITACIÓN DE CAMINO VECINAL",
    ],
}
ENTITY_TYPES = [
    "MUNICIPALIDAD",
    "GOBIERNO REGIONAL",
    "HOSPITAL",
    "UNIVERSIDAD NACIONAL",
    "MINISTERIO",
    "PROGRAMA NACIONAL",
    "EMPRESA PÚBLICA",
]
SUFFIXES = ["S.A.C.", "E.I.R.L.", "S.A.", "S.R.L."]


def ruc_check_digit(first_ten: str) -> int:
    """Dígito verificador (módulo 11) de los 10 primeros dígitos de un RUC."""
    total = sum(int(d) * w for d, w in zip(first_ten, RUC_CHECK_WEIGHTS, strict=True))
    check = 11 - (total % 11)
    return 0 if check == 10 else 1 if check == 11 else check


def demo_ruc(number: int) -> str:
    """RUC sintético válido en el rango 20999xxxxxx."""
    first_ten = f"20999{number:05d}"
    return first_ten + str(ruc_check_digit(first_ten))


def _iso(day: date, hour: int = 9, minute: int = 0) -> str:
    return datetime.combine(day, time(hour, minute)).isoformat() + _LIMA_OFFSET


def _weighted_choice(rng: random.Random, items: list[Any], weights: list[float]) -> Any:
    return rng.choices(items, weights=weights, k=1)[0]


def _value(amount: float, currency: str, amount_pen: float | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "amount": amount,
        "currency": currency,
        "currencyName": CURRENCY_NAMES[currency],
    }
    if amount_pen is not None:
        value["amount_PEN"] = amount_pen
    return value


def _same_day_period(day: date) -> dict[str, str]:
    """Periodo con inicio = fin (forma en que el OECE publica tenderPeriod)."""
    return {"startDate": _iso(day, 0), "endDate": _iso(day, 0)}


def build_exchange_rates(rng: random.Random, start: date, end: date) -> dict[date, float]:
    """Serie diaria (días hábiles) de tipo de cambio S/ por US$ simulada."""
    rates: dict[date, float] = {}
    rate, day = 3.72, start
    while day <= end:
        if day.weekday() < 5:
            rate = min(3.95, max(3.45, rate + rng.gauss(0, 0.006)))
            rates[day] = round(rate, 4)
        day += timedelta(days=1)
    return rates


def _rate_on(rates: dict[date, float], day: date) -> float:
    """Último tipo de cambio disponible en la fecha o hasta 10 días antes."""
    for offset in range(11):
        found = rates.get(day - timedelta(days=offset))
        if found:
            return found
    return 3.72


def build_catalogs(
    rng: random.Random, n_entities: int = 30, n_suppliers: int = 180, n_consortia: int = 24
) -> dict[str, Any]:
    """Entidades, proveedores y consorcios ficticios.

    Igual que en la publicación del OECE: las entidades se identifican con un
    código ``PE-CONSUCODE`` y su RUC va en ``additionalIdentifiers``; los
    consorcios usan un código interno de 7 dígitos (no un RUC).
    """
    regions = list(DEPARTAMENTOS)
    region_weights = [6.0 if r == "LIMA" else 1.0 for r in regions]
    entities = []
    for i in range(1, n_entities + 1):
        kind = ENTITY_TYPES[(i - 1) % len(ENTITY_TYPES)]
        department = _weighted_choice(rng, regions, region_weights)
        entities.append(
            {
                "code": str(1000 + i),
                # La última entidad no publica RUC (prueba la llave alternativa).
                "ruc": demo_ruc(i) if i < n_entities else None,
                "name": f"{kind} DEMO {i:02d}",
                "short": f"DEMO{i:02d}",
                "department": department,
                # address.region a veces trae la provincia en lugar del departamento.
                "region": department if i % 3 else f"PROVINCIA DEMO {i:02d}",
                "locality": f"DISTRITO DEMO {i:02d}",
            }
        )
    suppliers = []
    for i in range(1, n_suppliers + 1):
        ruc = demo_ruc(1000 + i)
        suppliers.append(
            {
                "party_id": f"PE-RUC-{ruc}",
                "code": ruc,
                "ruc": ruc,
                "name": f"PROVEEDOR DEMO {i:03d} {SUFFIXES[i % len(SUFFIXES)]}",
            }
        )
    consortia = []
    for i in range(1, n_consortia + 1):
        code = f"15{i:05d}"
        consortia.append(
            {
                "party_id": f"PE-RUC-{code}",
                "code": code,
                "ruc": None,
                "name": f"CONSORCIO DEMO {i:02d}",
            }
        )
    # Algunas entidades tienen un proveedor "favorito" (patrón de concentración).
    favorites = {entities[i]["code"]: suppliers[i * 7]["party_id"] for i in (2, 5, 11, 17)}
    return {
        "entities": entities,
        "suppliers": suppliers,
        "consortia": consortia,
        "favorites": favorites,
    }


def _buyer_party(entity: dict[str, Any]) -> dict[str, Any]:
    party: dict[str, Any] = {
        "id": f"PE-CONSUCODE-{entity['code']}",
        "name": entity["name"],
        "identifier": {"id": entity["code"], "scheme": "PE-CONSUCODE", "legalName": entity["name"]},
        "address": {
            "locality": entity["locality"],
            "region": entity["region"],
            "department": entity["department"],
            "countryName": "PERU",
        },
        "roles": ["buyer", "procuringEntity"],
    }
    if entity["ruc"]:
        party["additionalIdentifiers"] = [
            {"id": entity["ruc"], "scheme": "PE-RUC", "legalName": entity["name"]}
        ]
    return party


def _supplier_party(supplier: dict[str, Any], roles: list[str]) -> dict[str, Any]:
    # Como en el OECE: la dirección del proveedor no se publica (a lo sumo, el país).
    return {
        "id": supplier["party_id"],
        "name": supplier["name"],
        "identifier": {"scheme": "PE-RUC", "id": supplier["code"], "legalName": supplier["name"]},
        "roles": roles,
    }


def generate_release(
    rng: random.Random,
    seq: int,
    catalogs: dict[str, Any],
    start: date,
    end: date,
    rates: dict[date, float] | None = None,
) -> dict[str, Any]:
    """Genera un release compilado OCDS sintético con las particularidades del OECE."""
    entities, suppliers = catalogs["entities"], catalogs["suppliers"]
    by_party_id = {s["party_id"]: s for s in suppliers}
    method = _weighted_choice(rng, METHODS, [m[3] for m in METHODS])
    detail, ocds_method, acronym, _, median, days_range, enquiry_range, bidders_range = method
    entity = rng.choice(entities)
    category = rng.choice(CATEGORIES_BY_METHOD[acronym])
    published = start + timedelta(days=rng.randint(0, (end - start).days))
    currency = "USD" if rng.random() < 0.02 else "PEN"
    amount = round(median * math.exp(rng.gauss(0, 0.9)), 2)
    if currency == "USD":
        amount = round(amount / 3.7, 2)
    rate = _rate_on(rates or {}, published) if currency == "USD" else 1.0
    # Valor referencial 0 = no informado (ocurre en la fuente real).
    declared = 0.0 if rng.random() < 0.04 else amount

    ocid = f"{OCID_PREFIX}-{seq:06d}"
    buyer_id = f"PE-CONSUCODE-{entity['code']}"
    title = f"{acronym}-SM-{rng.randint(1, 250)}-{published.year}-{entity['short']}-1"
    tender: dict[str, Any] = {
        "id": str(100000 + seq),
        "title": title,
        "description": f"{rng.choice(OBJECTS[category])} - {entity['name']}",
        "procuringEntity": {"id": buyer_id, "name": entity["name"]},
        "datePublished": _iso(published, 8, 30),
        "procurementMethod": ocds_method,
        "procurementMethodDetails": detail,
        "mainProcurementCategory": category,
        "value": _value(declared, currency, round(declared * rate, 2)),
    }
    if ocds_method != "direct":
        duration = rng.randint(*days_range)
        close_date = published + timedelta(days=duration)
        if rng.random() < 0.4:
            # Como en el OECE: tenderPeriod solo trae la fecha de convocatoria.
            tender["tenderPeriod"] = _same_day_period(published)
        else:
            tender["tenderPeriod"] = {
                "startDate": _iso(published, 9),
                "endDate": _iso(close_date, 18),
            }
        enquiry_days = rng.randint(*enquiry_range)
        enquiry_start = published + timedelta(days=1)
        tender["enquiryPeriod"] = {
            "startDate": _iso(enquiry_start, 0, 1),
            "endDate": _iso(enquiry_start + timedelta(days=enquiry_days), 23, 59),
            "durationInDays": enquiry_days,
        }
    else:
        close_date = published
        tender["tenderPeriod"] = _same_day_period(published)

    favorite = catalogs["favorites"].get(entity["code"])
    n_bidders = 1 if rng.random() < 0.18 else rng.randint(*bidders_range)
    pool = rng.sample(suppliers, k=min(len(suppliers), max(n_bidders, 1)))
    if favorite and rng.random() < 0.75:
        pool[0] = by_party_id[favorite]
    elif rng.random() < 0.08:
        pool[0] = rng.choice(catalogs["consortia"])
    bidders = list({s["party_id"]: s for s in pool}.values())[: max(n_bidders, 1)]
    tenderers = [{"id": s["party_id"], "name": s["name"]} for s in bidders]
    if len(tenderers) > 1 and rng.random() < 0.03:
        tenderers.append(dict(tenderers[-1]))  # duplicado (problema conocido de la fuente)
    if rng.random() < 0.9:
        tender["tenderers"] = tenderers  # si falta, los postores salen de "parties"
        tender["numberOfTenderers"] = len(bidders)

    cancelled = rng.random() < 0.04
    awards: list[dict[str, Any]] = []
    contracts: list[dict[str, Any]] = []
    winners: list[dict[str, Any]] = []
    last_date = close_date
    if cancelled:
        tender["status"] = "cancelled"
    else:
        first = bidders[0]
        keeps_first = first["party_id"] == favorite or first["ruc"] is None
        winner = first if keeps_first else rng.choice(bidders)
        winners = [winner]
        if rng.random() < 0.02:
            partner = rng.choice(suppliers)
            if partner["party_id"] != winner["party_id"]:
                winners.append(partner)
        draw = rng.random()
        if draw < 0.15:
            ratio = rng.uniform(0.98, 1.0)
        elif draw < 0.18:
            ratio = rng.uniform(1.01, 1.10)
        else:
            ratio = rng.uniform(0.75, 0.97)
        award_date = close_date + timedelta(days=rng.randint(3, 25))
        unsuccessful = rng.random() < 0.02
        award_id = f"{tender['id']}-{winner['code']}"
        award: dict[str, Any] = {
            "id": award_id,
            "value": _value(round(amount * ratio, 2), currency),
            "date": _iso(award_date, 0),
            "suppliers": [{"id": w["party_id"], "name": w["name"]} for w in winners],
        }
        if unsuccessful:
            award["status"] = "unsuccessful"  # en la fuente real el estado suele venir vacío
            tender["status"] = "unsuccessful"
        awards.append(award)
        last_date = award_date
        if not unsuccessful and rng.random() < 0.88:
            signed = award_date + timedelta(days=rng.randint(5, 20))
            start_day = signed + timedelta(days=rng.randint(1, 10))
            months = rng.randint(1, 12)
            contract: dict[str, Any] = {
                "id": str(2_000_000 + seq),
                "awardID": award_id if rng.random() > 0.03 else None,
                "title": f"CONTRATO N° {rng.randint(1, 300):03d}-{signed.year}-{entity['short']}",
                "status": rng.choice(["active", "terminated"]) if rng.random() < 0.3 else None,
                "dateSigned": _iso(signed, 0),
                "value": _value(round(amount * ratio, 2), currency),
                "period": {
                    "startDate": _iso(start_day, 0),
                    "endDate": _iso(start_day + timedelta(days=30 * months), 0),
                    "durationInDays": 30 * months,
                },
            }
            contracts.append({k: v for k, v in contract.items() if v is not None})
            last_date = signed

    winner_ids = {w["party_id"] for w in winners}
    parties = [_buyer_party(entity)]
    for bidder in bidders:
        roles = ["tenderer", "supplier"] if bidder["party_id"] in winner_ids else ["tenderer"]
        parties.append(_supplier_party(bidder, roles))
    bidder_ids = {b["party_id"] for b in bidders}
    for partner in winners:
        if partner["party_id"] not in bidder_ids:
            parties.append(_supplier_party(partner, ["supplier"]))

    release: dict[str, Any] = {
        "ocid": ocid,
        "id": f"{ocid}-{last_date.strftime('%Y%m%d')}",
        "date": _iso(last_date, 20),
        "tag": ["compiled"],
        "initiationType": "tender",
        "language": "es",
        "buyer": {"id": buyer_id, "name": entity["name"]},
        "parties": parties,
        "tender": tender,
        "dataSegmentation": {"id": f"{published:%Y-%m}", "criteria": _SEGMENTATION_CRITERIA},
    }
    if awards:
        release["awards"] = awards
    if contracts:
        release["contracts"] = contracts
    return release


def generate_sanctions(
    rng: random.Random, catalogs: dict[str, Any], releases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Sanciones sintéticas: algunas se superponen con adjudicaciones (activa RF06).

    Solo se sanciona a proveedores con RUC: las sanciones del Tribunal recaen en
    personas naturales o jurídicas, no en el consorcio.
    """
    names = {s["ruc"]: s["name"] for s in catalogs["suppliers"]}
    awarded: dict[str, list[date]] = {}
    for release in releases:
        for award in release.get("awards", []):
            for supplier in award.get("suppliers", []):
                ruc = supplier["id"].replace("PE-RUC-", "")
                if ruc in names:
                    awarded.setdefault(ruc, []).append(date.fromisoformat(award["date"][:10]))
    rows: list[dict[str, Any]] = []
    candidates = sorted(awarded)
    rng.shuffle(candidates)
    for index, ruc in enumerate(candidates[:12]):
        pivot = rng.choice(awarded[ruc])
        if index < 6:  # sanción vigente durante una adjudicación
            start = pivot - timedelta(days=rng.randint(10, 120))
            end: date | None = pivot + timedelta(days=rng.randint(30, 400))
        else:  # sanción anterior (ya cumplida al momento de adjudicarse)
            end = pivot - timedelta(days=rng.randint(30, 300))
            start = end - timedelta(days=rng.randint(90, 720))
        definitive = index == 0
        rows.append(
            {
                "ruc": ruc,
                "nombre": names[ruc],
                "tipo": "INHABILITACIÓN DEFINITIVA" if definitive else "INHABILITACIÓN TEMPORAL",
                "inicio": start,
                "fin": None if definitive else end,
                "resolucion": (
                    f"RES. N° {rng.randint(100, 4999):04d}-{start.year}-TCP-S{rng.randint(1, 9)}"
                ),
                "motivo": rng.choice(
                    [
                        "Presentar información inexacta",
                        "Incumplir obligaciones contractuales",
                        "Presentar documentación falsa",
                        "Desistirse de la oferta",
                    ]
                ),
            }
        )
    rows.append(
        {
            "ruc": demo_ruc(9000),
            "nombre": "PROVEEDOR DEMO SIN CONTRATOS S.A.C.",
            "tipo": "INHABILITACIÓN TEMPORAL",
            "inicio": date(2023, 3, 1),
            "fin": date(2024, 9, 1),
            "resolucion": "RES. N° 0101-2023-TCP-S1",
            "motivo": "Presentar información inexacta",
        }
    )
    valid = demo_ruc(9999)
    invalid = valid[:-1] + str((int(valid[-1]) + 1) % 10)  # dígito verificador alterado
    rows.append(
        {
            "ruc": invalid,
            "nombre": "REGISTRO CON RUC INVÁLIDO (PRUEBA DE CALIDAD)",
            "tipo": "INHABILITACIÓN TEMPORAL",
            "inicio": date(2024, 1, 10),
            "fin": date(2024, 6, 10),
            "resolucion": "RES. N° 0202-2024-TCP-S2",
            "motivo": "Registro de prueba",
        }
    )
    return rows


def write_sanctions_excel(rows: list[dict[str, Any]], path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sanciones"
    sheet["A1"] = "REGISTRO DE PROVEEDORES SANCIONADOS - DATOS SINTÉTICOS DE DEMOSTRACIÓN"
    sheet["A1"].font = Font(bold=True, size=12)
    sheet["A2"] = (
        "Archivo ficticio generado por contrataciones.sample_data. No usar para conclusiones."
    )
    headers = [
        "RUC",
        "NOMBRE O RAZÓN SOCIAL",
        "TIPO DE SANCIÓN",
        "FECHA INICIO",
        "FECHA FIN",
        "NÚMERO DE RESOLUCIÓN",
        "INFRACCIÓN",
    ]
    sheet.append([])
    sheet.append(headers)
    for cell in sheet[4]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(
            [
                row["ruc"],
                row["nombre"],
                row["tipo"],
                row["inicio"].strftime("%d/%m/%Y"),
                row["fin"].strftime("%d/%m/%Y") if row["fin"] else "",
                row["resolucion"],
                row["motivo"],
            ]
        )
    for column, width in zip("ABCDEFG", [14, 42, 28, 14, 14, 30, 40], strict=True):
        sheet.column_dimensions[column].width = width
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def write_exchange_rates(rates: dict[date, float], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fecha", "moneda", "tipo_cambio", "fuente"])
        for day in sorted(rates):
            writer.writerow([day.isoformat(), "USD", f"{rates[day]:.4f}", "SINTETICO_DEMO"])
    return path


def generate_sample_data(
    output_dir: str | Path,
    n_processes: int = 1200,
    seed: int = 2026,
    start: date = date(2024, 1, 2),
    end: date = date(2025, 12, 15),
) -> dict[str, Path]:
    """Genera los tres archivos de demostración en ``output_dir``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    rates = build_exchange_rates(rng, start - timedelta(days=31), end + timedelta(days=90))
    catalogs = build_catalogs(rng)
    releases = [
        generate_release(rng, seq, catalogs, start, end, rates) for seq in range(1, n_processes + 1)
    ]

    ocds_path = output_dir / "ocds_sample.jsonl"
    with ocds_path.open("w", encoding="utf-8") as handle:
        for release in releases:
            handle.write(json.dumps(release, ensure_ascii=False) + "\n")

    sanctions_path = write_sanctions_excel(
        generate_sanctions(rng, catalogs, releases), output_dir / "sanciones_sample.xlsx"
    )
    rates_path = write_exchange_rates(rates, output_dir / "tipo_cambio_sample.csv")
    logger.info("Datos sintéticos generados en %s (%d procesos)", output_dir, n_processes)
    return {"ocds": ocds_path, "sanciones": sanctions_path, "tipo_cambio": rates_path}
