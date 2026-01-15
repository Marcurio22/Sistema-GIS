#!/usr/bin/env python3
import os
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import geopandas as gpd
from shapely.geometry import box, mapping, shape

from PIL import Image

import math
import rasterio
from rasterio.warp import reproject, Resampling, transform_bounds, transform_geom, calculate_default_transform
from rasterio.transform import from_bounds
from rasterio.windows import from_bounds as window_from_bounds
from rasterio.mask import mask
from rasterio.features import geometry_mask

from pystac_client import Client
import planetary_computer as pc


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
    
from sqlalchemy import text
from webapp import create_app, db

print("[NDVI] RUNNING FILE:", __file__)

# =============================
# MODO TEST (SOLO ESTE ARCHIVO)
# =============================
TEST_BBOX_FRAC = 0.15      # 15% del ROI
TEST_BBOX_MODE = "center" # center | sw | se | nw | ne

# Directorio de salida de test
TEST_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "tests" / "ndvi_output"
TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------
# Config (por entorno)
# -----------------------------
ROI_PATH = os.getenv("ROI_PATH", str(Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg"))

DAYS_BACK = int(os.getenv("S2_DAYS_BACK", "180"))
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "60"))
MAX_ITEMS_TOTAL = int(os.getenv("S2_MAX_ITEMS_TOTAL", "30"))
PER_TILE = int(os.getenv("S2_MAX_ITEMS_PER_TILE", "5"))
FETCH_LIMIT = int(os.getenv("S2_FETCH_LIMIT", "200"))
# 10 píxeles, conservar metros con crs
# Resolución objetivo en metros/píxel (Sentinel-2 B04/B08 = 10 m)
NDVI_RES_M = float(os.getenv("NDVI_RES_M", "10"))
NDVI_COMPOSITE = os.getenv("NDVI_COMPOSITE", "max").lower()  # max | median
MIN_VALID_FRAC = float(os.getenv("NDVI_MIN_VALID_FRAC", "0.02"))

# Salvaguarda por si la bbox es enorme: limita dimensión máxima
NDVI_MAX_DIM = int(os.getenv("NDVI_MAX_DIM", "12000"))
# NDVI_MAX_DIM = os.getenv("NDVI_MAX_DIM")
# NDVI_MAX_DIM = int(NDVI_MAX_DIM) if NDVI_MAX_DIM else None

DEBUG_STAC = os.getenv("DEBUG_STAC", "0") == "1"
DEBUG_S2 = os.getenv("DEBUG_S2", "0") == "1"

S2_COLLECTION = os.getenv("S2_STAC_COLLECTION", "sentinel-2-l2a")
STAC_URL = os.getenv("STAC_URL", "https://planetarycomputer.microsoft.com/api/stac/v1")

# SCL inválidos (nubes/sombras/nieve/nodata, etc.)
INVALID_SCL = {0, 1, 3, 7, 8, 9, 10, 11}

# -----------------------------
# Utilidades
# -----------------------------

# -------- Modo test bbox ---------
def make_test_bbox(roi_bbox, frac=0.15, mode="center"):
    minx, miny, maxx, maxy = roi_bbox

    w = (maxx - minx) * frac
    h = (maxy - miny) * frac

    if mode == "center":
        cx = (minx + maxx) / 2
        cy = (miny + maxy) / 2
        return (cx - w/2, cy - h/2, cx + w/2, cy + h/2)

    if mode == "sw":
        return (minx, miny, minx + w, miny + h)
    if mode == "se":
        return (maxx - w, miny, maxx, miny + h)
    if mode == "nw":
        return (minx, maxy - h, minx + w, maxy)
    if mode == "ne":
        return (maxx - w, maxy - h, maxx, maxy)

    raise ValueError(f"Modo test bbox inválido: {mode}")

def safe_replace(src_tmp: str, dst: str, retries: int = 6, sleep_s: float = 0.5) -> bool:
    """
    En Windows, si el destino está abierto (visor/QGIS/servidor), os.replace puede fallar.
    Reintentamos. Si no se puede, devolvemos False (el tmp se queda ahí para renombrarlo luego).
    """
    for i in range(retries):
        try:
            os.replace(src_tmp, dst)
            return True
        except PermissionError:
            time.sleep(sleep_s)
    return False


def compute_output_shape(minx, miny, maxx, maxy, max_dim=2048, min_dim=512):
    lon_span = maxx - minx
    lat_span = maxy - miny
    if lon_span <= 0 or lat_span <= 0:
        return (min_dim, min_dim)

    ratio = lon_span / lat_span
    if ratio >= 1:
        w = max_dim
        h = int(max_dim / ratio)
    else:
        h = max_dim
        w = int(max_dim * ratio)

    w = max(min_dim, min(max_dim, w))
    h = max(min_dim, min(max_dim, h))
    return w, h


def _href_readable(href: str) -> str:
    if href.startswith("s3://"):
        return "/vsis3/" + href[len("s3://") :]
    return href


def reproject_to_grid(href, dst_transform, dst_crs, width, height, resampling, dtype=np.float32, nodata=np.nan):
    href = _href_readable(href)
    env_opts = dict(
        AWS_NO_SIGN_REQUEST="YES",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_MAX_RETRY="4",
        GDAL_HTTP_RETRY_DELAY="1",
    )
    with rasterio.Env(**env_opts):
        with rasterio.open(href) as src:
            dst = np.full((height, width), nodata, dtype=dtype)
            reproject(
                source=rasterio.band(src, 1),
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=resampling,
                dst_nodata=nodata,
            )
            return dst

def warp_tif_to_3857(src_tif: str, dst_tif: str):
    dst_crs = "EPSG:3857"
    with rasterio.open(src_tif) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )
        kwargs = src.meta.copy()
        kwargs.update({
            "crs": dst_crs,
            "transform": transform,
            "width": width,
            "height": height,
            "nodata": src.nodata,
        })

        with rasterio.open(dst_tif, "w", **kwargs) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                src_nodata=src.nodata,
                dst_nodata=src.nodata,
            )

        
def get_item_asset_crs(item, asset_key="B04"):
    """
    Lee el CRS real del asset (normalmente UTM por tile) abriendo el raster.
    """
    a = item.assets
    if asset_key not in a:
        raise ValueError(f"Item {item.id} no tiene asset {asset_key}")

    href = _href_readable(a[asset_key].href)
    env_opts = dict(
        AWS_NO_SIGN_REQUEST="YES",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_MAX_RETRY="4",
        GDAL_HTTP_RETRY_DELAY="1",
    )
    with rasterio.Env(**env_opts):
        with rasterio.open(href) as src:
            if src.crs is None:
                raise ValueError(f"Asset {asset_key} de {item.id} no tiene CRS")
            return src.crs


def compute_grid_from_bbox_meters(bbox4326, dst_crs, res_m, max_dim=None):
    """
    bbox4326: (minx, miny, maxx, maxy) en EPSG:4326
    dst_crs: CRS proyectado (UTM, etc.)
    res_m: tamaño de píxel en metros
    max_dim: (opcional) límite para evitar grids gigantes

    Devuelve: (width, height, dst_transform, dst_bounds_proj)
    """
    minx, miny, maxx, maxy = bbox4326

    # Pasamos bounds 4326 -> dst_crs (en metros). densify para más precisión.
    b = transform_bounds("EPSG:4326", dst_crs, minx, miny, maxx, maxy, densify_pts=21)
    minx_p, miny_p, maxx_p, maxy_p = b

    span_x = maxx_p - minx_p
    span_y = maxy_p - miny_p
    if span_x <= 0 or span_y <= 0:
        raise ValueError("BBox proyectada inválida (span <= 0)")

    width = int(math.ceil(span_x / res_m))
    height = int(math.ceil(span_y / res_m))

    if max_dim is not None:
        # Mantiene aspecto pero limita el tamaño si es enorme
        scale = max(width / max_dim, height / max_dim, 1.0)
        width = int(math.ceil(width / scale))
        height = int(math.ceil(height / scale))

    dst_transform = from_bounds(minx_p, miny_p, maxx_p, maxy_p, width, height)
    return width, height, dst_transform, (minx_p, miny_p, maxx_p, maxy_p)


def compute_ndvi(red, nir):
    den = nir + red
    return np.where(den == 0, np.nan, (nir - red) / den)


def ndvi_to_rgba(ndvi):
    """
    RGBA con alpha=0 en nodata.
    Colormap razonable (suelo/vegetación/agua).
    """
    h, w = ndvi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid = np.isfinite(ndvi)
    if not np.any(valid):
        return rgba

    v = np.clip(ndvi, -0.2, 0.9)
    t = (v + 0.2) / 1.1  # 0..1

    # marrón -> amarillo -> verde
    stops = [
        (0.00, (110,  70,  50)),
        (0.25, (185, 135,  70)),
        (0.45, (230, 210, 120)),
        (0.65, (150, 210, 140)),
        (0.85, ( 60, 170,  90)),
        (1.00, ( 20, 110,  60)),
    ]

    rgb = np.zeros((h, w, 3), dtype=np.float32)
    for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
        m = valid & (t >= t0) & (t <= t1)
        if not np.any(m):
            continue
        a = (t[m] - t0) / (t1 - t0 + 1e-12)
        c0 = np.array(c0, dtype=np.float32)
        c1 = np.array(c1, dtype=np.float32)
        rgb[m] = (1 - a)[:, None] * c0 + a[:, None] * c1

    rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return rgba

# -----------------------------
# ROI
# -----------------------------
def get_roi_bbox_from_gpkg():
    roi_path = Path(ROI_PATH)
    if not roi_path.exists():
        raise FileNotFoundError(f"ROI no existe: {roi_path.resolve()}")

    roi = gpd.read_file(roi_path).to_crs(4326)
    minx, miny, maxx, maxy = roi.total_bounds
    bbox = (float(minx), float(miny), float(maxx), float(maxy))
    print("ROI bbox:", bbox)
    return bbox


# -----------------------------
# STAC
# -----------------------------
def open_stac_catalog():
    cat = Client.open(STAC_URL)
    if DEBUG_STAC:
        cols = list(cat.get_collections())
        print(f"[STAC] Abierto PC: {STAC_URL} | colecciones: {len(cols)}")
        print("[STAC] Ejemplos:", [c.id for c in cols[:20]])
    return cat


def _cloud(item):
    return float((item.properties or {}).get("eo:cloud_cover", 999.0))


def _tile(item):
    # Planetary Computer usa s2:mgrs_tile
    return (item.properties or {}).get("s2:mgrs_tile") or "UNKNOWN"


def search_items(catalog, bbox, geom_geojson, start_dt, end_dt):
    # Preferimos intersects; fallback bbox
    try:
        search = catalog.search(
            collections=[S2_COLLECTION],
            intersects=geom_geojson,
            datetime=f"{start_dt.isoformat()}/{end_dt.isoformat()}",
            limit=FETCH_LIMIT,
        )
        items = list(search.items())
    except Exception:
        items = []

    if not items:
        search = catalog.search(
            collections=[S2_COLLECTION],
            bbox=list(bbox),
            datetime=f"{start_dt.isoformat()}/{end_dt.isoformat()}",
            limit=FETCH_LIMIT,
        )
        items = list(search.items())

    print(f"[NDVI] Items encontrados (sin filtrar): {len(items)}")
    if DEBUG_S2 and items:
        it0 = items[0]
        print(f"[NDVI] Colección usada: {S2_COLLECTION}")
        print("[NDVI] Ejemplo ID:", it0.id)
        print("[NDVI] Ejemplo datetime:", it0.datetime)
        print("[NDVI] Ejemplo cloud:", _cloud(it0))
        print("[NDVI] Ejemplo tile:", _tile(it0))
        print("[NDVI] Assets keys ejemplo:", list(it0.assets.keys())[:30])

    return items


def pick_items(items):
    # filtra por nubes y reparte por tile
    items = [it for it in items if _cloud(it) <= CLOUD_MAX]
    items.sort(key=lambda it: (_cloud(it), -(it.datetime or datetime(1970,1,1,tzinfo=timezone.utc)).timestamp()))

    per_tile = {}
    for it in items:
        t = _tile(it)
        per_tile.setdefault(t, [])
        if len(per_tile[t]) < PER_TILE:
            per_tile[t].append(it)

    picked = []
    for t in sorted(per_tile.keys()):
        picked.extend(per_tile[t])

    picked = picked[:MAX_ITEMS_TOTAL]

    print(f"[NDVI] Tiles en picked: {sorted(per_tile.keys())}")
    print(f"[NDVI] picked total: {len(picked)} (<= {MAX_ITEMS_TOTAL})")
    print(f"[NDVI] Items tras filtro nube<= {CLOUD_MAX}: {len(items)}")
    return picked

# -----------------------------
# BBDD: recintos y stats
# -----------------------------
def fetch_recintos_geojson(minx, miny, maxx, maxy):
    sql = text("""
        SELECT id_recinto, ST_AsGeoJSON(geom) AS geojson, ST_SRID(geom) AS srid
        FROM public.recintos
        WHERE geom IS NOT NULL
          AND geom && ST_MakeEnvelope(:minx,:miny,:maxx,:maxy,4326)
    """)
    rows = db.session.execute(sql, {
        "minx": minx, "miny": miny,
        "maxx": maxx, "maxy": maxy
    }).fetchall()

    return [(int(r.id_recinto), r.geojson, int(r.srid) if r.srid else 4326) for r in rows]

def zonal_stats_for_geom_fast(dataset, geom):
    # bounds en CRS del dataset
    minx, miny, maxx, maxy = geom.bounds

    # ventana mínima del raster que cubre el recinto
    win = window_from_bounds(minx, miny, maxx, maxy, transform=dataset.transform)

    # recorta a límites del raster
    win = win.round_offsets().round_lengths()
    if win.width <= 0 or win.height <= 0:
        return None

    # lee solo la ventana
    arr = dataset.read(1, window=win).astype(np.float32)

    # si todo es NaN, fuera
    if not np.any(np.isfinite(arr)):
        return None

    # máscara del polígono en la ventana
    win_transform = dataset.window_transform(win)
    m = geometry_mask(
        [mapping(geom)],
        transform=win_transform,
        out_shape=arr.shape,
        invert=True
    )

    vals = arr[m]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return None

    return {
        "mean": float(vals.mean()),
        "min": float(vals.min()),
        "max": float(vals.max()),
        "std": float(vals.std()),
    }


# -----------------------------
# main
# -----------------------------

print("======================================")
print("   EJECUTANDO update_ndvi_test.py")
print("======================================")

def main():
    app = create_app()
    with app.app_context():
        minx, miny, maxx, maxy = get_roi_bbox_from_gpkg()

        # =================================
        # TEST: bbox reducido SOLO para BBDD
        # =================================
        bbdd_bbox = make_test_bbox(
            (minx, miny, maxx, maxy),
            frac=TEST_BBOX_FRAC,
            mode=TEST_BBOX_MODE
        )

        print(f"[TEST] BBDD bbox reducido: {bbdd_bbox}")

        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(days=DAYS_BACK)
        end_dt = now

        print(f"[NDVI] Ventana: {start_dt.isoformat()} -> {end_dt.isoformat()}")
        print(f"[NDVI] Cloud max: {CLOUD_MAX} | max_items: {MAX_ITEMS_TOTAL} | per_tile: {PER_TILE} | fetch_limit: {FETCH_LIMIT}")

        bbox = (minx, miny, maxx, maxy)
        geom = mapping(box(minx, miny, maxx, maxy))

        catalog = open_stac_catalog()
        items_all = search_items(catalog, bbox, geom, start_dt, end_dt)
        items = pick_items(items_all)

        if not items:
            print("No hay escenas candidatas; no se actualiza.")
            return 0

        # Firma Planetary Computer (tokens SAS)
        items = [pc.sign(item) for item in items]

        # --- Rejilla destino correcta (10 m reales) ---
        # 1) Sacar CRS desde la imagen Sentinel (B04 del primer item usable)
        dst_crs = get_item_asset_crs(items[0], asset_key="B04")

        # 2) Construir rejilla a resolución fija en metros
        width, height, dst_transform, dst_bounds_proj = compute_grid_from_bbox_meters(
            bbox4326=(minx, miny, maxx, maxy),
            dst_crs=dst_crs,
            res_m=NDVI_RES_M,
            max_dim=NDVI_MAX_DIM,   # salvaguarda opcional
        )

        if DEBUG_S2:
            minx_p, miny_p, maxx_p, maxy_p = dst_bounds_proj
            print(f"[NDVI] dst_crs: {dst_crs}")
            print(f"[NDVI] grid: {width}x{height} | res_m={NDVI_RES_M}")
            print(f"[NDVI] bounds_proj: {(minx_p, miny_p, maxx_p, maxy_p)}")
            print(f"[NDVI] GRID FINAL: {width} x {height} = {width*height:,} px")


        ndvi_stack = []
        used_ids = []
        skipped = 0

        for it in items:
            a = it.assets
            # PC usa B04/B08/SCL en mayúsculas
            if "B04" not in a or "B08" not in a:
                skipped += 1
                continue

            red = reproject_to_grid(a["B04"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
            nir = reproject_to_grid(a["B08"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)

            red = red.astype(np.float32); nir = nir.astype(np.float32)
            red[red <= 0] = np.nan
            nir[nir <= 0] = np.nan

            if "SCL" in a:
                scl = reproject_to_grid(a["SCL"].href, dst_transform, dst_crs, width, height, Resampling.nearest)
                scl_i = np.nan_to_num(scl, nan=0).astype(np.int32)
                bad = np.isin(scl_i, list(INVALID_SCL))
                red[bad] = np.nan
                nir[bad] = np.nan

            ndvi = compute_ndvi(red, nir)
            valid_frac = float(np.isfinite(ndvi).sum()) / float(ndvi.size)

            if valid_frac < MIN_VALID_FRAC:
                if DEBUG_S2:
                    print(f"[NDVI] Skip {it.id}: valid_frac={valid_frac:.4f} < {MIN_VALID_FRAC}")
                skipped += 1
                continue

            ndvi_stack.append(ndvi)
            used_ids.append(it.id)

        if not ndvi_stack:
            print("No se pudo calcular NDVI (sin datos válidos).")
            return 0

        stack = np.stack(ndvi_stack, axis=0)
        if NDVI_COMPOSITE == "median":
            comp = np.nanmedian(stack, axis=0)
        else:
            comp = np.nanmax(stack, axis=0)

        if not np.any(np.isfinite(comp)):
            print("Composite NDVI vacío (todo nubes/NaN).")
            return 0
    
        print(f"[NDVI] Escenas usadas ({len(used_ids)}): {used_ids}")
        print(f"[NDVI] Escenas saltadas: {skipped}")

        # -----------------------------
        # Guardar GeoTIFF UTM + reproyectado 3857 + PNG 3857 + meta.json
        # -----------------------------
        static_ndvi_dir = TEST_OUTPUT_DIR
        static_ndvi_dir.mkdir(parents=True, exist_ok=True)

        ts = now.strftime("%Y%m%d_%H%M%S")

        tif_path_utm = static_ndvi_dir / f"ndvi_test_{ts}_utm.tif"
        tif_path_3857 = static_ndvi_dir / f"ndvi_test_{ts}_3857.tif"
        png_path_3857 = static_ndvi_dir / f"ndvi_test_{ts}_3857.png"

        latest_tif_utm = static_ndvi_dir / "ndvi_latest_test_utm.tif"
        latest_tif_3857 = static_ndvi_dir / "ndvi_latest_test_3857.tif"
        latest_png_3857 = static_ndvi_dir / "ndvi_latest_test_3857.png"
        meta_json = static_ndvi_dir / "ndvi_latest_test.json"


        # Preparar profile GeoTIFF
        profile = {
            "driver": "GTiff",
            "height": comp.shape[0],
            "width": comp.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": dst_crs,
            "transform": dst_transform,
            "nodata": np.nan,
            "compress": "deflate",
        }

        # 1) Guardar GeoTIFF UTM versionado
        with rasterio.open(str(tif_path_utm), "w", **profile) as dst:
            dst.write(comp.astype(np.float32), 1)
        print(f"OK: NDVI GeoTIFF UTM -> {tif_path_utm}")

        # 2) Warpear a EPSG:3857
        warp_tif_to_3857(str(tif_path_utm), str(tif_path_3857))
        print(f"OK: NDVI GeoTIFF 3857 -> {tif_path_3857}")

        # 3) PNG RGBA SIEMPRE desde el 3857
        with rasterio.open(str(tif_path_3857)) as ds3857:
            comp3857 = ds3857.read(1).astype(np.float32)

        rgba_3857 = ndvi_to_rgba(comp3857)
        Image.fromarray(rgba_3857, mode="RGBA").save(str(png_path_3857), format="PNG", optimize=True)
        print(f"OK: NDVI PNG 3857 -> {png_path_3857}")

        # 4) Actualizar latest
        ok_tif_utm  = safe_replace(str(tif_path_utm),  str(latest_tif_utm))
        ok_tif_3857 = safe_replace(str(tif_path_3857), str(latest_tif_3857))
        ok_png_3857 = safe_replace(str(png_path_3857), str(latest_png_3857))

        if not ok_tif_utm:
            print("WARNING: no pude reemplazar ndvi_latest_utm.tif (bloqueado).")
        if not ok_tif_3857:
            print("WARNING: no pude reemplazar ndvi_latest_3857.tif (bloqueado).")
        if not ok_png_3857:
            print("WARNING: no pude reemplazar ndvi_latest_3857.png (bloqueado).")

        # 5) Bounds Leaflet reales desde el raster 3857
        tif_3857_to_read = latest_tif_3857 if ok_tif_3857 else tif_path_3857
        with rasterio.open(str(tif_3857_to_read)) as ds:
            b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
            minx2, miny2, maxx2, maxy2 = map(float, b)

        # 6) meta.json (útil para debug/visor si lo lees)
        meta = {
            "updated_utc": now.isoformat(),
            "window": [start_dt.isoformat(), end_dt.isoformat()],
            "collection": S2_COLLECTION,
            "composite": NDVI_COMPOSITE,
            "items_used": used_ids,
            "used": len(used_ids),
            "skipped": skipped,

            # Bounds reales del NDVI 3857 pero expresados en 4326 para Leaflet
            "bbox": [minx2, miny2, maxx2, maxy2],  # lon/lat
            "bounds_leaflet": [[miny2, minx2], [maxy2, maxx2]],  # lat/lon

            "size": [int(comp.shape[1]), int(comp.shape[0])],  # (width,height) del UTM base
            "cloud_max": CLOUD_MAX,
            "per_tile": PER_TILE,
            "min_valid_frac": MIN_VALID_FRAC,

            "latest_png": latest_png_3857.name,
            "latest_tif_utm": latest_tif_utm.name,
            "latest_tif_3857": latest_tif_3857.name,
        }
        meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


        print(f"OK: NDVI meta.json -> {meta_json}")

        # -----------------------------
        # Debugs de BBDD
        # -----------------------------
        t_db0 = time.perf_counter()
        rminx, rminy, rmaxx, rmaxy = bbdd_bbox
        recintos = fetch_recintos_geojson(rminx, rminy, rmaxx, rmaxy)
        print(f"[BBDD] recintos a procesar: {len(recintos)} | t={time.perf_counter()-t_db0:.2f}s")

        t_loop0 = time.perf_counter()
    
        # -----------------------------
        # BBDD
        # -----------------------------
        try:
            # 1) Insert en public.imagenes (cumple CHECK: origen en {satelite,dron})
            sql_img = text("""
                INSERT INTO public.imagenes
                  (origen, fecha_adquisicion, epsg, sensor, resolucion_m, bbox, ruta_archivo)
                VALUES
                  (:origen, :fecha, :epsg, :sensor, :res, ST_MakeEnvelope(:minx,:miny,:maxx,:maxy,4326), :ruta)
                RETURNING id_imagen
            """)
            # guardamos ruta relativa (más portable)
            ruta_rel = str(Path("tests") / "ndvi_output" / latest_tif_utm.name)
            id_imagen = db.session.execute(sql_img, {
                "origen": "satelite",
                "fecha": now,
                "epsg": int(dst_crs.to_epsg() or 0),
                "sensor": f"TEST NDVI | Sentinel-2 L2A (Planetary Computer) | composite={NDVI_COMPOSITE}",
                "res": float(NDVI_RES_M),
                "minx": minx2, "miny": miny2, "maxx": maxx2, "maxy": maxy2,
                "ruta": ruta_rel,
            }).scalar()

            rminx, rminy, rmaxx, rmaxy = bbdd_bbox
            recintos = fetch_recintos_geojson(rminx, rminy, rmaxx, rmaxy)


            tif_to_open: Path = latest_tif_utm if ok_tif_utm else tif_path_utm

            with rasterio.open(str(tif_to_open)) as ds:
                inserted = 0
                ds_crs = ds.crs

                sql_idx = text("""
                    INSERT INTO public.indices_raster
                    (id_imagen, id_recinto, tipo_indice, fecha_calculo, epsg, resolucion_m,
                    valor_medio, valor_min, valor_max, desviacion_std, ruta_raster)
                    VALUES
                    (:id_imagen, :id_recinto, :tipo, :fecha, :epsg, :res,
                    :mean, :min, :max, :std, :ruta)
                    ON CONFLICT (id_imagen, id_recinto, tipo_indice)
                    DO UPDATE SET
                    fecha_calculo   = EXCLUDED.fecha_calculo,
                    epsg           = EXCLUDED.epsg,
                    resolucion_m    = EXCLUDED.resolucion_m,
                    valor_medio     = EXCLUDED.valor_medio,
                    valor_min       = EXCLUDED.valor_min,
                    valor_max       = EXCLUDED.valor_max,
                    desviacion_std  = EXCLUDED.desviacion_std,
                    ruta_raster     = EXCLUDED.ruta_raster
                """)

                rows_to_insert = []

                for id_recinto, gj, srid in recintos:
                    geom_rec = shape(json.loads(gj))

                    # reproyecta geom_rec desde su SRID real al CRS del raster NDVI
                    geom_rec_gj = mapping(geom_rec)
                    geom_proj_gj = transform_geom(f"EPSG:{srid}", ds_crs, geom_rec_gj, precision=6)
                    geom_proj = shape(geom_proj_gj)

                    stats = zonal_stats_for_geom_fast(ds, geom_proj)
                    if not stats:
                        continue

                    # Debug progreso    
                    if inserted % 50 == 0 and inserted > 0:
                        elapsed = time.perf_counter() - t_loop0
                        print(f"[BBDD] procesados {inserted} recintos | {elapsed:.1f}s | ~{(elapsed/inserted):.2f}s/recinto")
                    # ---------------------------------------------
                    # dentro del loop, cuando hay stats:
                    rows_to_insert.append({
                        "id_imagen": int(id_imagen),
                        "id_recinto": int(id_recinto),
                        "tipo": "NDVI",
                        "fecha": now,
                        "epsg": int(dst_crs.to_epsg() or 0),
                        "res": float(NDVI_RES_M),
                        "mean": stats["mean"],
                        "min": stats["min"],
                        "max": stats["max"],
                        "std": stats["std"],
                        "ruta": ruta_rel,
                    })

                    inserted += 1

                    if inserted % 500 == 0:
                        db.session.execute(sql_idx, rows_to_insert)
                        rows_to_insert.clear()

                if rows_to_insert:
                    db.session.execute(sql_idx, rows_to_insert)

            db.session.commit()
            print(f"OK: NDVI guardado en BBDD -> imagenes.id_imagen={id_imagen} | indices_raster insertados={inserted}")
        except Exception as e:
            db.session.rollback()
            print("WARNING: No se pudo guardar NDVI en BBDD. Los ficheros sí se han generado.")
            print("Detalle error:", repr(e))

        return 0


if __name__ == "__main__":
    raise SystemExit(main())