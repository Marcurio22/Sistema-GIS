"""
Cálculo de Kc a partir de NDVI y catálogo de cultivos.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

FORMULAS_KC = {
    "KC_HERBACEO_COBERTURA_RAPIDA": {
        "tipo": "kc_unico",
        "fuente": "Calera/AgriSat-Irrimaps",
    },
    "KC_ANUAL_SUELO_VISIBLE": {
        "tipo": "kc_unico",
        "fuente": "Calera/AgriSat-Irrimaps",
    },
    "KCB_GENERAL": {
        "tipo": "kcb_basal",
        "fuente": "Calera/AgriSat-Irrimaps + FAO56 dual",
    },
    "KC_FIJO_BAJO": {
        "tipo": "kc_unico",
        "fuente": "criterio operativo suelo/barbecho",
    },
}

DEFAULT_FORMULA = "KCB_GENERAL"
DEFAULT_KC_MIN = 0.15
DEFAULT_KC_MAX = 1.00

CULTIVOS_KC_CSV = Path(__file__).resolve().parent / "cultivos_kc.csv"


def norm_cultivo(nombre: str) -> str:
    s = str(nombre or "").strip().upper()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def eval_formula(formula_code: str, ndvi: float) -> float:
    code = (formula_code or "").strip().upper()
    if code == "KC_HERBACEO_COBERTURA_RAPIDA":
        return 1.25 * ndvi + 0.10
    if code == "KC_ANUAL_SUELO_VISIBLE":
        return 0.85 * ndvi + 0.47
    if code == "KCB_GENERAL":
        return 1.44 * ndvi - 0.10
    if code == "KC_FIJO_BAJO":
        return 0.10
    return 1.0


def clamp_kc(kc: float, kc_min: float, kc_max: float) -> float:
    return max(float(kc_min), min(float(kc_max), float(kc)))


def calc_kc(
    ndvi: float | None,
    formula_code: str,
    kc_min: float,
    kc_max: float,
) -> tuple[float, float | None]:
    """
    Devuelve (kc_clamped, ndvi_usado).
    Si no hay NDVI válido, usa el punto medio del rango operativo.
    """
    if ndvi is not None and _is_finite(ndvi):
        ndvi_used = float(ndvi)
        kc_raw = eval_formula(formula_code, ndvi_used)
        return clamp_kc(kc_raw, kc_min, kc_max), ndvi_used

    kc_fallback = (float(kc_min) + float(kc_max)) / 2.0
    return kc_fallback, None


def _is_finite(v) -> bool:
    try:
        f = float(v)
        return f == f  # NaN check
    except (TypeError, ValueError):
        return False


def load_kc_catalog(path: Path | None = None) -> dict[str, dict]:
    csv_path = path or CULTIVOS_KC_CSV
    df = pd.read_csv(csv_path)
    catalog: dict[str, dict] = {}
    for _, row in df.iterrows():
        key = norm_cultivo(row["cultivo"])
        catalog[key] = {
            "cultivo": str(row["cultivo"]).strip(),
            "grupo": str(row.get("grupo", "") or "").strip(),
            "formula_code": str(row["formula_code"]).strip().upper(),
            "kc_min": float(row["kc_min"]),
            "kc_max": float(row["kc_max"]),
            "confianza": str(row.get("confianza", "") or "").strip(),
        }
    return catalog


def lookup_cultivo(catalog: dict[str, dict], cultivo_nombre: str) -> dict:
    key = norm_cultivo(cultivo_nombre)
    if key in catalog:
        return catalog[key]
    return {
        "cultivo": cultivo_nombre,
        "grupo": "",
        "formula_code": DEFAULT_FORMULA,
        "kc_min": DEFAULT_KC_MIN,
        "kc_max": DEFAULT_KC_MAX,
        "confianza": "baja",
    }
