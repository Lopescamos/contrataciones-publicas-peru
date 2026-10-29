"""Pruebas de lectura de Excel/CSV y detección de formato."""

import gzip

import pandas as pd
import pytest
from openpyxl import Workbook

from contrataciones.ingestion.excel_loader import (
    SchemaError,
    apply_column_mapping,
    list_sheets,
    load_csv,
    load_excel,
    load_tabular,
    normalize_header,
    validate_columns,
)
from contrataciones.ingestion.file_detector import auto_load, detect_format

MAPPING = {
    "ruc": ["RUC", "NRO_RUC"],
    "nombre": ["RAZON_SOCIAL", "NOMBRE_O_RAZON_SOCIAL"],
    "fecha_inicio": ["FECHA_INICIO", "FECHA_DE_INICIO"],
}


def test_normalize_header():
    assert normalize_header("  Número de Resolución ") == "NUMERO_DE_RESOLUCION"
    assert normalize_header("Nº RUC") == "NO_RUC"
    assert normalize_header("Fecha-Inicio (dd/mm)") == "FECHA_INICIO_DD_MM"


@pytest.fixture
def excel_with_title(tmp_path):
    path = tmp_path / "sanciones.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Datos"
    sheet["A1"] = "REPORTE DE SANCIONES"
    sheet["A2"] = "Fuente: prueba"
    sheet.append([])
    sheet.append(["Nro. RUC", "Nombre o Razón Social", "Fecha de Inicio", "Otra"])
    sheet.append(["20131312955", "EMPRESA UNO", "01/02/2025", "x"])
    sheet.append(["20100047218", "EMPRESA DOS", "15/03/2025", "y"])
    workbook.save(path)
    return path


def test_load_excel_detects_header_row(excel_with_title):
    frame = load_excel(excel_with_title, header_row="auto", aliases=MAPPING)
    assert list(frame.columns)[:3] == ["Nro. RUC", "Nombre o Razón Social", "Fecha de Inicio"]
    assert len(frame) == 2
    assert frame.iloc[0, 0] == "20131312955"  # se lee como texto: no pierde ceros ni dígitos
    assert list_sheets(excel_with_title) == ["Datos"]


def test_apply_column_mapping_renames_and_orders(excel_with_title):
    frame = load_tabular(excel_with_title, header_row="auto", aliases=MAPPING)
    mapped = apply_column_mapping(frame, MAPPING, required=["ruc"])
    assert list(mapped.columns) == ["ruc", "nombre", "fecha_inicio"]
    assert mapped["nombre"].tolist() == ["EMPRESA UNO", "EMPRESA DOS"]


def test_apply_column_mapping_missing_required_raises():
    frame = pd.DataFrame({"OTRA": [1]})
    with pytest.raises(SchemaError, match="ruc"):
        apply_column_mapping(frame, MAPPING, required=["ruc"])


def test_apply_column_mapping_fills_optional_columns():
    frame = pd.DataFrame({"RUC": ["20131312955"]})
    mapped = apply_column_mapping(frame, MAPPING, required=["ruc"])
    assert mapped["nombre"].isna().all()


def test_load_csv_semicolon_latin1(tmp_path):
    path = tmp_path / "datos.csv"
    path.write_bytes("RUC;Razón Social\n20131312955;SUPERINTENDENCIA\n".encode("latin-1"))
    frame = load_csv(path)
    assert list(frame.columns) == ["RUC", "Razón Social"]
    assert frame.iloc[0, 0] == "20131312955"


def test_validate_columns():
    assert validate_columns(pd.DataFrame({"a": [1]}), ["a", "b"]) == ["b"]


def test_detect_format_and_auto_load(tmp_path, excel_with_title):
    csv_path = tmp_path / "x.csv"
    pd.DataFrame({"a": [1, 2]}).to_csv(csv_path, index=False)
    parquet_path = tmp_path / "x.parquet"
    pd.DataFrame({"a": [1, 2]}).to_parquet(parquet_path)
    jsonl_gz = tmp_path / "x.jsonl.gz"
    with gzip.open(jsonl_gz, "wt") as handle:
        handle.write('{"a": 1}\n{"a": 2}\n')
    assert detect_format(csv_path) == "csv"
    assert detect_format(parquet_path) == "parquet"
    assert detect_format(excel_with_title) == "xlsx"
    assert detect_format(jsonl_gz) == "jsonl"
    assert auto_load(parquet_path)["a"].tolist() == [1, 2]
    assert auto_load(jsonl_gz)["a"].tolist() == [1, 2]
    assert len(auto_load(csv_path)) == 2
