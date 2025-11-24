"""
descargar_sigpac.py

Descarga todos los recintos SIGPAC que intersectan tu ROI,
recorta exactamente a ROI, guarda backup rotatorio y vuelca a PostGIS.

Autor: Marcos Zamorano Lasso
Versión: 1.1.0
Fecha: 2025-11-21
"""

import os
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# (Opcional pero recomendable para geometrías MultiPolygon)
try:
    from geoalchemy2 import Geometry
    _HAS_GEOALCHEMY = True
except ImportError:
    _HAS_GEOALCHEMY = False


# -----------------------------
# 1) Cargar ROI y calcular bbox
# -----------------------------
roi_path = "../data/processed/roi.gpkg"  # usa gpkg/shp, NO .qgz
roi = gpd.read_file(roi_path).to_crs(4326)  # WGS84 / CRS84

minx, miny, maxx, maxy = roi.total_bounds
bbox = (float(minx), float(miny), float(maxx), float(maxy))
print("ROI bbox:", bbox)


# -------------------------------------------
# 2) Descargar TODOS los recintos por páginas
# -------------------------------------------
def descargar_todo_sigpac_recintos(bbox, limit=10000):
    """
    Descarga todos los recintos SIGPAC que intersectan el bbox paginando con offset.
    limit = tamaño de página (no total).
    """
    base_url = "https://sigpac-hubcloud.es/ogcapi/collections/recintos/items"
    offset = 0
    pages = []

    while True:
        url = (
            f"{base_url}?f=json"
            f"&bbox-crs=http://www.opengis.net/def/crs/OGC/1.3/CRS84"
            f"&bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            f"&limit={limit}&offset={offset}"
        )

        print(f"→ Descargando página offset={offset}")
        resp = requests.get(url, timeout=180)
        resp.raise_for_status()
        data = resp.json()

        feats = data.get("features", [])
        if not feats:
            break

        gdf_page = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
        pages.append(gdf_page)

        if len(feats) < limit:
            break

        offset += limit

    if not pages:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    gdf_all = gpd.GeoDataFrame(pd.concat(pages, ignore_index=True), crs="EPSG:4326")
    print(f"✅ Total recintos descargados en bbox: {len(gdf_all)}")
    return gdf_all


print("\nDescargando recintos del SIGPAC…")
gdf_recintos = descargar_todo_sigpac_recintos(bbox, limit=10000)


# ---------------------------------------------------
# 3) Recortar EXACTAMENTE a ROI (no solo bbox)
# ---------------------------------------------------
#print("\nRecortando a ROI exacta…")
#roi_union = roi.geometry.unary_union
#gdf_recintos = gdf_recintos.set_geometry("geometry")
#gdf_recintos = gpd.clip(gdf_recintos, roi_union)

# Limpieza básica de geometrías inválidas (por si acaso)
#gdf_recintos["geometry"] = gdf_recintos["geometry"].buffer(0)
#gdf_recintos = gdf_recintos[gdf_recintos.is_valid]

#print(f"✅ Total recintos tras clip a ROI: {len(gdf_recintos)}")
#print(gdf_recintos.head())


# ---------------------------------------------------
# 4) Guardar backup local ROTATORIO (solo 2 últimos)
# ---------------------------------------------------
out_dir = Path("data/raw/sigpac")
out_dir.mkdir(parents=True, exist_ok=True)

stamp = date.today().isoformat()
rec_path = out_dir / f"{stamp}_recintos.gpkg"

gdf_recintos.to_file(rec_path, driver="GPKG")
print(f"\nBackup guardado en: {rec_path}")

# Mantener solo los 2 últimos backups
files = sorted(out_dir.glob("*_recintos.gpkg"))
for f in files[:-2]:
    f.unlink(missing_ok=True)
    print(f"Backup antiguo eliminado: {f}")


# ---------------------------------------------------
# 5) Volcar a PostGIS en CHUNKS
# ---------------------------------------------------
print("\nEscribiendo en PostGIS…")
load_dotenv()

host = os.getenv("POSTGRES_HOST", "localhost")
port = os.getenv("POSTGRES_PORT", "5432")
db   = os.getenv("POSTGRES_DB")
user = os.getenv("POSTGRES_USER")
pwd  = os.getenv("POSTGRES_PASSWORD")

if not all([db, user, pwd]):
    raise RuntimeError("Faltan POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD en .env")

db_url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
engine = create_engine(db_url)

# Crear schema si no existe
with engine.begin() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS sigpac"))

# dtype robusto para MultiPolygon si tienes geoalchemy2
dtype = None
if _HAS_GEOALCHEMY:
    dtype = {"geometry": Geometry("MULTIPOLYGON", srid=4326)}

gdf_recintos.to_postgis(
    name="recintos",
    con=engine,
    schema="sigpac",
    if_exists="replace",
    index=False,
    chunksize=5000,      # no saturar RAM/DB
    dtype=dtype
)

print("✅ Tabla sigpac.recintos actualizada correctamente.")