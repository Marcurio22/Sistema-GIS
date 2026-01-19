#!/usr/bin/env python3
import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import geopandas as gpd
from shapely.geometry import box, mapping, shape

from PIL import Image

import math
import rasterio
from rasterio.warp import (
    reproject, Resampling, transform_bounds, transform_geom, calculate_default_transform
)
from rasterio.transform import from_bounds
from rasterio.windows import from_bounds as window_from_bounds
from rasterio.features import geometry_mask

from pystac_client import Client
import planetary_computer as pc

from sqlalchemy import text
from webapp import create_app, db

print("[NDVI] RUNNING FILE:", __file__)

# -----------------------------
# Config (por entorno)
# -----------------------------
ROI_PATH = os.getenv(
    "ROI_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg"),
)

DAYS_BACK = int(os.getenv("S2_DAYS_BACK", "10"))
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "60"))
MAX_ITEMS_TOTAL = int(os.getenv("S2_MAX_ITEMS_TOTAL", "10"))
PER_TILE = int(os.getenv("S2_MAX_ITEMS_PER_TILE", "5"))
FETCH_LIMIT = int(os.getenv("S2_FETCH_LIMIT", "200"))

# Resolución objetivo en metros/píxel (Sentinel-2 B04/B08 = 10 m)
NDVI_RES_M = float(os.getenv("NDVI_RES_M", "10"))

NDVI_COMPOSITE = os.getenv("NDVI_COMPOSITE", "max").lower()  # max | median
MIN_VALID_FRAC = float(os.getenv("NDVI_MIN_VALID_FRAC", "0.02"))

# Salvaguarda por si la bbox es enorme: limita dimensión máxima
NDVI_MAX_DIM = int(os.getenv("NDVI_MAX_DIM", "12000"))

DEBUG_STAC = os.getenv("DEBUG_STAC", "0") == "1"
DEBUG_S2 = os.getenv("DEBUG_S2", "0") == "1"

S2_COLLECTION = os.getenv("S2_STAC_COLLECTION", "sentinel-2-l2a")
STAC_URL = os.getenv("STAC_URL", "https://planetarycomputer.microsoft.com/api/stac/v1")

# SCL inválidos (nubes/sombras/nieve/nodata, etc.)
INVALID_SCL = {0, 1, 3, 7, 8, 9, 10, 11}

# Batch insert BBDD (común)
DB_BATCH_SIZE = int(os.getenv("NDVI_DB_BATCH_SIZE", "500"))
DB_PROGRESS_EVERY = int(os.getenv("NDVI_DB_PROGRESS_EVERY", "500"))


# -----------------------------
# Utilidades
# -----------------------------
def safe_replace(src_tmp: str, dst: str, retries: int = 6, sleep_s: float = 0.5) -> bool:
    """
    En Windows, si el destino está abierto (visor/QGIS/servidor), os.replace puede fallar.
    Reintentamos. Si no se puede, devolvemos False.
    """
    for _ in range(retries):
        try:
            os.replace(src_tmp, dst)
            return True
        except PermissionError:
            time.sleep(sleep_s)
    return False


def _href_readable(href: str) -> str:
    if href.startswith("s3://"):
        return "/vsis3/" + href[len("s3://"):]
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
    dst_crs = "EPSG:25830"
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
    """Lee el CRS real del asset (normalmente UTM por tile) abriendo el raster."""
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
    """
    minx, miny, maxx, maxy = bbox4326
    b = transform_bounds("EPSG:4326", dst_crs, minx, miny, maxx, maxy, densify_pts=21)
    minx_p, miny_p, maxx_p, maxy_p = b

    span_x = maxx_p - minx_p
    span_y = maxy_p - miny_p
    if span_x <= 0 or span_y <= 0:
        raise ValueError("BBox proyectada inválida (span <= 0)")

    width = int(math.ceil(span_x / res_m))
    height = int(math.ceil(span_y / res_m))

    if max_dim is not None:
        scale = max(width / max_dim, height / max_dim, 1.0)
        width = int(math.ceil(width / scale))
        height = int(math.ceil(height / scale))

    dst_transform = from_bounds(minx_p, miny_p, maxx_p, maxy_p, width, height)
    return width, height, dst_transform, (minx_p, miny_p, maxx_p, maxy_p)


def compute_ndvi(red, nir):
    den = nir + red
    return np.where(den == 0, np.nan, (nir - red) / den)


def ndvi_to_rgba(ndvi):
    """RGBA con alpha=0 en nodata."""
    h, w = ndvi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid = np.isfinite(ndvi)
    if not np.any(valid):
        return rgba

    v = np.clip(ndvi, -0.2, 1.0)
    t = (v + 0.2) / 1.2  # Normalizar a 0..1

    # Colores basados en tu tabla
    stops = [
        (0.00, (0, 0, 0)),        # NDVI < -0.2: Negro #000000
        (0.167, (165, 0, 38)),    # NDVI ≤ 0: Rojo oscuro #a50026
        (0.333, (215, 48, 39)),   # NDVI ≤ .1: Rojo #d73027
        (0.417, (244, 109, 67)),  # NDVI ≤ .2: Naranja-rojo #f46d43
        (0.500, (253, 174, 97)),  # NDVI ≤ .3: Naranja #fdae61
        (0.583, (254, 224, 139)), # NDVI ≤ .4: Amarillo #fee08b
        (0.667, (255, 255, 191)), # NDVI ≤ .5: Amarillo claro #ffffbf
        (0.750, (217, 239, 139)), # NDVI ≤ .6: Verde-amarillo #d9ef8b
        (0.833, (166, 217, 106)), # NDVI ≤ .7: Verde claro #a6d96a
        (0.917, (102, 189, 99)),  # NDVI ≤ .8: Verde medio #66bd63
        (0.958, (26, 152, 80)),   # NDVI ≤ .9: Verde oscuro #1a9850
        (1.00, (0, 104, 55)),     # NDVI ≤ 1.0: Verde muy oscuro #006837
    ]

    rgb = np.zeros((h, w, 3), dtype=np.float32)
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        
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
    return (item.properties or {}).get("s2:mgrs_tile") or "UNKNOWN"


def search_items(catalog, bbox, geom_geojson, start_dt, end_dt):
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
    items = [it for it in items if _cloud(it) <= CLOUD_MAX]
    items.sort(key=lambda it: (_cloud(it), -(it.datetime or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp()))

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
# main
# -----------------------------
def main():
    app = create_app()
    with app.app_context():
        minx, miny, maxx, maxy = get_roi_bbox_from_gpkg()

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

        items = [pc.sign(item) for item in items]

        # rejilla destino 10 m reales
        dst_crs = get_item_asset_crs(items[0], asset_key="B04")
        width, height, dst_transform, dst_bounds_proj = compute_grid_from_bbox_meters(
            bbox4326=(minx, miny, maxx, maxy),
            dst_crs=dst_crs,
            res_m=NDVI_RES_M,
            max_dim=NDVI_MAX_DIM,
        )

        if DEBUG_S2:
            minx_p, miny_p, maxx_p, maxy_p = dst_bounds_proj
            print(f"[NDVI] dst_crs: {dst_crs}")
            print(f"[NDVI] grid: {width}x{height} | res_m={NDVI_RES_M}")
            print(f"[NDVI] bounds_proj: {(minx_p, miny_p, maxx_p, maxy_p)}")
            print(f"[NDVI] GRID FINAL: {width} x {height} = {width*height:,} px")

        ndvi_stack = []
        used_ids = []
        used_dates = []
        skipped = 0

        for it in items:
            a = it.assets
            if "B04" not in a or "B08" not in a:
                skipped += 1
                continue

            # Leer bandas
            red = reproject_to_grid(a["B04"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
            nir = reproject_to_grid(a["B08"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)

            # Convertir a float32
            red = red.astype(np.float32)
            nir = nir.astype(np.float32)
            
            # CORRECCIÓN: Filtrar valores inválidos ANTES de convertir a reflectancia
            # Sentinel-2 L2A usa valores 0-10000 para reflectancia
            red[(red < 0) | (red > 10000)] = np.nan
            nir[(nir < 0) | (nir > 10000)] = np.nan
            
            # CORRECCIÓN: Convertir a reflectancia (0-1)
            red = red / 10000.0
            nir = nir / 10000.0

            # Aplicar máscara SCL (nubes, sombras, etc.)
            if "SCL" in a:
                scl = reproject_to_grid(a["SCL"].href, dst_transform, dst_crs, width, height, Resampling.nearest)
                scl_i = np.nan_to_num(scl, nan=0).astype(np.int32)
                bad = np.isin(scl_i, list(INVALID_SCL))
                red[bad] = np.nan
                nir[bad] = np.nan

            # Calcular NDVI
            ndvi = compute_ndvi(red, nir)
            valid_frac = float(np.isfinite(ndvi).sum()) / float(ndvi.size)

            if valid_frac < MIN_VALID_FRAC:
                if DEBUG_S2:
                    print(f"[NDVI] Skip {it.id}: valid_frac={valid_frac:.4f} < {MIN_VALID_FRAC}")
                skipped += 1
                continue

            # DIAGNÓSTICO: Imprimir estadísticas para verificar
            if DEBUG_S2:
                valid_ndvi = ndvi[np.isfinite(ndvi)]
                if len(valid_ndvi) > 0:
                    print(f"[NDVI] {it.id}: min={valid_ndvi.min():.3f}, "
                          f"max={valid_ndvi.max():.3f}, "
                          f"mean={valid_ndvi.mean():.3f}, "
                          f"median={np.median(valid_ndvi):.3f}")

            ndvi_stack.append(ndvi)
            used_ids.append(it.id)
            
            # Guardar fecha
            item_date = it.datetime
            if item_date:
                used_dates.append(item_date.isoformat())
            else:
                used_dates.append("unknown")

        if not ndvi_stack:
            print("No se pudo calcular NDVI (sin datos válidos).")
            return 0

        stack = np.stack(ndvi_stack, axis=0)
        if NDVI_COMPOSITE == "median":
            comp = np.nanmedian(stack, axis=0)
        else:
            # WARNING posible si algún pixel es todo NaN a través del stack (normal)
            comp = np.nanmax(stack, axis=0)

        if not np.any(np.isfinite(comp)):
            print("Composite NDVI vacío (todo nubes/NaN).")
            return 0

        print(f"[NDVI] Escenas usadas ({len(used_ids)}): {used_ids}")
        print(f"[NDVI] Fechas de imágenes: {used_dates}")
        print(f"[NDVI] Escenas saltadas: {skipped}")

        # DIAGNÓSTICO FINAL
        valid_comp = comp[np.isfinite(comp)]
        if len(valid_comp) > 0:
            print(f"\n[DIAGNÓSTICO FINAL COMPOSITE]")
            print(f"  NDVI min: {valid_comp.min():.3f}")
            print(f"  NDVI max: {valid_comp.max():.3f}")
            print(f"  NDVI mean: {valid_comp.mean():.3f}")
            print(f"  NDVI p25: {np.percentile(valid_comp, 25):.3f}")
            print(f"  NDVI p50: {np.percentile(valid_comp, 50):.3f}")
            print(f"  NDVI p75: {np.percentile(valid_comp, 75):.3f}")
            
            # Histograma de valores
            bins = [-1, -0.2, 0, 0.2, 0.4, 0.6, 0.8, 1.0]
            hist, _ = np.histogram(valid_comp, bins=bins)
            print(f"  Distribución por rangos:")
            for i in range(len(bins)-1):
                pct = 100 * hist[i] / len(valid_comp)
                print(f"    {bins[i]:+.1f} a {bins[i+1]:+.1f}: {pct:5.1f}%")
            print()

        # -----------------------------
        # Guardar GeoTIFF UTM + reproyectado 3857 + PNG 3857
        # -----------------------------
        static_ndvi_dir = Path(app.root_path) / "static" / "ndvi"
        static_ndvi_dir.mkdir(parents=True, exist_ok=True)

        ts = now.strftime("%Y%m%d_%H%M%S")
        tif_path_utm = static_ndvi_dir / f"ndvi2_{ts}_utm.tif"
        tif_path_3857 = static_ndvi_dir / f"ndvi2_{ts}_3857.tif"
        png_path_3857 = static_ndvi_dir / f"ndvi2_{ts}_3857.png"

        latest_tif_utm = static_ndvi_dir / "ndvi2_latest_utm.tif"
        latest_tif_3857 = static_ndvi_dir / "ndvi2_latest_3857.tif"
        latest_png_3857 = static_ndvi_dir / "ndvi2_latest_3857.png"
        meta_json = static_ndvi_dir / "ndvi2_latest.json"

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

        with rasterio.open(str(tif_path_utm), "w", **profile) as dst:
            dst.write(comp.astype(np.float32), 1)
        print(f"OK: NDVI2 GeoTIFF UTM -> {tif_path_utm}")

        warp_tif_to_3857(str(tif_path_utm), str(tif_path_3857))
        print(f"OK: NDVI2 GeoTIFF 3857 -> {tif_path_3857}")

        with rasterio.open(str(tif_path_3857)) as ds3857:
            comp3857 = ds3857.read(1).astype(np.float32)

        rgba_3857 = ndvi_to_rgba(comp3857)
        Image.fromarray(rgba_3857, mode="RGBA").save(str(png_path_3857), format="PNG", optimize=True)
        print(f"OK: NDVI2 PNG 3857 -> {png_path_3857}")

        ok_tif_utm = safe_replace(str(tif_path_utm), str(latest_tif_utm))
        ok_tif_3857 = safe_replace(str(tif_path_3857), str(latest_tif_3857))
        ok_png_3857 = safe_replace(str(png_path_3857), str(latest_png_3857))

        if not ok_tif_utm:
            print("WARNING: no pude reemplazar ndvi2_latest_utm.tif (bloqueado).")
        if not ok_tif_3857:
            print("WARNING: no pude reemplazar ndvi2_latest_3857.tif (bloqueado).")
        if not ok_png_3857:
            print("WARNING: no pude reemplazar ndvi2_latest_3857.png (bloqueado).")

        # bounds leaflet reales desde el raster 3857 (convertidos a 4326)
        tif_3857_to_read = latest_tif_3857 if ok_tif_3857 else tif_path_3857
        with rasterio.open(str(tif_3857_to_read)) as ds:
            b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
            minx2, miny2, maxx2, maxy2 = map(float, b)

        # Calcular rango de fechas de las imágenes usadas
        image_dates = []
        for date_str in used_dates:
            if date_str != "unknown":
                try:
                    image_dates.append(datetime.fromisoformat(date_str.replace('Z', '+00:00')))
                except:
                    pass
        
        date_range_str = ""
        if image_dates:
            min_date = min(image_dates)
            max_date = max(image_dates)
            if min_date.date() == max_date.date():
                date_range_str = min_date.strftime("%Y-%m-%d")
            else:
                date_range_str = f"{min_date.strftime('%Y-%m-%d')} a {max_date.strftime('%Y-%m-%d')}"

        meta = {
            "updated_utc": now.isoformat(),
            "window": [start_dt.isoformat(), end_dt.isoformat()],
            "collection": S2_COLLECTION,
            "composite": NDVI_COMPOSITE,
            "items_used": used_ids,
            "image_dates": used_dates,
            "date_range": date_range_str,
            "used": len(used_ids),
            "skipped": skipped,
            "bbox": [minx2, miny2, maxx2, maxy2],  # lon/lat
            "bounds_leaflet": [[miny2, minx2], [maxy2, maxx2]],  # lat/lon
            "size": [int(comp.shape[1]), int(comp.shape[0])],
            "cloud_max": CLOUD_MAX,
            "per_tile": PER_TILE,
            "min_valid_frac": MIN_VALID_FRAC,
            "latest_png": latest_png_3857.name,
            "latest_tif_utm": latest_tif_utm.name,
            "latest_tif_3857": latest_tif_3857.name,
        }
        meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK: NDVI2 meta.json -> {meta_json}")
        
        if date_range_str:
            print(f"[INFO] Fechas de imágenes: {date_range_str}")

        print("[INFO] Archivos NDVI2 generados. NO se guarda en base de datos.")
        
        return 0


if __name__ == "__main__":
    raise SystemExit(main())