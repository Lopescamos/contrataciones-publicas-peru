# Atajos para Linux, macOS y Git Bash en Windows.
# En PowerShell usa directamente los comandos equivalentes (ver README.md).
PYTHON ?= python
YEAR ?= 2025

.PHONY: help install lint format test coverage sample run run-bulk download setup-db db-up db-down clean

help:  ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install:  ## Instala el proyecto con las dependencias de desarrollo y de ML
	$(PYTHON) -m pip install -e ".[dev,ml]"

lint:  ## Revisa estilo y errores con ruff
	ruff check src tests scripts
	ruff format --check src tests scripts

format:  ## Formatea el código
	ruff format src tests scripts
	ruff check --fix src tests scripts

test:  ## Ejecuta las pruebas
	$(PYTHON) -m pytest

coverage:  ## Pruebas con reporte de cobertura
	$(PYTHON) -m pytest --cov=contrataciones --cov-report=term-missing

sample:  ## Regenera los datos sintéticos de demostración
	contrataciones sample

run:  ## Pipeline completo con datos de demostración
	contrataciones run --source sample

download:  ## Descarga el archivo OCDS de un año (YEAR=2025)
	contrataciones download --year $(YEAR)

run-bulk:  ## Pipeline con datos reales descargados (YEAR=2025)
	contrataciones run --source bulk --year $(YEAR)

setup-db:  ## Crea tablas y vistas en la base configurada
	contrataciones setup-db

db-up:  ## Levanta PostgreSQL local con Docker
	docker compose up -d

db-down:  ## Detiene PostgreSQL local
	docker compose down

clean:  ## Borra datos generados (no toca data/sample ni data/raw)
	rm -rf data/processed/* data/curated/* data/exports/* data/db/*.db logs/*.log*
	rm -rf data/features/* data/predictions/*
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	touch data/processed/.gitkeep data/curated/.gitkeep data/exports/.gitkeep data/db/.gitkeep
	touch data/features/.gitkeep data/predictions/.gitkeep
