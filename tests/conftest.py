"""Fixtures compartidas por las pruebas."""

from __future__ import annotations

import copy
import shutil
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
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


# =============================================================================
# Fase 2 (machine learning): capa gold mínima con señal plantada
# =============================================================================
GOLD_METHODS = [
    (1, "Licitación Pública", "open", True, False),
    (2, "Adjudicación Simplificada", "open", True, False),
    (3, "Subasta Inversa Electrónica", "open", True, False),
    (4, "Convenio", "direct", False, True),
]
GOLD_CATEGORIES = [(1, "goods", "Bienes"), (2, "services", "Servicios"), (3, "works", "Obras")]
GOLD_ENTITIES = [
    "MUNICIPALIDAD DISTRITAL DE PRUEBA",
    "GOBIERNO REGIONAL DE PRUEBA",
    "HOSPITAL REGIONAL DE PRUEBA",
    "MINISTERIO DE PRUEBA",
    "UNIVERSIDAD NACIONAL DE PRUEBA",
    "EMPRESA DE AGUA DE PRUEBA S.A.",
]
# Efectos plantados sobre log(adjudicado / referencial) cuando signal=True.
METHOD_EFFECT = {1: -0.12, 2: -0.06, 3: -0.25, 4: 0.0}
CATEGORY_EFFECT = {1: 0.0, 2: -0.04, 3: 0.03}
ENTITY_EFFECT = {"HOSPITAL": -0.15, "EMPRESA": 0.06}


def make_gold_tables(
    n: int = 1500,
    *,
    signal: bool = True,
    anomalies: bool = False,
    seed: int = 7,
    start: str = "2023-01-01",
    days: int = 730,
) -> dict[str, pd.DataFrame]:
    """Capa gold mínima con la forma de ``data/curated`` para probar el modelo de ML.

    * ``signal=True``: log(adjudicado/referencial) depende del método, la categoría, el
      tipo de entidad y el tamaño del proceso, con ruido pequeño. La línea base B1
      (método x categoría) no capta ni la entidad ni el tamaño: un buen modelo la supera.
      Los convenios se adjudican exactamente al valor referencial.
    * ``signal=False``: ruido puro; ningún modelo debería superar a la mediana global.
    * ``anomalies=True``: planta 8 sobrecostos y 8 subcostos evidentes (x2.2 y x0.45).

    Siempre incluye 40 procesos sin adjudicación, 30 sin valor referencial, 5 errores de
    datos (razón 0.001), una adjudicación inválida posterior y ``n_postores``
    correlacionado con el objetivo (fuga que la guardia debe impedir).
    """
    rng = np.random.default_rng(seed)
    metodos = pd.DataFrame(
        GOLD_METHODS,
        columns=[
            "metodo_key",
            "metodo_detalle",
            "metodo_ocds",
            "es_competitivo",
            "es_contratacion_directa",
        ],
    )
    categorias = pd.DataFrame(
        GOLD_CATEGORIES, columns=["categoria_key", "categoria_ocds", "categoria"]
    )
    names = [f"{name} {i:02d}" for i, name in enumerate(GOLD_ENTITIES * 2, 1)]
    entidades = pd.DataFrame(
        {
            "entidad_key": range(1, len(names) + 1),
            "entidad_id": [f"20{900000000 + i}" for i in range(1, len(names) + 1)],
            "ruc": None,
            "nombre": names,
            "departamento": ["Lima", "Cusco", "Piura", "Junín"] * 3,
            "pais": "Perú",
        }
    )
    metodo = rng.integers(1, 5, n)
    categoria = rng.integers(1, 4, n)
    entidad = rng.integers(1, len(names) + 1, n)
    convocatoria = pd.Timestamp(start) + pd.to_timedelta(rng.integers(0, days, n), unit="D")
    adjudicacion = convocatoria + pd.to_timedelta(rng.integers(20, 75, n), unit="D")
    log_vr = rng.normal(12.0, 1.2, n)
    referencial = np.round(np.exp(log_vr), 2)
    if signal:
        entity_effect = np.array(
            [next((v for k, v in ENTITY_EFFECT.items() if k in names[e - 1]), 0.0) for e in entidad]
        )
        log_ratio = (
            pd.Series(metodo).map(METHOD_EFFECT).to_numpy()
            + pd.Series(categoria).map(CATEGORY_EFFECT).to_numpy()
            + entity_effect
            - 0.04 * (log_vr - 12.0)
            + rng.normal(0, 0.02, n)
        )
        log_ratio = np.where(metodo == 4, 0.0, log_ratio)
    else:
        log_ratio = rng.normal(-0.10, 0.08, n)

    order = rng.permutation(n)
    no_award, no_reference, data_error = order[:40], order[40:70], order[70:75]
    if anomalies:
        candidates = np.setdiff1d(np.flatnonzero(metodo != 4), order[:75])
        planted = rng.choice(candidates, 16, replace=False)
        log_ratio[planted[:8]] += 0.8
        log_ratio[planted[8:]] -= 0.8
    monto = np.round(referencial * np.exp(log_ratio), 2)
    monto[no_award] = np.nan
    referencial[no_reference] = np.nan
    monto[data_error] = np.round(referencial[data_error] * 0.001, 2)
    ratio = monto / referencial
    postores = np.clip(np.round(4 - 10 * log_ratio + rng.normal(0, 0.5, n)), 1, None)
    consultas = rng.integers(2, 11, n).astype("float64")
    consultas[rng.random(n) < 0.1] = np.nan

    fact_proceso = pd.DataFrame(
        {
            "proceso_key": np.arange(1, n + 1),
            "ocid": [f"ocds-test-{i:05d}" for i in range(1, n + 1)],
            "nomenclatura": [f"PROC-{i:05d}" for i in range(1, n + 1)],
            "descripcion": "ADQUISICIÓN DE PRUEBA",
            "entidad_key": entidad,
            "metodo_key": metodo,
            "categoria_key": categoria,
            "fecha_convocatoria_key": convocatoria.strftime("%Y%m%d").astype(int),
            "estado": "complete",
            "moneda": "PEN",
            "valor_referencial": referencial,
            "valor_referencial_pen": referencial,
            "n_postores": pd.array(postores, dtype="Int64"),
            "plazo_presentacion_dias": pd.array([pd.NA] * n, dtype="Int64"),
            "plazo_consultas_dias": pd.array(consultas, dtype="Int64"),
            "n_adjudicaciones": (~np.isnan(monto)).astype(int),
            "monto_adjudicado_pen": monto,
            "ratio_adjudicado_referencial": np.round(ratio, 6),
            "n_alertas": 0,
            "puntaje_riesgo": 0,
            "nivel_riesgo": "Sin alertas",
            "nivel_riesgo_orden": 0,
        }
    )
    awarded = np.flatnonzero(~np.isnan(monto))
    fact_adjudicacion = pd.DataFrame(
        {
            "adjudicacion_key": np.arange(1, len(awarded) + 1),
            "proceso_key": awarded + 1,
            "ocid": fact_proceso["ocid"].to_numpy()[awarded],
            "award_id": [f"a{i}" for i in awarded],
            "fecha_adjudicacion_key": adjudicacion[awarded].strftime("%Y%m%d").astype(int),
            "es_valida": True,
            "monto_adjudicado_pen": monto[awarded],
        }
    )
    # Una adjudicación inválida posterior no debe cambiar la fecha de adjudicación.
    invalid = fact_adjudicacion.iloc[[0]].assign(
        adjudicacion_key=len(awarded) + 1,
        award_id="anulada",
        fecha_adjudicacion_key=20991231,
        es_valida=False,
    )
    return {
        "fact_proceso": fact_proceso,
        "dim_metodo": metodos,
        "dim_categoria": categorias,
        "dim_entidad": entidades,
        "fact_adjudicacion": pd.concat([fact_adjudicacion, invalid], ignore_index=True),
    }


def fast_model_config() -> dict[str, Any]:
    """``config/model_config.yaml`` con modelos más livianos para las pruebas."""
    config = copy.deepcopy(load_yaml(ROOT / "config" / "model_config.yaml"))
    config["models"]["hist_gradient_boosting"].update({"max_iter": 40, "learning_rate": 0.1})
    config["models"]["permutation_repeats"] = 2
    return config


def model_inputs(gold: dict[str, pd.DataFrame], config: dict[str, Any]) -> tuple:
    """Dataset de modelado, matriz de features y especificaciones."""
    from contrataciones.features.builder import build_features
    from contrataciones.features.catalog import load_feature_specs
    from contrataciones.features.dataset import build_modeling_table

    specs = load_feature_specs(config["features"])
    table = build_modeling_table(gold, config["population"])
    return table, build_features(table, specs, config["entity_types"]), specs


@pytest.fixture
def model_config() -> dict[str, Any]:
    return fast_model_config()


@pytest.fixture(scope="session")
def trained() -> SimpleNamespace:
    """Modelo entrenado una sola vez con señal plantada y anomalías (solo lectura)."""
    from contrataciones.models.trainer import train_model
    from contrataciones.models.workflow import build_artifact

    config = fast_model_config()
    gold = make_gold_tables(signal=True, anomalies=True)
    table, X, specs = model_inputs(gold, config)
    result = train_model(table, X, specs, config)
    artifact = build_artifact(
        version="monto_esperado_20260101_000000",
        config=config,
        specs=specs,
        table=table,
        result=result,
        data={"run_id": "prueba", "fuente": "prueba", "sinteticos": True},
        trained_at=datetime(2026, 1, 1),
    )
    return SimpleNamespace(
        config=config, gold=gold, table=table, X=X, specs=specs, result=result, artifact=artifact
    )
