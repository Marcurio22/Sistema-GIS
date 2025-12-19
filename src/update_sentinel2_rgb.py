import os
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import geopandas as gpd
from PIL import Image

import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
from rasterio.features import rasterize

from shapely.geometry import box, mapping

from pystac_client import Client
from pystac_client.exceptions import APIError
import planetary_computer as pc

from webapp import create_app


# ---------------------------
# ENV / Config
# ---------------------------
ROI_PATH = os.getenv("ROI_PATH", str(Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg"))

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_COLLECTION = os.getenv("S2_STAC_COLLECTION", "sentinel-2-l2a")

DAYS_BACK = int(os.getenv("S2_DAYS_BACK", "120"))
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "40"))
MAX_ITEMS = int(os.getenv("S2_MAX_ITEMS_TOTAL", "12"))
PER_TILE = int(os.getenv("S2_PER_TILE", "2"))
FETCH_LIMIT = int(os.getenv("S2_FETCH_LIMIT", "200"))

RGB_MAX_DIM = int(os.getenv("RGB_MAX_DIM", "4096"))
DEBUG_STAC = os.getenv("DEBUG_STAC", "0") == "1"
DEBUG_S2 = os.getenv("DEBUG_S2", "0") == "1"

# descartar escenas con poco pixel válido tras SCL
MIN_VALID_FRAC = float(os.getenv("RGB_MIN_VALID_FRAC", "0.05"))

# SCL inválidos (nubes/sombras/nieve/nodata)
INVALID_SCL = {0, 1, 3, 7, 8, 9, 10, 11}

# True color bands (PC usa estas keys en mayúsculas)
BAND_R = "B04"
BAND_G = "B03"
BAND_B = "B02"
BAND_SCL = "SCL"


# ---------------------------
# ROI (bbox + geometría)
# ---------------------------
def load_roi_4326():
    roi_path = Path(ROI_PATH)
    if not roi_path.exists():
        raise FileNotFoundError(f"ROI no existe: {roi_path.resolve()}")

    roi = gpd.read_file(roi_path).to_crs(4326)
    geom = roi.unary_union  # Multi/Polygon
    minx, miny, maxx, maxy = roi.total_bounds
    return geom, (float(minx), float(miny), float(maxx), float(maxy))


def compute_output_shape(minx, miny, maxx, maxy, max_dim=4096, min_dim=512):
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


# ---------------------------
# STAC
# ---------------------------
def open_pc_stac():
    cat = Client.open(PC_STAC)
    if DEBUG_STAC:
        cols = list(cat.get_collections())
        print(f"[STAC] Abierto PC: {PC_STAC} | colecciones: {len(cols)}")
        print("[STAC] Ejemplos:", [c.id for c in cols[:20]])
    return cat


def _cloud(item):
    return float((item.properties or {}).get("eo:cloud_cover", 999.0))


def _dt(item):
    return item.datetime or datetime(1970, 1, 1, tzinfo=timezone.utc)


def _tile_id(item):
    p = item.properties or {}
    return p.get("s2:mgrs_tile") or p.get("mgrs:tile") or "UNKNOWN"


def search_items_with_retry(catalog, geom_geojson, bbox, start_dt, end_dt, retries=3):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            search = catalog.search(
                collections=[S2_COLLECTION],
                intersects=geom_geojson,
                datetime=f"{start_dt.isoformat()}/{end_dt.isoformat()}",
                limit=FETCH_LIMIT,
            )
            items = list(search.items())
            if not items:
                search = catalog.search(
                    collections=[S2_COLLECTION],
                    bbox=list(bbox),
                    datetime=f"{start_dt.isoformat()}/{end_dt.isoformat()}",
                    limit=FETCH_LIMIT,
                )
                items = list(search.items())
            return items
        except APIError as e:
            last_err = e
            wait = 1.5 * attempt
            print(f"[STAC] APIError (intento {attempt}/{retries}): {e}. Reintentando en {wait:.1f}s")
            time.sleep(wait)

    raise RuntimeError(f"No se pudo consultar STAC tras {retries} intentos. Último error: {last_err}")


def pick_items_latest(items):
    """
    Importante: para “satélite actual”, priorizamos *recencia*.
    1) Filtra por CLOUD_MAX.
    2) Ordena por datetime desc (más reciente primero), y por cloud como desempate.
    3) Limita por PER_TILE + MAX_ITEMS.
    """
    print(f"[RGB] Items encontrados (sin filtrar): {len(items)}")

    items = [it for it in items if _cloud(it) <= CLOUD_MAX]
    items.sort(key=lambda it: (-_dt(it).timestamp(), _cloud(it)))

    per_tile = {}
    picked = []
    for it in items:
        t = _tile_id(it)
        per_tile.setdefault(t, 0)
        if per_tile[t] >= PER_TILE:
            continue
        picked.append(it)
        per_tile[t] += 1
        if len(picked) >= MAX_ITEMS:
            break

    if DEBUG_S2 and picked:
        it0 = picked[0]
        print("[RGB] Ejemplo ID:", it0.id)
        print("[RGB] Ejemplo datetime:", it0.datetime)
        print("[RGB] Ejemplo cloud:", _cloud(it0))
        print("[RGB] Ejemplo tile:", _tile_id(it0))
        print("[RGB] Assets keys ejemplo:", list(it0.assets.keys())[:40])
        print("[RGB] Tiles en picked:", sorted(per_tile.keys()))
        print(f"[RGB] picked total: {len(picked)} (<= {MAX_ITEMS})")

    print(f"[RGB] Items tras filtro nube<= {CLOUD_MAX}: {len(picked)}")
    return picked


# ---------------------------
# Raster helpers
# ---------------------------
def reproject_band_to_grid(href, dst_transform, dst_crs, width, height, resampling, retries=3):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            env_opts = dict(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff,.jp2",
                GDAL_HTTP_MAX_RETRY="3",
                GDAL_HTTP_RETRY_DELAY="1",
            )
            with rasterio.Env(**env_opts):
                with rasterio.open(href) as src:
                    dst = np.full((height, width), np.nan, dtype=np.float32)
                    reproject(
                        source=rasterio.band(src, 1),
                        destination=dst,
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=dst_transform,
                        dst_crs=dst_crs,
                        resampling=resampling,
                        dst_nodata=np.nan,
                    )
                    return dst
        except Exception as e:
            last_err = e
            if DEBUG_S2:
                print(f"[RGB] Reintento {attempt}/{retries} falló leyendo banda: {e}")
            time.sleep(0.8 * attempt)
    raise RuntimeError(str(last_err))


def sr_to_srgb_8bit(r, g, b, gamma=2.2):
    """
    Sentinel-2 L2A en Planetary Computer: reflectancia escalada ~ 0..10000.
    Convertimos a 0..1, hacemos un estirado suave y aplicamos gamma sRGB.
    """
    rgb = np.stack([r, g, b], axis=0).astype(np.float32)  # (3,H,W)

    # escala física
    rgb = rgb / 10000.0
    rgb = np.clip(rgb, 0.0, 1.0)

    # estirado suave global (evita "rosa")
    # clip a percentiles sobre válidos
    valid = np.isfinite(rgb).all(axis=0)
    if np.any(valid):
        v = rgb[:, valid]
        lo = np.percentile(v, 1)
        hi = np.percentile(v, 99)
        if hi <= lo:
            hi = lo + 1e-6
        rgb = (rgb - lo) / (hi - lo)
        rgb = np.clip(rgb, 0.0, 1.0)

    # gamma
    rgb = np.power(rgb, 1.0 / gamma)

    out = (rgb * 255.0).astype(np.uint8)
    return out  # (3,H,W)


def atomic_replace_with_retry(src_tmp: str, dst_final: Path, retries=8, wait=0.35):
    last = None
    for i in range(1, retries + 1):
        try:
            os.replace(src_tmp, str(dst_final))
            return True
        except PermissionError as e:
            last = e
            print(f"[RGB] Destino bloqueado (intento {i}/{retries}). Cierra visor/preview o para Flask. Reintento en {wait:.2f}s")
            time.sleep(wait)
    print(f"[RGB] ERROR: no pude reemplazar {dst_final}. Detalle: {last}")
    return False


# ---------------------------
# main
# ---------------------------
def main():
    app = create_app()
    with app.app_context():
        roi_geom, bbox = load_roi_4326()
        minx, miny, maxx, maxy = bbox

        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(days=DAYS_BACK)
        end_dt = now

        print(f"[RGB] Ventana: {start_dt.isoformat()} -> {end_dt.isoformat()}")
        print(f"[RGB] Cloud max: {CLOUD_MAX} | max_items: {MAX_ITEMS} | per_tile: {PER_TILE} | fetch_limit: {FETCH_LIMIT}")
        print(f"[RGB] ROI bbox: {bbox}")

        catalog = open_pc_stac()

        geom_geojson = mapping(roi_geom)  # mejor que bbox para búsqueda
        items_all = search_items_with_retry(catalog, geom_geojson, bbox, start_dt, end_dt, retries=3)
        items = pick_items_latest(items_all)

        if not items:
            print("No hay escenas candidatas; no se actualiza.")
            return 0

        # firmar URLs
        items = [pc.sign(it) for it in items]

        width, height = compute_output_shape(minx, miny, maxx, maxy, max_dim=RGB_MAX_DIM)
        dst_crs = "EPSG:4326"
        dst_transform = from_bounds(minx, miny, maxx, maxy, width, height)

        # máscara ROI para alpha (quita triángulos/zonas fuera del ROI si quieres)
        roi_mask = rasterize(
            [(roi_geom, 1)],
            out_shape=(height, width),
            transform=dst_transform,
            fill=0,
            dtype=np.uint8,
            all_touched=False,
        ).astype(bool)

        rgb_stack = []
        used_ids = []
        skipped = 0

        for it in items:
            try:
                a = it.assets
                for k in (BAND_R, BAND_G, BAND_B):
                    if k not in a:
                        raise RuntimeError(f"Item sin banda {k}")

                r = reproject_band_to_grid(a[BAND_R].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
                g = reproject_band_to_grid(a[BAND_G].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
                b = reproject_band_to_grid(a[BAND_B].href, dst_transform, dst_crs, width, height, Resampling.bilinear)

                # máscara nubes/sombras por SCL
                if BAND_SCL in a:
                    scl = reproject_band_to_grid(a[BAND_SCL].href, dst_transform, dst_crs, width, height, Resampling.nearest)
                    scl_i = np.nan_to_num(scl, nan=0).astype(np.int32)
                    bad = np.isin(scl_i, list(INVALID_SCL))
                else:
                    bad = np.zeros((height, width), dtype=bool)

                # aplicar máscara ROI (para alpha)
                bad = bad | (~roi_mask)

                r = r.astype(np.float32); g = g.astype(np.float32); b = b.astype(np.float32)
                r[bad] = np.nan; g[bad] = np.nan; b[bad] = np.nan

                valid_frac = float(np.isfinite(r).mean())
                if valid_frac < MIN_VALID_FRAC:
                    if DEBUG_S2:
                        print(f"[RGB] Skip {it.id}: valid_frac={valid_frac:.4f} < {MIN_VALID_FRAC}")
                    skipped += 1
                    continue

                rgb_stack.append(np.stack([r, g, b], axis=0))
                used_ids.append(it.id)

            except Exception as e:
                skipped += 1
                print(f"[RGB] Error leyendo {it.id}: {e}")

        if not rgb_stack:
            print("No se pudo leer ninguna escena útil. No se actualiza.")
            return 0

        stack = np.stack(rgb_stack, axis=0)  # (T,3,H,W)
        comp = np.nanmedian(stack, axis=0)   # (3,H,W)

        # alpha: donde hay NaN -> transparente
        alpha = np.where(np.isfinite(comp).all(axis=0), 255, 0).astype(np.uint8)

        # si todo es transparente, no pisar latest
        if alpha.max() == 0:
            print("Composite vacío (todo nubes/NaN). No se actualiza.")
            return 0

        # a 8-bit “real”
        rgb8 = sr_to_srgb_8bit(comp[0], comp[1], comp[2])  # (3,H,W)
        rgb8 = np.transpose(rgb8, (1, 2, 0))               # (H,W,3)
        rgba = np.dstack([rgb8, alpha])                    # (H,W,4)

        # Guardar
        static_dir = Path(app.root_path) / "static" / "sentinel2"
        static_dir.mkdir(parents=True, exist_ok=True)

        out_png = static_dir / "s2_rgb_latest.png"
        out_meta = static_dir / "s2_rgb_latest.json"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png", dir=str(static_dir)) as tmp:
            tmp_png = tmp.name

        Image.fromarray(rgba, mode="RGBA").save(tmp_png, format="PNG", optimize=True)

        ok = atomic_replace_with_retry(tmp_png, out_png)
        if not ok:
            print(f"[RGB] WARNING: generado pero NO se pudo actualizar latest por bloqueo. Temporal: {tmp_png}")
            return 0

        meta = {
            "updated_utc": now.isoformat(),
            "window": [start_dt.isoformat(), end_dt.isoformat()],
            "collection": S2_COLLECTION,
            "items_total_found": len(items_all),
            "items_used": used_ids,
            "used": len(used_ids),
            "skipped": skipped,
            "bbox": [minx, miny, maxx, maxy],
            "size": [width, height],
            "cloud_max": CLOUD_MAX,
            "per_tile": PER_TILE,
            "min_valid_frac": MIN_VALID_FRAC,
        }
        out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"OK: actualizado {out_png} (used={len(used_ids)}, skipped={skipped})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())