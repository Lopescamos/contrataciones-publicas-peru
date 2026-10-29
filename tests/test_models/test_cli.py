"""Prueba de punta a punta de ``contrataciones-ml`` sobre los datos sintéticos."""

import pandas as pd
import pytest
import yaml

from contrataciones.cli import main as pipeline_main
from contrataciones.ingestion.db_connector import DatabaseConnector
from contrataciones.models.cli import main as ml_main
from contrataciones.utils.config_loader import load_config


@pytest.fixture
def ml_project(tmp_project):
    """Proyecto temporal con la capa gold de la muestra (400 procesos) y modelos livianos."""
    path = tmp_project / "config" / "model_config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["models"]["hist_gradient_boosting"]["max_iter"] = 60
    config["models"]["permutation_repeats"] = 2
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert pipeline_main(["run", "--source", "sample", "--limit", "400", "--no-excel"]) == 0
    return tmp_project


def test_train_predict_and_list(ml_project, capsys):
    assert ml_main(["train"]) == 0
    output = capsys.readouterr().out
    assert "aceptado: no" in output  # en la muestra la razón es ruido: no hay qué aprender
    assert "datos SINTÉTICOS" in output
    assert len(list((ml_project / "models" / "trained").glob("*.joblib"))) == 1
    assert (ml_project / "models" / "metadata" / "model_catalog.yaml").is_file()
    assert (ml_project / "data" / "features" / "dataset_modelado.parquet").is_file()

    assert ml_main(["predict"]) == 0
    assert "Procesos evaluados" in capsys.readouterr().out
    predictions = pd.read_parquet(
        ml_project / "data" / "predictions" / "pred_monto_esperado.parquet"
    )
    assert (ml_project / "data" / "predictions" / "pred_monto_esperado.csv").is_file()
    assert (ml_project / "data" / "exports" / "reporte_montos_atipicos.xlsx").is_file()
    query = ml_project / "sql" / "queries_ml" / "01_atipicos_por_entidad.sql"
    with DatabaseConnector("local_sqlite", config=load_config("db_config")) as db:
        count = db.read_query("SELECT COUNT(*) AS n FROM pred_monto_esperado")["n"].item()
        assert count == len(predictions)
        assert isinstance(db.read_query("SELECT * FROM vw_montos_atipicos"), pd.DataFrame)
        assert len(db.read_sql_file(query, params={"minimo": 1})) > 0

    # El pipeline de analítica sigue funcionando con la tabla y la vista de ML en la base
    # (la tabla de predicciones no tiene llaves foráneas hacia la capa gold).
    assert pipeline_main(["run", "--source", "sample", "--limit", "400", "--no-excel"]) == 0
    assert pipeline_main(["setup-db", "--drop"]) == 0

    assert ml_main(["list"]) == 0
    assert "monto_esperado_" in capsys.readouterr().out


def test_predict_errors_exit_with_code_1(ml_project):
    assert ml_main(["predict", "--no-db"]) == 1  # todavía no hay modelos
    assert ml_main(["train"]) == 0
    assert ml_main(["predict", "--version", "monto_esperado_19990101_000000", "--no-db"]) == 1


def test_train_without_gold_fails_cleanly(tmp_project):
    assert ml_main(["train"]) == 1


def test_list_without_models(tmp_project, capsys):
    assert ml_main(["list"]) == 0
    assert "No hay modelos" in capsys.readouterr().out
