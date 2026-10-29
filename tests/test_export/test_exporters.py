"""Pruebas de exportación a Parquet, CSV y Excel."""

import pandas as pd
from openpyxl import load_workbook

from contrataciones.export.csv_exporter import export_csv, export_tables
from contrataciones.export.excel_exporter import (
    ExcelStyle,
    export_multi_sheet,
    infer_number_format,
)


def test_export_tables_parquet_and_csv(tmp_path):
    tables = {"dim_a": pd.DataFrame({"x": [1, 2]}), "fact_b": pd.DataFrame({"monto": [1.5, None]})}
    written = export_tables(tables, parquet_dir=tmp_path / "pq", csv_dir=tmp_path / "csv")
    assert len(written["parquet"]) == 2 and len(written["csv"]) == 2
    assert pd.read_parquet(tmp_path / "pq" / "dim_a.parquet")["x"].tolist() == [1, 2]
    raw = (tmp_path / "csv" / "fact_b.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM para que Excel lea UTF-8


def test_export_csv_uses_iso_dates(tmp_path):
    frame = pd.DataFrame({"fecha": pd.to_datetime(["2025-03-07"]), "nombre": ["Áncash"]})
    path = export_csv(frame, tmp_path / "x.csv")
    assert "2025-03-07" in path.read_text(encoding="utf-8-sig")


def test_infer_number_format():
    assert infer_number_format("monto_adjudicado_pen") == "#,##0.00"
    assert infer_number_format("pct_postor_unico") == "0.0%"
    assert infer_number_format("n_procesos") == "#,##0"
    assert infer_number_format("anio") == "0"
    assert infer_number_format("fecha", pd.Series(pd.to_datetime(["2025-01-01"]))) == "dd/mm/yyyy"
    assert infer_number_format("nombre") is None


def test_export_multi_sheet_formatting(tmp_path):
    frame = pd.DataFrame(
        {
            "nombre": ["A", "B"],
            "monto_adjudicado_pen": [1234.5, 99.0],
            "n_procesos": pd.array([3, pd.NA], dtype="Int64"),
        }
    )
    path = export_multi_sheet(
        {"Datos": frame},
        tmp_path / "r.xlsx",
        style=ExcelStyle(),
        titles={"Datos": ("Título", "Subtítulo")},
    )
    sheet = load_workbook(path)["Datos"]
    assert sheet["A1"].value == "Título"
    assert sheet["A4"].value == "Nombre"  # encabezado legible
    assert sheet["B4"].value == "Monto adjudicado (S/)"
    assert sheet["B5"].number_format == "#,##0.00"
    assert sheet["A4"].font.bold
    assert sheet.freeze_panes == "A5"
    assert sheet.auto_filter.ref == "A4:C6"
