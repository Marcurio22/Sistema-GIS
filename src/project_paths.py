"""
Rutas portables relativas a la raíz del proyecto.
Usar en scripts batch / predicción en lugar de rutas absolutas por máquina.
"""
from __future__ import annotations

import os
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    cur = (start or Path(__file__).resolve()).resolve()
    if cur.is_file():
        cur = cur.parent
    for _ in range(15):
        if (cur / "src").is_dir() and ((cur / "data").is_dir() or (cur / "Prediccion").is_dir()):
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root(Path(__file__).resolve().parent)

PREDICCION_DIR = PROJECT_ROOT / "Prediccion"
PREDICCION_DLL_DIR = PREDICCION_DIR
MODELOS_PRED_DIR = PREDICCION_DIR / "modelosPred"
SALIDA_PRED_DIR = PREDICCION_DIR / "salidaPred"

# Salida intermedia ET / cultivos (sustituye C:\datos\salida)
DATOS_SALIDA_DIR = Path(os.getenv("GIS_DATOS_SALIDA", str(PROJECT_ROOT / "data" / "salida")))

NDVI_COMPOSITE_DIR = PROJECT_ROOT / "data" / "processed" / "ndvi_composite"
ETP_STATIC_DIR = PROJECT_ROOT / "src" / "webapp" / "static" / "etp_prediccion"
RIEGO_STATIC_DIR = PROJECT_ROOT / "src" / "webapp" / "static" / "riego_prediccion"

_DEFAULT_GEOSERVER_MAPAS = (
    r"C:\ProgramData\GeoServer\data\mapascontinuos"
    if os.name == "nt"
    else "/var/geoserver/data/mapascontinuos"
)
GEOSERVER_MAPAS_DIR = Path(os.getenv("GEOSERVER_MAPAS_CONTINUOS_DIR", _DEFAULT_GEOSERVER_MAPAS))


def ndvi_mosaic_mas_reciente() -> Path | None:
    """Último mosaico NDVI UTM en data/processed/ndvi_composite."""
    if not NDVI_COMPOSITE_DIR.is_dir():
        return None
    archivos = list(NDVI_COMPOSITE_DIR.glob("ndvi_pc_*_mosaic_utm.tif"))
    if not archivos:
        return None
    return max(archivos, key=lambda p: p.stat().st_mtime)
