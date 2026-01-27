import os
from datetime import date
from pathlib import Path
from io import BytesIO
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    from geoalchemy2 import Geometry
    _HAS_GEOALCHEMY = True
except ImportError:
    _HAS_GEOALCHEMY = False


load_dotenv()

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parents[1]

roi_path = os.getenv("ROI_PATH", str(PROJECT_ROOT / "data" / "processed" / "ROI.gpkg"))
roi_path = Path(roi_path)
if not roi_path.is_absolute():
    roi_path = (PROJECT_ROOT / roi_path).resolve()

roi = gpd.read_file(roi_path).to_crs(4326)
minx, miny, maxx, maxy = roi.total_bounds
bbox4326 = (float(minx), float(miny), float(maxx), float(maxy))
print("ROI path:", roi_path)
print("ROI bbox EPSG:4326:", bbox4326)

WFS_URL = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"

def get_typename_cadastralparcel():
    params = {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"}
    r = requests.get(WFS_URL, params=params, timeout=180)
    r.raise_for_status()

    root = ET.fromstring(r.content)

    # Namespaces típicos de WFS Capabilities
    ns = {
        "wfs": "http://www.opengis.net/wfs/2.0",
        "ows": "http://www.opengis.net/ows/1.1",
    }

    # Busca FeatureType/Name que contenga "CadastralParcel"
    for ft in root.findall(".//wfs:FeatureType", ns):
        name_el = ft.find("wfs:Name", ns)
        if name_el is not None and "CadastralParcel" in name_el.text:
            return name_el.text

    # Fallback conocido/documentado
    return "CP:CadastralParcel"

TYPENAME = get_typename_cadastralparcel()
print("Typename detectado:", TYPENAME)

# Elegir UTM ETRS89 por centroide del ROI (simple)
centroid = roi.geometry.union_all().centroid  # evita warning
lon = float(centroid.x)
if lon < -12.0:
    epsg_utm = 25828
elif lon < -6.0:
    epsg_utm = 25829
elif lon < 0.0:
    epsg_utm = 25830
else:
    epsg_utm = 25831
print("UTM ETRS89 EPSG elegido:", epsg_utm)

roi_utm = roi.to_crs(epsg_utm)
minx_m, miny_m, maxx_m, maxy_m = roi_utm.total_bounds

tile_m = int(os.getenv("CATASTRO_TILE_M", "1000"))
tiles = []
x = minx_m
while x < maxx_m:
    y = miny_m
    while y < maxy_m:
        tiles.append((x, y, min(x + tile_m, maxx_m), min(y + tile_m, maxy_m)))
        y += tile_m
    x += tile_m

print(f"Tiles generados: {len(tiles)}")

def get_feature_gml(bbox_m):
    # En documentación del catastro suelen usar SRSname=EPSG::25830 :contentReference[oaicite:1]{index=1}
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typenames": TYPENAME,
        "srsName": f"EPSG::{epsg_utm}",
        "bbox": f"{bbox_m[0]},{bbox_m[1]},{bbox_m[2]},{bbox_m[3]}",
        "outputFormat": "text/xml; subtype=gml/3.2.1",
    }
    r = requests.get(WFS_URL, params=params, timeout=180)
    r.raise_for_status()
    return r.content

gdfs = []
for i, t in enumerate(tiles, start=1):
    print(f"→ Tile {i}/{len(tiles)} bbox_utm={t}")
    try:
        content = get_feature_gml(t)
        # parsea GML con geopandas (Fiona/OGR)
        gdf_tile = gpd.read_file(BytesIO(content))
        if not gdf_tile.empty:
            gdfs.append(gdf_tile)
            print(f"   ✅ features={len(gdf_tile)}")
        else:
            print("   (vacío)")
    except Exception as e:
        print(f"   ⚠️ fallo tile: {e}")

if not gdfs:
    print("⚠️ No se descargó ninguna parcela. Revisa conectividad/servicio.")
    raise SystemExit(0)

parcelas = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True))
# Normaliza CRS
if parcelas.crs is None:
    parcelas = parcelas.set_crs(epsg_utm)
else:
    parcelas = parcelas.to_crs(epsg_utm)

# Campos mínimos “para pintar”
# intenta detectar la ref catastral (según schema INSPIRE suele llamarse nationalCadastralReference)
cols_lower = {c.lower(): c for c in parcelas.columns}
ref_col = cols_lower.get("nationalcadastralreference") or cols_lower.get("refcat")

parcelas["refcat"] = parcelas[ref_col] if ref_col else None

# inspire_id (si viene separado o directo)
if "inspireId" in parcelas.columns:
    parcelas["inspire_id"] = parcelas["inspireId"].astype(str)
else:
    parcelas["inspire_id"] = None

parcelas = parcelas.to_crs(4326)
parcelas_utm_area = parcelas.to_crs(epsg_utm)
parcelas["area_m2"] = parcelas_utm_area.geometry.area

# Dedupe si hay inspire_id
if parcelas["inspire_id"].notna().any():
    parcelas = parcelas.drop_duplicates(subset=["inspire_id"])

# Backup
out_dir = PROJECT_ROOT / "data" / "raw" / "catastro"
out_dir.mkdir(parents=True, exist_ok=True)
stamp = date.today().isoformat()
out_path = out_dir / f"{stamp}_parcelas_catastro.gpkg"
parcelas.to_file(out_path, driver="GPKG")
print(f"Backup guardado en: {out_path}")

# PostGIS
host = os.getenv("POSTGRES_HOST", "localhost")
port = os.getenv("POSTGRES_PORT", "5432")
db   = os.getenv("POSTGRES_DB")
user = os.getenv("POSTGRES_USER")
pwd  = os.getenv("POSTGRES_PASSWORD")
db_url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
engine = create_engine(db_url)

with engine.begin() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS catastro"))
    conn.execute(text("""
        DO $$
        BEGIN
            IF to_regclass('catastro.parcelas') IS NOT NULL THEN
                TRUNCATE TABLE catastro.parcelas;
            END IF;
        END
        $$;
    """))

parcelas_min = parcelas[["inspire_id", "refcat", "area_m2", "geometry"]].copy()

dtype = {"geometry": Geometry("MULTIPOLYGON", srid=4326)} if _HAS_GEOALCHEMY else None

parcelas_min.to_postgis(
    name="parcelas",
    con=engine,
    schema="catastro",
    if_exists="append",
    index=False,
    chunksize=2000,
    dtype=dtype,
)

print("Tabla catastro.parcelas actualizada.")
