#!/usr/bin/env python3
import os
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import geopandas as gpd
from PIL import Image

import math
import rasterio
from rasterio.warp import reproject, transform_bounds, calculate_default_transform, Resampling
from rasterio.transform import from_bounds

from shapely.geometry import box, mapping

from pystac_client import Client
import planetary_computer as pc

from webapp import create_app


# -----------------------------
# Config (por entorno)
# -----------------------------
ROI_PATH = os.getenv("ROI_PATH", str(Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg"))

DAYS_BACK = int(os.getenv("S2_DAYS_BACK", "120"))
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "60"))
MAX_ITEMS_TOTAL = int(os.getenv("S2_MAX_ITEMS_TOTAL", "12"))
PER_TILE = int(os.getenv("S2_MAX_ITEMS_PER_TILE", "2"))
FETCH_LIMIT = int(os.getenv("S2_FETCH_LIMIT", "200"))

RGB_RES_M = float(os.getenv("S2_RGB_RES_M", "10"))         # 10 m/px reales
RGB_MAX_DIM = int(os.getenv("S2_RGB_MAX_DIM", "12000"))    # salvaguarda (sube si tu ROI es grande)
RGB_COMPOSITE = os.getenv("S2_RGB_COMPOSITE", "median").lower()  # median | max
RGB_GAMMA = float(os.getenv("S2_RGB_GAMMA", "1.15"))             # 1.0..1.4 típico
MIN_VALID_FRAC = float(os.getenv("S2_RGB_MIN_VALID_FRAC", "0.02"))

DEBUG_STAC = os.getenv("DEBUG_STAC", "0") == "1"
DEBUG_S2 = os.getenv("DEBUG_S2", "0") == "1"

S2_COLLECTION = os.getenv("S2_STAC_COLLECTION", "sentinel-2-l2a")
STAC_URL = os.getenv("STAC_URL", "https://planetarycomputer.microsoft.com/api/stac/v1")

# SCL inválidos (nubes/sombras/nieve/nodata, etc.)
# (Planetary Computer SCL sigue el estándar Sentinel-2)
INVALID_SCL = {0, 1, 3, 7, 8, 9, 10, 11}


# -----------------------------
# Utilidades
# -----------------------------
def safe_replace(src_tmp: str, dst: str, retries: int = 6, sleep_s: float = 0.5) -> bool:
    """Reintenta os.replace para evitar WinError 5 si el destino está abierto."""
    for _ in range(retries):
        try:
            os.replace(src_tmp, dst)
            return True
        except PermissionError:
            time.sleep(sleep_s)
    return False

def get_roi_bbox_from_gpkg():
    roi_path = Path(ROI_PATH)
    if not roi_path.exists():
        raise FileNotFoundError(f"No existe ROI.gpkg en: {roi_path.resolve()}")

    roi = gpd.read_file(roi_path).to_crs(4326)
    minx, miny, maxx, maxy = roi.total_bounds
    return float(minx), float(miny), float(maxx), float(maxy)


def open_stac_catalog():
    cat = Client.open(STAC_URL)
    if DEBUG_STAC:
        cols = list(cat.get_collections())
        print(f"[STAC] Abierto PC: {STAC_URL} | colecciones: {len(cols)}")
        print("[STAC] Ejemplos:", [c.id for c in cols[:20]])
    return cat

def get_item_asset_crs(item, asset_key="B04"):
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
    return width, height, dst_transform

def warp_rgb_tif_to_3857(src_tif: str, dst_tif: str):
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
            "count": 3,
            "dtype": src.dtypes[0],
            "nodata": src.nodata,
        })

        with rasterio.open(dst_tif, "w", **kwargs) as dst:
            for b in (1, 2, 3):
                reproject(
                    source=rasterio.band(src, b),
                    destination=rasterio.band(dst, b),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear,
                    src_nodata=src.nodata,
                    dst_nodata=src.nodata,
                )

def _cloud(item):
    return float((item.properties or {}).get("eo:cloud_cover", 999.0))


def _tile(item):
    return (item.properties or {}).get("s2:mgrs_tile") or "UNKNOWN"


def search_items(catalog, bbox, geom_geojson, start_dt, end_dt):
    # Preferimos intersects; si falla o viene vacío, fallback con bbox
    items = []
    try:
        search = catalog.search(
            collections=[S2_COLLECTION],
            intersects=geom_geojson,
            datetime=f"{start_dt.isoformat()}/{end_dt.isoformat()}",
            limit=FETCH_LIMIT,
        )
        items = list(search.items())
    except Exception as e:
        if DEBUG_STAC:
            print("[RGB] search(intersects) falló:", repr(e))
        items = []

    if not items:
        search = catalog.search(
            collections=[S2_COLLECTION],
            bbox=list(bbox),
            datetime=f"{start_dt.isoformat()}/{end_dt.isoformat()}",
            limit=FETCH_LIMIT,
        )
        items = list(search.items())

    print(f"[RGB] Colección usada: {S2_COLLECTION}")
    print(f"[RGB] Items encontrados (sin filtrar): {len(items)}")

    if items and DEBUG_S2:
        it0 = items[0]
        print("[RGB] Ejemplo ID:", it0.id)
        print("[RGB] Ejemplo datetime:", it0.datetime)
        print("[RGB] Ejemplo cloud:", _cloud(it0))
        print("[RGB] Ejemplo tile:", _tile(it0))
        print("[RGB] Assets keys ejemplo:", list(it0.assets.keys())[:35])

    return items


def pick_items(items):
    # filtra por nubes y reparte por tile
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

    print(f"[RGB] Tiles en picked: {sorted(per_tile.keys())}")
    print(f"[RGB] picked total: {len(picked)} (<= {MAX_ITEMS_TOTAL})")
    print(f"[RGB] Items tras filtro nube<= {CLOUD_MAX}: {len(items)}")
    return picked


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


def read_band_with_retries(asset_href, dst_transform, dst_crs, width, height, resampling, retries=3):
    last = None
    for i in range(retries):
        try:
            return reproject_to_grid(asset_href, dst_transform, dst_crs, width, height, resampling)
        except Exception as e:
            last = e
            if DEBUG_S2:
                print(f"[RGB] Reintento {i+1}/{retries} falló leyendo asset:", repr(e))
            time.sleep(0.5)
    raise last


def stretch_and_gamma(x, valid_mask, p_low=2.0, p_high=98.0, gamma=1.15):
    """
    x: float32 0..1 aprox (reflectancia)
    devuelve uint8 0..255
    """
    if not np.any(valid_mask):
        return np.zeros_like(x, dtype=np.uint8), (None, None)

    vals = x[valid_mask]
    if vals.size < 500:
        # fallback
        lo, hi = 0.02, 0.30
    else:
        lo = float(np.nanpercentile(vals, p_low))
        hi = float(np.nanpercentile(vals, p_high))
        if not np.isfinite(lo) or not np.isfinite(hi) or (hi - lo) < 1e-6:
            lo, hi = 0.02, 0.30

    y = (x - lo) / (hi - lo + 1e-12)
    y = np.clip(y, 0.0, 1.0)

    # gamma correction: y^(1/gamma)
    if gamma and gamma > 0:
        y = np.power(y, 1.0 / gamma)

    out = (y * 255.0).astype(np.uint8)
    return out, (lo, hi)


def make_rgba(r8, g8, b8, alpha_mask):
    rgba = np.zeros((r8.shape[0], r8.shape[1], 4), dtype=np.uint8)
    rgba[..., 0] = r8
    rgba[..., 1] = g8
    rgba[..., 2] = b8
    rgba[..., 3] = np.where(alpha_mask, 255, 0).astype(np.uint8)
    return rgba


# -----------------------------
# main
# -----------------------------
def main():
    app = create_app()
    with app.app_context():
        minx, miny, maxx, maxy = get_roi_bbox_from_gpkg()
        bbox = (minx, miny, maxx, maxy)

        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(days=DAYS_BACK)
        end_dt = now

        print(f"[RGB] Ventana: {start_dt.isoformat()} -> {end_dt.isoformat()}")
        print(f"[RGB] Cloud max: {CLOUD_MAX} | max_items: {MAX_ITEMS_TOTAL} | per_tile: {PER_TILE} | fetch_limit: {FETCH_LIMIT}")
        print(f"[RGB] ROI bbox: {bbox}")

        geom = mapping(box(minx, miny, maxx, maxy))

        catalog = open_stac_catalog()
        items_all = search_items(catalog, bbox, geom, start_dt, end_dt)
        picked = pick_items(items_all)

        if not picked:
            print("No hay escenas candidatas; no se actualiza.")
            return 0

        # Sign Planetary Computer items (SAS tokens)
        picked = [pc.sign(it) for it in picked]

        # CRS real (UTM) del tile Sentinel
        dst_crs = get_item_asset_crs(picked[0], asset_key="B04")

        # Grid a 10 m/px (en metros), con salvaguarda RGB_MAX_DIM
        width, height, dst_transform = compute_grid_from_bbox_meters(
            bbox4326=(minx, miny, maxx, maxy),
            dst_crs=dst_crs,
            res_m=RGB_RES_M,
            max_dim=RGB_MAX_DIM,
        )

        print(f"[RGB] dst_crs={dst_crs} | grid={width}x{height} | res_m={RGB_RES_M}")

        r_stack, g_stack, b_stack = [], [], []
        used_ids = []
        skipped = 0

        # Cloud mean aproximado de los usados
        clouds = []

        for it in picked:
            a = it.assets

            # PC: bandas en mayúsculas
            if "B04" not in a or "B03" not in a or "B02" not in a:
                skipped += 1
                continue

            try:
                # reflectancia típica en uint16 escalada (0..10000)
                r = read_band_with_retries(a["B04"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
                g = read_band_with_retries(a["B03"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
                b = read_band_with_retries(a["B02"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)

                r = r.astype(np.float32) / 10000.0
                g = g.astype(np.float32) / 10000.0
                b = b.astype(np.float32) / 10000.0

                # limpiar inválidos
                r[(r <= 0) | (r > 1.5)] = np.nan
                g[(g <= 0) | (g > 1.5)] = np.nan
                b[(b <= 0) | (b > 1.5)] = np.nan

                # máscara nubes por SCL (si existe)
                if "SCL" in a:
                    scl = read_band_with_retries(a["SCL"].href, dst_transform, dst_crs, width, height, Resampling.nearest)
                    scl_i = np.nan_to_num(scl, nan=0).astype(np.int32)
                    bad = np.isin(scl_i, list(INVALID_SCL))
                    r[bad] = np.nan
                    g[bad] = np.nan
                    b[bad] = np.nan

                valid = np.isfinite(r) & np.isfinite(g) & np.isfinite(b)
                valid_frac = float(valid.sum()) / float(valid.size)

                if valid_frac < MIN_VALID_FRAC:
                    if DEBUG_S2:
                        print(f"[RGB] Skip {it.id}: valid_frac={valid_frac:.4f} < {MIN_VALID_FRAC}")
                    skipped += 1
                    continue

                r_stack.append(r)
                g_stack.append(g)
                b_stack.append(b)
                used_ids.append(it.id)
                clouds.append(_cloud(it))

            except Exception as e:
                skipped += 1
                if DEBUG_S2:
                    print(f"[RGB] Error leyendo {it.id}: {repr(e)}")
                continue

        if not r_stack:
            print("[RGB] No se pudo leer ninguna escena válida. No se actualiza.")
            return 0

        r_stack = np.stack(r_stack, axis=0)
        g_stack = np.stack(g_stack, axis=0)
        b_stack = np.stack(b_stack, axis=0)

        if RGB_COMPOSITE == "max":
            r_comp = np.nanmax(r_stack, axis=0)
            g_comp = np.nanmax(g_stack, axis=0)
            b_comp = np.nanmax(b_stack, axis=0)
        else:
            r_comp = np.nanmedian(r_stack, axis=0)
            g_comp = np.nanmedian(g_stack, axis=0)
            b_comp = np.nanmedian(b_stack, axis=0)

        alpha = np.isfinite(r_comp) & np.isfinite(g_comp) & np.isfinite(b_comp)

        # Stretch + gamma por banda
        r8, (r_lo, r_hi) = stretch_and_gamma(r_comp, alpha, gamma=RGB_GAMMA)
        g8, (g_lo, g_hi) = stretch_and_gamma(g_comp, alpha, gamma=RGB_GAMMA)
        b8, (b_lo, b_hi) = stretch_and_gamma(b_comp, alpha, gamma=RGB_GAMMA)

        rgba = make_rgba(r8, g8, b8, alpha)

        # -----------------------------
        # Guardar GeoTIFF UTM + reproyectado 3857 + PNG 3857 + meta.json
        # -----------------------------
        static_dir = Path(app.root_path) / "static" / "sentinel2"
        static_dir.mkdir(parents=True, exist_ok=True)

        ts = now.strftime("%Y%m%d_%H%M%S")

        tif_utm = static_dir / f"s2_rgb_{ts}_utm.tif"
        tif_3857 = static_dir / f"s2_rgb_{ts}_3857.tif"
        png_3857 = static_dir / f"s2_rgb_{ts}_3857.png"

        latest_tif_utm = static_dir / "s2_rgb_latest_utm.tif"
        latest_tif_3857 = static_dir / "s2_rgb_latest_3857.tif"
        latest_png_3857 = static_dir / "s2_rgb_latest_3857.png"
        meta_json = static_dir / "s2_rgb_latest.json"

        # Guardamos el composite en UTM (float32 0..1 aprox)
        profile = {
            "driver": "GTiff",
            "height": r_comp.shape[0],
            "width": r_comp.shape[1],
            "count": 3,
            "dtype": "float32",
            "crs": dst_crs,
            "transform": dst_transform,
            "nodata": np.nan,
            "compress": "deflate",
        }

        with rasterio.open(str(tif_utm), "w", **profile) as dst:
            dst.write(r_comp.astype(np.float32), 1)
            dst.write(g_comp.astype(np.float32), 2)
            dst.write(b_comp.astype(np.float32), 3)

        # Warp a 3857 (para Leaflet)
        warp_rgb_tif_to_3857(str(tif_utm), str(tif_3857))

        # Leer el 3857 y generar PNG (stretch+gamma aquí, ya en 3857)
        with rasterio.open(str(tif_3857)) as ds:
            r3857 = ds.read(1).astype(np.float32)
            g3857 = ds.read(2).astype(np.float32)
            b3857 = ds.read(3).astype(np.float32)

            alpha = np.isfinite(r3857) & np.isfinite(g3857) & np.isfinite(b3857)

            r8, (r_lo, r_hi) = stretch_and_gamma(r3857, alpha, gamma=RGB_GAMMA)
            g8, (g_lo, g_hi) = stretch_and_gamma(g3857, alpha, gamma=RGB_GAMMA)
            b8, (b_lo, b_hi) = stretch_and_gamma(b3857, alpha, gamma=RGB_GAMMA)

            rgba = make_rgba(r8, g8, b8, alpha)

            # bounds reales desde el raster 3857 convertidos a 4326
            b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
            minx2, miny2, maxx2, maxy2 = map(float, b)

        Image.fromarray(rgba, mode="RGBA").save(str(png_3857), format="PNG", optimize=True)

        # Reemplazar "latest" (con safe_replace por Windows)
        ok_tif_utm = safe_replace(str(tif_utm), str(latest_tif_utm))
        ok_tif_3857 = safe_replace(str(tif_3857), str(latest_tif_3857))
        ok_png_3857 = safe_replace(str(png_3857), str(latest_png_3857))

        if not ok_tif_utm:
            print("WARNING: no pude reemplazar s2_rgb_latest_utm.tif (bloqueado).")
        if not ok_tif_3857:
            print("WARNING: no pude reemplazar s2_rgb_latest_3857.tif (bloqueado).")
        if not ok_png_3857:
            print("WARNING: no pude reemplazar s2_rgb_latest_3857.png (bloqueado).")

        cloud_mean = float(np.mean(clouds)) if clouds else None

        meta = {
            "updated_utc": now.isoformat(),
            "window": [start_dt.isoformat(), end_dt.isoformat()],
            "collection": S2_COLLECTION,
            "items_total_found": len(items_all),
            "items_used": used_ids,
            "used": len(used_ids),
            "skipped": skipped,
            "bbox": [minx2, miny2, maxx2, maxy2],  # bounds reales (lon/lat) del 3857
            "bounds_leaflet": [[miny2, minx2], [maxy2, maxx2]],
            "size": [int(width), int(height)],
            "cloud_max": CLOUD_MAX,
            "cloud_mean_used": cloud_mean,
            "composite": RGB_COMPOSITE,
            "gamma": RGB_GAMMA,
            "stretch": {
                "r": {"p2": r_lo, "p98": r_hi},
                "g": {"p2": g_lo, "p98": g_hi},
                "b": {"p2": b_lo, "p98": b_hi},
            },
            "min_valid_frac": MIN_VALID_FRAC,
            "latest_png": latest_png_3857.name,
            "latest_tif_utm": latest_tif_utm.name,
            "latest_tif_3857": latest_tif_3857.name,
        }
        meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"OK: actualizado {latest_png_3857} (used={len(used_ids)}, skipped={skipped})")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())