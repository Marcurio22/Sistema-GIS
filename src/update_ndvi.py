#!/usr/bin/env python3
import os
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import geopandas as gpd
from shapely.geometry import box, mapping, shape

from PIL import Image

import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
from rasterio.mask import mask

from pystac_client import Client
import planetary_computer as pc

from sqlalchemy import text
from webapp import create_app, db

# -----------------------------
# Config (por entorno)
# -----------------------------
ROI_PATH = os.getenv("ROI_PATH", str(Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg"))

DAYS_BACK = int(os.getenv("S2_DAYS_BACK", "180"))
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "60"))
MAX_ITEMS_TOTAL = int(os.getenv("S2_MAX_ITEMS_TOTAL", "30"))
PER_TILE = int(os.getenv("S2_MAX_ITEMS_PER_TILE", "5"))
FETCH_LIMIT = int(os.getenv("S2_FETCH_LIMIT", "200"))

NDVI_MAX_DIM = int(os.getenv("NDVI_MAX_DIM", "2048"))
NDVI_COMPOSITE = os.getenv("NDVI_COMPOSITE", "max").lower()  # max | median
MIN_VALID_FRAC = float(os.getenv("NDVI_MIN_VALID_FRAC", "0.02"))

DEBUG_STAC = os.getenv("DEBUG_STAC", "0") == "1"
DEBUG_S2 = os.getenv("DEBUG_S2", "0") == "1"

S2_COLLECTION = os.getenv("S2_STAC_COLLECTION", "sentinel-2-l2a")
STAC_URL = os.getenv("STAC_URL", "https://planetarycomputer.microsoft.com/api/stac/v1")

# SCL inválidos (nubes/sombras/nieve/nodata, etc.)
INVALID_SCL = {0, 1, 3, 7, 8, 9, 10, 11}


# -----------------------------
# Utilidades
# -----------------------------
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
def fetch_recintos_geojson():
    sql = text("""
        SELECT id_recinto, ST_AsGeoJSON(geom) AS geojson
        FROM public.recintos
        WHERE geom IS NOT NULL
    """)
    rows = db.session.execute(sql).fetchall()
    return [(int(r.id_recinto), r.geojson) for r in rows]


def zonal_stats_for_geom(dataset, geom):
    data, _ = mask(dataset, [geom], crop=True, nodata=np.nan, filled=True)
    arr = data[0].astype(np.float32)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    return {
        "mean": float(np.mean(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "std": float(np.std(arr)),
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

        # Firma Planetary Computer (tokens SAS)
        items = [pc.sign(item) for item in items]

        width, height = compute_output_shape(minx, miny, maxx, maxy, max_dim=NDVI_MAX_DIM)
        dst_crs = "EPSG:4326"
        dst_transform = from_bounds(minx, miny, maxx, maxy, width, height)

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

        # -----------------------------
        # Guardar GeoTIFF + latest PNG (RGBA)
        # -----------------------------
        static_ndvi_dir = Path(app.root_path) / "static" / "ndvi"
        static_ndvi_dir.mkdir(parents=True, exist_ok=True)

        # versionado por timestamp (evita choques si lo tienes abierto)
        ts = now.strftime("%Y%m%d_%H%M%S")
        tif_path = static_ndvi_dir / f"ndvi_{ts}.tif"
        png_path = static_ndvi_dir / f"ndvi_{ts}.png"

        latest_tif = static_ndvi_dir / "ndvi_latest.tif"
        latest_png = static_ndvi_dir / "ndvi_latest.png"
        meta_json = static_ndvi_dir / "ndvi_latest.json"

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

        # GeoTIFF (primero a versionado)
        with rasterio.open(str(tif_path), "w", **profile) as dst:
            dst.write(comp.astype(np.float32), 1)

        # PNG RGBA (primero a versionado)
        rgba = ndvi_to_rgba(comp)
        Image.fromarray(rgba, mode="RGBA").save(str(png_path), format="PNG", optimize=True)

        print(f"OK: NDVI GeoTIFF -> {tif_path}")
        print(f"OK: NDVI PNG -> {png_path}")

        # intenta actualizar latest (robusto en Windows)
        # si está bloqueado, no crashea; deja los versionados y avisa
        ok_tif = safe_replace(str(tif_path), str(latest_tif))
        ok_png = safe_replace(str(png_path), str(latest_png))

        if not ok_tif:
            print("WARNING: no pude reemplazar ndvi_latest.tif (bloqueado). Se queda la versión con timestamp.")
        if not ok_png:
            print("WARNING: no pude reemplazar ndvi_latest.png (bloqueado). Se queda la versión con timestamp.")

        # meta (Leaflet bounds correctos)
        meta = {
            "updated_utc": now.isoformat(),
            "window": [start_dt.isoformat(), end_dt.isoformat()],
            "collection": S2_COLLECTION,
            "composite": NDVI_COMPOSITE,
            "items_used": used_ids,
            "used": len(used_ids),
            "skipped": skipped,
            "bbox": [minx, miny, maxx, maxy],  # lon/lat
            "bounds_leaflet": [[miny, minx], [maxy, maxx]],  # lat/lon
            "size": [width, height],
            "cloud_max": CLOUD_MAX,
            "per_tile": PER_TILE,
            "min_valid_frac": MIN_VALID_FRAC,
            "latest_png": str(latest_png.name),
            "latest_tif": str(latest_tif.name),
        }
        meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # -----------------------------
        # BBDD
        # -----------------------------
        try:
            # 1) Insert en public.imagenes (cumple CHECK: origen en {satelite,dron})
            # OJO: bbox geom está en EPSG:4326 => ST_MakeEnvelope(xmin,ymin,xmax,ymax,4326)
            sql_img = text("""
                INSERT INTO public.imagenes
                  (origen, fecha_adquisicion, epsg, sensor, resolucion_m, bbox, ruta_archivo)
                VALUES
                  (:origen, :fecha, :epsg, :sensor, :res, ST_MakeEnvelope(:minx,:miny,:maxx,:maxy,4326), :ruta)
                RETURNING id_imagen
            """)
            # guardamos ruta relativa (más portable)
            ruta_rel = str(Path("static") / "ndvi" / "ndvi_latest.tif")
            id_imagen = db.session.execute(sql_img, {
                "origen": "satelite",
                "fecha": now,
                "epsg": 4326,
                "sensor": f"Sentinel-2 L2A (Planetary Computer) NDVI | composite={NDVI_COMPOSITE}",
                "res": 10.0,
                "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy,
                "ruta": ruta_rel,
            }).scalar()

            recintos = fetch_recintos_geojson()

            # Abrimos el latest_tif (si está bloqueado y no se pudo reemplazar, abrimos el versionado)
            tif_to_open = latest_tif if ok_tif else Path(str(tif_path))
            with rasterio.open(str(tif_to_open)) as ds:
                inserted = 0
                for id_recinto, gj in recintos:
                    geom_rec = shape(json.loads(gj))
                    stats = zonal_stats_for_geom(ds, geom_rec)
                    if not stats:
                        continue

                    sql_idx = text("""
                        INSERT INTO public.indices_raster
                          (id_imagen, id_recinto, id_parcela, tipo_indice, fecha_calculo, epsg, resolucion_m,
                           valor_medio, valor_min, valor_max, desviacion_std, ruta_raster)
                        VALUES
                          (:id_imagen, :id_recinto, NULL, :tipo, :fecha, :epsg, :res,
                           :mean, :min, :max, :std, :ruta)
                    """)
                    db.session.execute(sql_idx, {
                        "id_imagen": int(id_imagen),
                        "id_recinto": int(id_recinto),
                        "tipo": "NDVI",
                        "fecha": now,
                        "epsg": 4326,
                        "res": 10.0,
                        "mean": stats["mean"],
                        "min": stats["min"],
                        "max": stats["max"],
                        "std": stats["std"],
                        "ruta": ruta_rel,
                    })
                    inserted += 1

            db.session.commit()
            print(f"OK: NDVI guardado en BBDD -> imagenes.id_imagen={id_imagen} | indices_raster insertados={inserted}")
        except Exception as e:
            db.session.rollback()
            print("WARNING: No se pudo guardar NDVI en BBDD. Los ficheros sí se han generado.")
            print("Detalle error:", repr(e))

        return 0


if __name__ == "__main__":
    raise SystemExit(main())