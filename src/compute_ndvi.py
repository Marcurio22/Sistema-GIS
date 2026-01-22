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

DAYS_BACK = int(os.getenv("S2_DAYS_BACK", "12"))
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
    """Reproyecta el raster a EPSG:3857 (Web Mercator) para visualización web"""
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
# BBDD: recintos y stats
# -----------------------------
def fetch_recintos_geojson():
    sql = text("""
        SELECT id_recinto, ST_AsGeoJSON(geom) AS geojson, ST_SRID(geom) AS srid
        FROM public.recintos
        WHERE geom IS NOT NULL
    """)
    rows = db.session.execute(sql).fetchall()
    return [(int(r.id_recinto), r.geojson, int(r.srid) if r.srid else 4326) for r in rows]


def zonal_stats_for_geom_fast(dataset, geom):
    # bounds en CRS del dataset
    minx, miny, maxx, maxy = geom.bounds

    # ventana mínima del raster que cubre el recinto
    win = window_from_bounds(minx, miny, maxx, maxy, transform=dataset.transform)

    # ajustar offsets/lengths
    win = win.round_offsets().round_lengths()
    if win.width <= 0 or win.height <= 0:
        return None

    # lee solo la ventana
    arr = dataset.read(1, window=win).astype(np.float32)
    if not np.any(np.isfinite(arr)):
        return None

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
            
            # Filtrar valores inválidos ANTES de convertir a reflectancia
            red[(red < 0) | (red > 10000)] = np.nan
            nir[(nir < 0) | (nir > 10000)] = np.nan
            
            # Convertir a reflectancia (0-1)
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

            # DIAGNÓSTICO
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
        # CALCULAR FECHA DEL NDVI (imagen más reciente)
        # -----------------------------
        image_dates_dt = []
        for date_str in used_dates:
            if date_str != "unknown":
                try:
                    image_dates_dt.append(datetime.fromisoformat(date_str.replace('Z', '+00:00')))
                except:
                    pass

        if image_dates_dt:
            ndvi_date = max(image_dates_dt)  # fecha de la imagen más reciente
            min_date = min(image_dates_dt)
            max_date = ndvi_date
            if min_date.date() == max_date.date():
                date_range_str = min_date.strftime("%Y-%m-%d")
            else:
                date_range_str = f"{min_date.strftime('%Y-%m-%d')} a {max_date.strftime('%Y-%m-%d')}"
            fecha_ndvi_str = ndvi_date.strftime("%Y%m%d")
        else:
            # fallback si no hay fechas válidas
            ndvi_date = now
            date_range_str = now.strftime("%Y-%m-%d")
            fecha_ndvi_str = now.strftime("%Y%m%d")

        print(f"[INFO] Fecha NDVI (de imágenes): {fecha_ndvi_str}")
        print(f"[INFO] Rango de fechas: {date_range_str}")

        # -----------------------------
        # Guardar archivos con timestamp de la imagen
        # -----------------------------
        static_ndvi_dir = Path(app.root_path) / "static" / "ndvi"
        static_ndvi_dir.mkdir(parents=True, exist_ok=True)

        # Archivos con fecha de las imágenes (NO se reemplazan)
        tif_path_utm = static_ndvi_dir / f"ndvi2_{fecha_ndvi_str}_utm.tif"
        tif_path_3857 = static_ndvi_dir / f"ndvi2_{fecha_ndvi_str}_3857.tif"
        png_path = static_ndvi_dir / f"ndvi2_{fecha_ndvi_str}.png"
        meta_json = static_ndvi_dir / f"ndvi2_{fecha_ndvi_str}.json"

        # Archivos "latest" (enlaces simbólicos o copias)
        latest_tif_utm = static_ndvi_dir / "ndvi2_latest_utm.tif"
        latest_tif_3857 = static_ndvi_dir / "ndvi2_latest_3857.tif"
        latest_png = static_ndvi_dir / "ndvi2_latest.png"
        latest_meta_json = static_ndvi_dir / "ndvi2_latest.json"

        # Guardar GeoTIFF UTM
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
        print(f"✓ NDVI2 GeoTIFF UTM -> {tif_path_utm}")

        # Reproyectar a 3857 para compatibilidad web
        warp_tif_to_3857(str(tif_path_utm), str(tif_path_3857))
        print(f"✓ NDVI2 GeoTIFF 3857 -> {tif_path_3857}")

        # MEJORADO: Generar PNG desde el raster UTM ORIGINAL (mejor calidad visual)
        # No usar el reproyectado porque puede verse distorsionado
        rgba = ndvi_to_rgba(comp)
        Image.fromarray(rgba, mode="RGBA").save(str(png_path), format="PNG", optimize=True)
        print(f"✓ NDVI2 PNG -> {png_path}")

        # Obtener bounds en 4326 del raster 3857 (para leaflet)
        with rasterio.open(str(tif_path_3857)) as ds:
            b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
            minx2, miny2, maxx2, maxy2 = map(float, b)

        # Crear metadata
        meta = {
            "generated_utc": now.isoformat(),
            "ndvi_date": ndvi_date.isoformat(),
            "ndvi_date_formatted": fecha_ndvi_str,
            "date_range": date_range_str,
            "search_window": [start_dt.isoformat(), end_dt.isoformat()],
            "collection": S2_COLLECTION,
            "composite_method": NDVI_COMPOSITE,
            "items_used": used_ids,
            "image_dates": used_dates,
            "items_count": len(used_ids),
            "items_skipped": skipped,
            "bbox_4326": [minx2, miny2, maxx2, maxy2],
            "bounds_leaflet": [[miny2, minx2], [maxy2, maxx2]],
            "grid_size": [int(comp.shape[1]), int(comp.shape[0])],
            "resolution_m": float(NDVI_RES_M),
            "crs_epsg": int(dst_crs.to_epsg() or 0),
            "cloud_max": CLOUD_MAX,
            "per_tile": PER_TILE,
            "min_valid_frac": MIN_VALID_FRAC,
            "files": {
                "utm_tif": tif_path_utm.name,
                "epsg3857_tif": tif_path_3857.name,
                "png": png_path.name,
                "metadata": meta_json.name
            }
        }

        # Guardar JSON timestamped
        meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ NDVI2 metadata -> {meta_json}")

        # Crear enlaces "latest" (copiar archivos)
        import shutil
        try:
            shutil.copy2(str(tif_path_utm), str(latest_tif_utm))
            shutil.copy2(str(tif_path_3857), str(latest_tif_3857))
            shutil.copy2(str(png_path), str(latest_png))
            shutil.copy2(str(meta_json), str(latest_meta_json))
            print(f"✓ Archivos 'latest' actualizados")
        except Exception as e:
            print(f"⚠ Error copiando archivos latest: {e}")

        # -----------------------------
        # BBDD: Guardar en indices_raster
        # -----------------------------
        print("\n" + "="*60)
        print("GUARDANDO EN BASE DE DATOS")
        print("="*60)

        try:
            # 1) Insert en public.imagenes con ruta TIMESTAMPED
            sql_img = text("""
                INSERT INTO public.imagenes
                  (origen, fecha_adquisicion, epsg, sensor, resolucion_m, bbox, ruta_archivo)
                VALUES
                  (:origen, :fecha, :epsg, :sensor, :res, ST_MakeEnvelope(:minx,:miny,:maxx,:maxy,4326), :ruta)
                RETURNING id_imagen
            """)
            
            # CAMBIO IMPORTANTE: usar ruta con timestamp, NO latest
            ruta_rel = str(Path("static") / "ndvi" / tif_path_utm.name)
            
            id_imagen = db.session.execute(sql_img, {
                "origen": "satelite",
                "fecha": ndvi_date.date(),  # Fecha de las imágenes
                "epsg": int(dst_crs.to_epsg() or 0),
                "sensor": f"Sentinel-2 L2A NDVI2 | {NDVI_COMPOSITE} | {date_range_str}",
                "res": float(NDVI_RES_M),
                "minx": minx2, "miny": miny2, "maxx": maxx2, "maxy": maxy2,
                "ruta": ruta_rel,
            }).scalar()
            
            print(f"[BBDD] Imagen insertada: id={id_imagen}, fecha={fecha_ndvi_str}, ruta={ruta_rel}")
            
            # 2) UPSERT en indices_raster
            sql_idx = text("""
                INSERT INTO public.indices_raster
                  (id_imagen, id_recinto, tipo_indice, fecha_calculo, fecha_ndvi, epsg, resolucion_m,
                   valor_medio, valor_min, valor_max, desviacion_std, ruta_raster, ruta_ndvi)
                VALUES
                  (:id_imagen, :id_recinto, :tipo, :fecha_calc, :fecha_ndvi, :epsg, :res,
                   :mean, :min, :max, :std, :ruta_raster, :ruta_ndvi)
                ON CONFLICT (id_imagen, id_recinto, tipo_indice)
                DO UPDATE SET
                  fecha_calculo  = EXCLUDED.fecha_calculo,
                  fecha_ndvi     = EXCLUDED.fecha_ndvi,
                  epsg           = EXCLUDED.epsg,
                  resolucion_m   = EXCLUDED.resolucion_m,
                  valor_medio    = EXCLUDED.valor_medio,
                  valor_min      = EXCLUDED.valor_min,
                  valor_max      = EXCLUDED.valor_max,
                  desviacion_std = EXCLUDED.desviacion_std,
                  ruta_raster    = EXCLUDED.ruta_raster,
                  ruta_ndvi      = EXCLUDED.ruta_ndvi
            """)
            
            recintos = fetch_recintos_geojson()
            print(f"[BBDD] Recintos a procesar: {len(recintos)}")
            
            rows_to_insert = []
            processed = 0
            inserted = 0
            out_of_bounds = 0
            no_valid_pixels = 0
            errors = 0
            
            with rasterio.open(str(tif_path_utm)) as ds:
                ds_crs = ds.crs
                ds_bounds = ds.bounds
                
                for id_recinto, gj, srid in recintos:
                    processed += 1
                    
                    try:
                        geom_rec = shape(json.loads(gj))
                        geom_proj_gj = transform_geom(f"EPSG:{srid}", ds_crs, mapping(geom_rec), precision=6)
                        geom_proj = shape(geom_proj_gj)
                        
                        if not geom_proj.intersects(box(*ds_bounds)):
                            out_of_bounds += 1
                            continue
                        
                        stats = zonal_stats_for_geom_fast(ds, geom_proj)
                        if not stats:
                            no_valid_pixels += 1
                            continue
                        
                        # CAMBIO: ruta thumbnail con fecha NDVI en carpeta thumbnails/
                        ruta_thumbnail = f"static/thumbnails/{fecha_ndvi_str}_{id_recinto}.png"
                        
                        rows_to_insert.append({
                            "id_imagen": int(id_imagen),
                            "id_recinto": int(id_recinto),
                            "tipo": "NDVI",
                            "fecha_calc": now,
                            "fecha_ndvi": ndvi_date,
                            "epsg": int(dst_crs.to_epsg() or 0),
                            "res": float(NDVI_RES_M),
                            "mean": stats["mean"],
                            "min": stats["min"],
                            "max": stats["max"],
                            "std": stats["std"],
                            "ruta_raster": ruta_rel,
                            "ruta_ndvi": ruta_thumbnail,
                        })
                        inserted += 1
                        
                        if len(rows_to_insert) >= DB_BATCH_SIZE:
                            db.session.execute(sql_idx, rows_to_insert)
                            rows_to_insert.clear()
                        
                        if DEBUG_S2 and (processed % DB_PROGRESS_EVERY == 0):
                            print(f"[BBDD] Procesados={processed} | Insertados={inserted}")
                    
                    except Exception as e:
                        errors += 1
                        if DEBUG_S2:
                            print(f"[BBDD] Error en recinto {id_recinto}: {e}")
                        continue
            
            # Insertar los últimos
            if rows_to_insert:
                db.session.execute(sql_idx, rows_to_insert)
            
            db.session.commit()
            
            print(f"\n[BBDD] ===== RESUMEN FINAL =====")
            print(f"  Total recintos: {len(recintos)}")
            print(f"  Insertados: {inserted}")
            print(f"  Fuera de bounds: {out_of_bounds}")
            print(f"  Sin píxeles: {no_valid_pixels}")
            print(f"  Errores: {errors}")
            print(f"✓ NDVI2 guardado en BD (id={id_imagen}, fecha={fecha_ndvi_str})")

        except Exception as e:
            db.session.rollback()
            print(f"\n✗ ERROR guardando en BD: {repr(e)}")
            import traceback
            traceback.print_exc()
        
        return 0


if __name__ == "__main__":
    raise SystemExit(main())