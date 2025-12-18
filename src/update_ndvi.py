#!/usr/bin/env python3
import os
import json
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
from sqlalchemy import text

from webapp import create_app, db

# -----------------------------
# Config (por entorno)
# -----------------------------
ROI_PATH = os.getenv("ROI_PATH", "../data/processed/roi.gpkg")
DAYS_BACK = int(os.getenv("S2_DAYS_BACK", "14"))
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "70"))
MAX_ITEMS_TOTAL = int(os.getenv("S2_MAX_ITEMS_TOTAL", "18"))

NDVI_MAX_DIM = int(os.getenv("NDVI_MAX_DIM", "2048"))
NDVI_COMPOSITE = os.getenv("NDVI_COMPOSITE", "max").lower()  # max | median

# SCL inválidos (nubes/sombras/nieve/nodata, etc.)
INVALID_SCL = {0, 1, 3, 7, 8, 9, 10, 11}

# -----------------------------
# ROI (como tú)
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

# -----------------------------
# STAC
# -----------------------------
def open_stac_catalog():
    for url in ("https://earth-search.aws.element84.com/v1", "https://earth-search.aws.element84.com/v0"):
        try:
            return Client.open(url)
        except Exception:
            pass
    raise RuntimeError("No se pudo abrir Earth Search STAC (v0/v1).")

def _cloud(item):
    return float((item.properties or {}).get("eo:cloud_cover", 999.0))

def search_items(catalog, geom_geojson, start_dt, end_dt):
    search = catalog.search(
        collections=["sentinel-s2-l2a-cogs"],
        intersects=geom_geojson,
        datetime=f"{start_dt.isoformat()}/{end_dt.isoformat()}",
    )
    return list(search.get_items())

def pick_items(items):
    items = [it for it in items if _cloud(it) <= CLOUD_MAX]
    items.sort(key=lambda it: (_cloud(it), -(it.datetime or datetime(1970,1,1,tzinfo=timezone.utc)).timestamp()))
    return items[:MAX_ITEMS_TOTAL]

# -----------------------------
# Raster reproyección remota
# -----------------------------
def _href_readable(href: str) -> str:
    if href.startswith("s3://"):
        return "/vsis3/" + href[len("s3://"):]
    return href

def reproject_to_grid(href, dst_transform, dst_crs, width, height, resampling, dtype=np.float32, nodata=np.nan):
    href = _href_readable(href)
    env_opts = dict(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR")
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

# -----------------------------
# NDVI -> PNG (RGBA simple)
# -----------------------------
def ndvi_to_rgba(ndvi):
    h, w = ndvi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid = np.isfinite(ndvi)
    if not np.any(valid):
        return rgba

    v = np.clip(ndvi, -0.2, 0.9)
    t = (v + 0.2) / 1.1  # 0..1

    stops = [
        (0.00, (120,  60,  40)),
        (0.25, (200, 140,  60)),
        (0.45, (240, 210, 120)),
        (0.65, (170, 220, 140)),
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
# BBDD: cargar recintos (geojson) para stats
# -----------------------------
def fetch_recintos_geojson():
    # Ajusta WHERE si quieres solo activos, o solo con propietario, etc.
    sql = text("""
        SELECT id_recinto, ST_AsGeoJSON(geometry) AS geojson
        FROM public.recintos
        WHERE geometry IS NOT NULL
    """)
    rows = db.session.execute(sql).fetchall()
    return [(int(r.id_recinto), r.geojson) for r in rows]

def zonal_stats_for_geom(dataset, geom):
    # geom en WGS84; dataset también lo vamos a guardar en EPSG:4326
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

        geom = mapping(box(minx, miny, maxx, maxy))
        catalog = open_stac_catalog()

        items = pick_items(search_items(catalog, geom, start_dt, end_dt))
        if not items:
            print("No hay escenas candidatas; no se actualiza.")
            return 0

        width, height = compute_output_shape(minx, miny, maxx, maxy, max_dim=NDVI_MAX_DIM)
        dst_crs = "EPSG:4326"
        dst_transform = from_bounds(minx, miny, maxx, maxy, width, height)

        ndvi_stack = []

        for it in items:
            a = it.assets
            if "B04" not in a or "B08" not in a:
                continue

            red = reproject_to_grid(a["B04"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
            nir = reproject_to_grid(a["B08"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)

            red = red.astype(np.float32); nir = nir.astype(np.float32)
            red[red == 0] = np.nan
            nir[nir == 0] = np.nan

            if "SCL" in a:
                scl = reproject_to_grid(a["SCL"].href, dst_transform, dst_crs, width, height, Resampling.nearest)
                scl_i = np.nan_to_num(scl, nan=0).astype(np.int32)
                bad = np.isin(scl_i, list(INVALID_SCL))
                red[bad] = np.nan
                nir[bad] = np.nan

            ndvi_stack.append(compute_ndvi(red, nir))

        if not ndvi_stack:
            print("No se pudo calcular NDVI (sin datos).")
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
        # Guardar raster histórico (GeoTIFF) + latest PNG
        # -----------------------------
        static_ndvi_dir = Path(app.root_path) / "static" / "ndvi"
        static_ndvi_dir.mkdir(parents=True, exist_ok=True)

        date_tag = now.strftime("%Y%m%d")
        tif_path = static_ndvi_dir / f"ndvi_{date_tag}.tif"
        latest_png = static_ndvi_dir / "ndvi_latest.png"
        meta_json = static_ndvi_dir / f"ndvi_{date_tag}.json"

        # GeoTIFF atómico
        tmp_tif = None
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
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tif", dir=str(static_ndvi_dir)) as tmp:
            tmp_tif = tmp.name
        with rasterio.open(tmp_tif, "w", **profile) as dst:
            dst.write(comp.astype(np.float32), 1)
        os.replace(tmp_tif, tif_path)

        # PNG latest (RGBA) atómico
        rgba = ndvi_to_rgba(comp)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png", dir=str(static_ndvi_dir)) as tmp:
            tmp_png = tmp.name
        Image.fromarray(rgba, mode="RGBA").save(tmp_png, format="PNG", optimize=True)
        os.replace(tmp_png, latest_png)

        # meta
        meta = {
            "updated_utc": now.isoformat(),
            "window": [start_dt.isoformat(), end_dt.isoformat()],
            "composite": NDVI_COMPOSITE,
            "items_used": [it.id for it in items],
            "bbox": [minx, miny, maxx, maxy],
            "size": [width, height],
            "tif": str(tif_path),
        }
        meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # -----------------------------
        # Insertar en BBDD: imagenes_satelitales + indices_raster
        # -----------------------------
        # 1) crear "imagen" (un lote/composite)
        sql_img = text("""
            INSERT INTO public.imagenes_satelitales
              (satelite, fecha_adquisicion, cobertura_nubes, nivel_procesamiento, producto_id, bandas_disponibles)
            VALUES
              (:sat, :fecha, :nubes, :nivel, :prod, :bandas)
            RETURNING id_imagen
        """)
        id_imagen = db.session.execute(sql_img, {
            "sat": "Sentinel-2",
            "fecha": now,
            "nubes": None,
            "nivel": f"L2A COG composite {NDVI_COMPOSITE}",
            "prod": ",".join([it.id for it in items])[:120],  # campo es varchar(120)
            "bandas": "B04,B08,SCL",
        }).scalar()

        # 2) stats por recinto
        recintos = fetch_recintos_geojson()

        with rasterio.open(tif_path) as ds:
            inserted = 0
            for id_recinto, gj in recintos:
                geom = shape(json.loads(gj))
                stats = zonal_stats_for_geom(ds, geom)
                if not stats:
                    continue

                sql_idx = text("""
                    INSERT INTO public.indices_raster
                      (id_imagen, id_recinto, tipo_indice, fecha_calculo, epsg, resolucion_m,
                       valor_medio, valor_min, valor_max, desviacion_std, ruta_raster)
                    VALUES
                      (:id_imagen, :id_recinto, :tipo, :fecha, :epsg, :res,
                       :mean, :min, :max, :std, :ruta)
                """)
                db.session.execute(sql_idx, {
                    "id_imagen": int(id_imagen),
                    "id_recinto": int(id_recinto),
                    "tipo": "NDVI",
                    "fecha": now,
                    "epsg": 4326,
                    "res": None,
                    "mean": stats["mean"],
                    "min": stats["min"],
                    "max": stats["max"],
                    "std": stats["std"],
                    "ruta": str(tif_path),
                })
                inserted += 1

        db.session.commit()
        print(f"OK: NDVI guardado + {inserted} registros en indices_raster (id_imagen={id_imagen})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())