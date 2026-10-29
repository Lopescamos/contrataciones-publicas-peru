"""Calidad de datos: reglas reutilizables, suite del dominio y perfilado.

Cada regla devuelve un :class:`CheckResult` con la cantidad y el porcentaje de
filas con problema. La regla falla cuando el porcentaje supera su umbral.

Dimensiones de calidad usadas (DAMA):
    Completitud, Unicidad, Validez, Consistencia, Integridad referencial.

Severidades:
    ERROR        el dato no es confiable para el análisis (p. ej. ocid duplicado).
    ADVERTENCIA  el análisis es posible, pero con sesgo o pérdida de cobertura.
    INFO         característica conocida de la fuente; se documenta y se maneja.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from contrataciones.processing.cleaner import valid_ruc_mask
from contrataciones.processing.currency import missing_rate_mask
from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

ERROR, WARNING, INFO = "ERROR", "ADVERTENCIA", "INFO"


@dataclass
class CheckResult:
    tabla: str
    regla: str
    dimension: str
    severidad: str
    columna: str | None
    filas_evaluadas: int
    filas_con_problema: int
    umbral_pct: float
    detalle: str = ""

    @property
    def pct_problema(self) -> float:
        if self.filas_evaluadas == 0:
            return 0.0
        return round(100.0 * self.filas_con_problema / self.filas_evaluadas, 4)

    @property
    def estado(self) -> str:
        return "FALLA" if self.pct_problema > self.umbral_pct else "OK"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pct_problema"] = self.pct_problema
        data["estado"] = self.estado
        return data


def check_mask(
    table: str,
    rule: str,
    problem_mask: pd.Series,
    *,
    dimension: str,
    severity: str = WARNING,
    column: str | None = None,
    max_pct: float = 0.0,
    detail: str = "",
    evaluated: int | None = None,
) -> CheckResult:
    """Regla genérica a partir de una máscara booleana de filas con problema."""
    mask = problem_mask.fillna(False).astype(bool)
    return CheckResult(
        tabla=table,
        regla=rule,
        dimension=dimension,
        severidad=severity,
        columna=column,
        filas_evaluadas=int(evaluated if evaluated is not None else len(mask)),
        filas_con_problema=int(mask.sum()),
        umbral_pct=float(max_pct),
        detalle=detail,
    )


def check_not_null(
    df: pd.DataFrame,
    table: str,
    column: str,
    *,
    max_pct: float = 0.0,
    severity: str = ERROR,
    detail: str = "",
) -> CheckResult:
    return check_mask(
        table,
        f"{column} no nulo",
        df[column].isna(),
        dimension="Completitud",
        severity=severity,
        column=column,
        max_pct=max_pct,
        detail=detail,
    )


def check_unique(
    df: pd.DataFrame, table: str, columns: list[str], *, severity: str = ERROR, detail: str = ""
) -> CheckResult:
    mask = df.duplicated(subset=columns, keep="first")
    return check_mask(
        table,
        f"{'+'.join(columns)} único",
        mask,
        dimension="Unicidad",
        severity=severity,
        column=",".join(columns),
        detail=detail,
    )


def check_range(
    df: pd.DataFrame,
    table: str,
    column: str,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    inclusive: bool = True,
    max_pct: float = 0.0,
    severity: str = WARNING,
    detail: str = "",
) -> CheckResult:
    values = pd.to_numeric(df[column], errors="coerce")
    mask = pd.Series(False, index=df.index)
    bounds = []
    if min_value is not None:
        mask |= values < min_value if inclusive else values <= min_value
        bounds.append(f"{'>=' if inclusive else '>'} {min_value:g}")
    if max_value is not None:
        mask |= values > max_value if inclusive else values >= max_value
        bounds.append(f"{'<=' if inclusive else '<'} {max_value:g}")
    rule = f"{column} {' y '.join(bounds)}"
    return check_mask(
        table,
        rule,
        mask & values.notna(),
        dimension="Validez",
        severity=severity,
        column=column,
        max_pct=max_pct,
        detail=detail,
        evaluated=int(values.notna().sum()),
    )


def check_allowed_values(
    df: pd.DataFrame,
    table: str,
    column: str,
    allowed: Iterable[Any],
    *,
    max_pct: float = 0.0,
    severity: str = WARNING,
    detail: str = "",
) -> CheckResult:
    allowed = list(allowed)
    present = df[column].notna()
    mask = present & ~df[column].isin(allowed)
    return check_mask(
        table,
        f"{column} en {allowed}",
        mask,
        dimension="Validez",
        severity=severity,
        column=column,
        max_pct=max_pct,
        detail=detail,
        evaluated=int(present.sum()),
    )


def check_valid_ruc(
    df: pd.DataFrame,
    table: str,
    column: str = "ruc",
    *,
    max_pct: float = 10.0,
    severity: str = WARNING,
    detail: str = "",
) -> CheckResult:
    present = df[column].notna()
    mask = present & ~valid_ruc_mask(df[column])
    return check_mask(
        table,
        f"{column} con dígito verificador válido",
        mask,
        dimension="Validez",
        severity=severity,
        column=column,
        max_pct=max_pct,
        detail=detail,
        evaluated=int(present.sum()),
    )


def check_referential(
    child: pd.DataFrame,
    child_col: str,
    parent: pd.DataFrame,
    parent_col: str,
    table: str,
    *,
    parent_name: str = "",
    max_pct: float = 0.0,
    severity: str = ERROR,
    detail: str = "",
) -> CheckResult:
    present = child[child_col].notna()
    mask = present & ~child[child_col].isin(set(parent[parent_col].dropna()))
    rule = f"{child_col} existe en {parent_name or 'tabla padre'}.{parent_col}"
    return check_mask(
        table,
        rule,
        mask,
        dimension="Integridad referencial",
        severity=severity,
        column=child_col,
        max_pct=max_pct,
        detail=detail,
        evaluated=int(present.sum()),
    )


def check_date_order(
    df: pd.DataFrame,
    table: str,
    start_col: str,
    end_col: str,
    *,
    max_pct: float = 1.0,
    severity: str = WARNING,
    detail: str = "",
) -> CheckResult:
    both = df[start_col].notna() & df[end_col].notna()
    mask = both & (df[end_col] < df[start_col])
    return check_mask(
        table,
        f"{end_col} >= {start_col}",
        mask,
        dimension="Consistencia",
        severity=severity,
        column=f"{start_col},{end_col}",
        max_pct=max_pct,
        detail=detail,
        evaluated=int(both.sum()),
    )


def info_count(
    table: str, rule: str, count: int, total: int, detail: str, dimension: str = "Consistencia"
) -> CheckResult:
    """Registra un hallazgo informativo (no falla nunca)."""
    return CheckResult(table, rule, dimension, INFO, None, int(total), int(count), 100.0, detail)


# =============================================================================
# Suite del dominio
# =============================================================================
def run_quality_suite(
    silver: dict[str, pd.DataFrame],
    cleaning_stats: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Ejecuta todas las reglas sobre la capa silver y devuelve el reporte."""
    stats = cleaning_stats or {}
    results: list[CheckResult] = []
    procesos = silver["procesos"]
    partes = silver["partes"]
    postores = silver["postores"]
    adjudicaciones = silver["adjudicaciones"]
    contratos = silver["contratos"]
    sanciones = silver.get("sanciones", pd.DataFrame())

    # --- procesos -----------------------------------------------------------
    results += [
        check_not_null(
            procesos, "procesos", "ocid", detail="Cada proceso debe tener su identificador OCDS."
        ),
        check_unique(procesos, "procesos", ["ocid"]),
        check_not_null(
            procesos,
            "procesos",
            "entidad_id_origen",
            max_pct=1.0,
            severity=WARNING,
            detail="Procesos sin entidad compradora identificada.",
        ),
        check_not_null(
            procesos,
            "procesos",
            "fecha_publicacion",
            max_pct=5.0,
            severity=WARNING,
            detail="Sin fecha no se puede ubicar el proceso en el tiempo.",
        ),
        check_not_null(
            procesos,
            "procesos",
            "valor_referencial",
            max_pct=20.0,
            severity=WARNING,
            detail="Valor referencial ausente o no positivo (se trata como desconocido).",
        ),
        check_date_order(
            procesos, "procesos", "fecha_inicio_presentacion", "fecha_fin_presentacion"
        ),
        check_allowed_values(
            procesos, "procesos", "moneda", ["PEN", "USD", "EUR"], max_pct=1.0, severity=INFO
        ),
        check_mask(
            "procesos",
            "metodo_detalle informado",
            procesos["metodo_detalle"].eq("No especificado"),
            dimension="Completitud",
            severity=WARNING,
            column="metodo_detalle",
            max_pct=5.0,
            detail="Sin método no se puede evaluar la competencia.",
        ),
    ]
    if "valor_referencial_pen" in procesos:
        results.append(
            check_mask(
                "procesos",
                "valor referencial convertido a PEN",
                missing_rate_mask(procesos, "valor_referencial", "moneda", "valor_referencial_pen"),
                dimension="Completitud",
                severity=WARNING,
                column="valor_referencial_pen",
                max_pct=0.5,
                detail="Montos en moneda extranjera sin tipo de cambio disponible.",
            )
        )
    if "valor_no_positivo" in stats:
        results.append(
            info_count(
                "procesos",
                "valor referencial <= 0 tratado como nulo",
                stats["valor_no_positivo"],
                len(procesos),
                "Valores 0 o negativos en tender.value se consideran no informados.",
                dimension="Validez",
            )
        )
    if {"fecha_inicio_presentacion", "fecha_fin_presentacion"} <= set(procesos.columns):
        inicio = procesos["fecha_inicio_presentacion"]
        fin = procesos["fecha_fin_presentacion"]
        with_dates = inicio.notna() & fin.notna()
        results.append(
            info_count(
                "procesos",
                "plazo de presentación no informado (inicio = fin)",
                int((with_dates & fin.eq(inicio)).sum()),
                int(with_dates.sum()),
                "tenderPeriod con inicio = fin (solo fecha de convocatoria): el plazo queda "
                "nulo y RF02 no lo evalúa (ver opción RF02.period en config/risk_rules.yaml).",
                dimension="Completitud",
            )
        )

    # --- partes ---------------------------------------------------------------
    compradores = partes[partes["es_comprador"]]
    results.append(check_valid_ruc(compradores, "partes (compradores)", max_pct=10.0))
    results.append(
        check_not_null(
            compradores,
            "partes (compradores)",
            "departamento",
            max_pct=10.0,
            severity=WARNING,
            detail="Sin departamento no se puede mapear el gasto.",
        )
    )

    # --- postores -------------------------------------------------------------
    results.append(check_valid_ruc(postores, "postores", max_pct=10.0))
    if "postores_duplicados" in stats:
        results.append(
            info_count(
                "postores",
                "postores duplicados eliminados",
                stats["postores_duplicados"],
                len(postores) + stats["postores_duplicados"],
                "Problema conocido de la fuente: postores con identificadores duplicados.",
                dimension="Unicidad",
            )
        )

    # --- adjudicaciones ---------------------------------------------------------
    results += [
        check_referential(
            adjudicaciones, "ocid", procesos, "ocid", "adjudicaciones", parent_name="procesos"
        ),
        check_range(
            adjudicaciones,
            "adjudicaciones",
            "monto",
            min_value=0,
            inclusive=False,
            max_pct=1.0,
            severity=WARNING,
        ),
        check_valid_ruc(adjudicaciones, "adjudicaciones", max_pct=10.0),
        check_not_null(
            adjudicaciones,
            "adjudicaciones",
            "proveedor_id",
            max_pct=2.0,
            severity=WARNING,
            detail="Adjudicaciones sin proveedor identificado.",
        ),
    ]
    fechas = procesos.drop_duplicates("ocid").set_index("ocid")["fecha_publicacion"]
    # Se compara por día: la fuente publica muchas fechas de adjudicación sin hora (00:00).
    award_day = pd.to_datetime(adjudicaciones["fecha_adjudicacion"]).dt.normalize()
    published_day = pd.to_datetime(adjudicaciones["ocid"].map(fechas)).dt.normalize()
    both_dates = award_day.notna() & published_day.notna()
    results.append(
        check_mask(
            "adjudicaciones",
            "fecha_adjudicacion >= fecha_publicacion",
            both_dates & (award_day < published_day),
            dimension="Consistencia",
            severity=WARNING,
            column="fecha_adjudicacion",
            max_pct=1.0,
            detail="Comparación por día calendario.",
            evaluated=int(both_dates.sum()),
        )
    )
    valid_awards = adjudicaciones[adjudicaciones["es_valida"]]
    award_keys = set(zip(valid_awards["ocid"], valid_awards["award_id"], strict=True))
    contract_keys = set(zip(contratos["ocid"], contratos["award_id"].fillna(""), strict=True))
    without_contract = sum(1 for key in award_keys if key not in contract_keys)
    results.append(
        info_count(
            "adjudicaciones",
            "adjudicaciones sin contrato vinculado",
            without_contract,
            len(award_keys),
            "Problema conocido de la fuente: awards sin contrato asociado.",
            dimension="Integridad referencial",
        )
    )

    # --- contratos ----------------------------------------------------------------
    results.append(
        info_count(
            "contratos",
            "contratos sin estado",
            int(contratos["estado"].eq("sin_estado").sum()),
            len(contratos),
            "Problema conocido de la fuente: contratos sin estado asignado.",
            dimension="Completitud",
        )
    )
    all_award_keys = set(zip(adjudicaciones["ocid"], adjudicaciones["award_id"], strict=True))
    unlinked = sum(
        1
        for key in zip(contratos["ocid"], contratos["award_id"], strict=True)
        if key not in all_award_keys
    )
    results.append(
        info_count(
            "contratos",
            "contratos sin adjudicación vinculada",
            unlinked,
            len(contratos),
            "Problema conocido de la fuente: contratos sin award asociado.",
            dimension="Integridad referencial",
        )
    )
    results.append(check_date_order(contratos, "contratos", "fecha_inicio", "fecha_fin"))

    # --- sanciones ---------------------------------------------------------------
    if not sanciones.empty:
        results += [
            check_valid_ruc(sanciones, "sanciones", max_pct=5.0),
            check_not_null(sanciones, "sanciones", "fecha_inicio", max_pct=1.0, severity=WARNING),
            check_date_order(sanciones, "sanciones", "fecha_inicio", "fecha_fin"),
        ]

    report = pd.DataFrame([r.to_dict() for r in results])
    order = [
        "tabla",
        "regla",
        "dimension",
        "severidad",
        "estado",
        "filas_evaluadas",
        "filas_con_problema",
        "pct_problema",
        "umbral_pct",
        "columna",
        "detalle",
    ]
    return report[order]


def summarize_quality(report: pd.DataFrame) -> dict[str, int]:
    """Conteo de reglas por estado y severidad."""
    failed = report[report["estado"] == "FALLA"]
    return {
        "reglas": len(report),
        "ok": int((report["estado"] == "OK").sum()),
        "fallas": len(failed),
        "fallas_error": int((failed["severidad"] == ERROR).sum()),
        "fallas_advertencia": int((failed["severidad"] == WARNING).sum()),
    }


def profile_dataframe(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Perfil por columna: tipo, nulos, valores únicos y un ejemplo."""
    rows = []
    for column in df.columns:
        series = df[column]
        non_null = series.dropna()
        try:
            unique = int(non_null.nunique())
        except TypeError:
            unique = -1
        rows.append(
            {
                "tabla": table,
                "columna": column,
                "tipo": str(series.dtype),
                "filas": len(series),
                "nulos": int(series.isna().sum()),
                "pct_nulos": round(100 * series.isna().mean(), 2) if len(series) else 0.0,
                "valores_unicos": unique,
                "ejemplo": str(non_null.iloc[0])[:80] if not non_null.empty else None,
            }
        )
    return pd.DataFrame(rows)
