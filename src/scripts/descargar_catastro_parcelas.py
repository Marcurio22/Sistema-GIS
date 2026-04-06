import os
import sys
from datetime import date
from pathlib import Path
from io import BytesIO
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
import geopandas as gpd
from shapely.geometry import MultiPolygon
from dotenv import load_dotenv
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from webapp import create_app, db   

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
    ns = {
        "wfs": "http://www.opengis.net/wfs/2.0",
        "ows": "http://www.opengis.net/ows/1.1",
    }
    for ft in root.findall(".//wfs:FeatureType", ns):
        name_el = ft.find("wfs:Name", ns)
        if name_el is not None and "CadastralParcel" in name_el.text:
            return name_el.text

    return "CP:CadastralParcel"


TYPENAME = get_typename_cadastralparcel()
print("Typename detectado:", TYPENAME)

try:
    centroid = roi.geometry.union_all().centroid
except AttributeError:
    centroid = roi.geometry.unary_union.centroid

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


def fetch_tile(args):
    i, t = args
    try:
        content = get_feature_gml(t)
        gdf_tile = gpd.read_file(BytesIO(content))
        if not gdf_tile.empty:
            print(f"   ✅ Tile {i}/{len(tiles)} features={len(gdf_tile)}")
            return gdf_tile
        print(f"   (vacío) Tile {i}/{len(tiles)}")
        return None
    except Exception as e:
        print(f"   ⚠️ fallo tile {i}/{len(tiles)}: {e}")
        return None

MAX_WORKERS = int(os.getenv("CATASTRO_WORKERS", "8"))
print(f"Descargando {len(tiles)} tiles con {MAX_WORKERS} workers en paralelo...")

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    results = list(executor.map(fetch_tile, enumerate(tiles, start=1)))
gdfs = [r for r in results if r is not None]

if not gdfs:
    print("⚠️ No se descargó ninguna parcela. Revisa conectividad/servicio.")
    raise SystemExit(0)

parcelas = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True))
parcelas = parcelas.set_crs(epsg_utm, allow_override=True)

mask = parcelas.geometry.geom_type == "Polygon"
parcelas.loc[mask, "geometry"] = parcelas.loc[mask, "geometry"].apply(MultiPolygon)
parcelas = parcelas.set_geometry("geometry")

cols_lower = {c.lower(): c for c in parcelas.columns}
ref_col = cols_lower.get("nationalcadastralreference") or cols_lower.get("refcat")
parcelas["refcat"] = parcelas[ref_col] if ref_col else None

if "inspireId" in parcelas.columns:
    parcelas["inspire_id"] = parcelas["inspireId"].apply(
        lambda x: x.get("localId") if isinstance(x, dict) else (str(x) if x else None)
    )
else:
    parcelas["inspire_id"] = None

parcelas["area_m2"] = parcelas.geometry.area

parcelas = parcelas.to_crs(4326)

before = len(parcelas)
if parcelas["refcat"].notna().any():
    parcelas = parcelas.drop_duplicates(subset=["refcat"], keep="first").reset_index(drop=True)
    print(f"Dedup por refcat: {before} → {len(parcelas)} parcelas")
elif parcelas["inspire_id"].notna().any():
    parcelas = parcelas.drop_duplicates(subset=["inspire_id"], keep="first").reset_index(drop=True)
    print(f"Dedup por inspire_id: {before} → {len(parcelas)} parcelas")
else:
    print("⚠️  Sin columna de clave única disponible, no se deduplica.")

print(f"Parcelas totales tras dedup: {len(parcelas)}")

out_dir = PROJECT_ROOT / "data" / "raw" / "catastro"
out_dir.mkdir(parents=True, exist_ok=True)
stamp = date.today().isoformat()
out_path = out_dir / f"{stamp}_parcelas_catastro.gpkg"
parcelas.to_file(out_path, driver="GPKG")
print(f"Backup guardado en: {out_path}")

app = create_app()   # ← igual que en el 2º script

with app.app_context():
    db.session.execute(text("CREATE SCHEMA IF NOT EXISTS catastro"))
    db.session.commit()

    parcelas_min = parcelas[["inspire_id", "refcat", "area_m2", "geometry"]].copy()
    parcelas_min.index.name = "id"

    dtype = {"geometry": Geometry("MULTIPOLYGON", srid=4326)} if _HAS_GEOALCHEMY else None

    parcelas_min.to_postgis(
        name="parcelas2",
        con=db.engine,            
        schema="catastro",
        if_exists="replace",
        index=True,
        chunksize=2000,
        dtype=dtype,
    )

    print("Tabla catastro.parcelas2 cargada.")