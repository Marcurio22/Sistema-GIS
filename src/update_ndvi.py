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

# Planetary Computer signing (muy recomendable)
try:
    import planetary_computer as pc
except Exception:
    pc = None

from sqlalchemy import text
from webapp import create_app, db


# -----------------------------
# Config (por entorno)
# -----------------------------
ROI_PATH = os.getenv("ROI_PATH", "../data/processed/roi.gpkg")

# ventana de búsqueda
DAYS_BACK = int(os.getenv("S2_DAYS_BACK", "180"))
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "60"))
MAX_ITEMS = int(os.getenv("S2_MAX_ITEMS_TOTAL", "30"))
PER_TILE = int(os.getenv("S2_PER_TILE", "5"))      # nº escenas por tile MGRS
FETCH_LIMIT = int(os.getenv("S2_FETCH_LIMIT", "200"))

DEBUG_STAC = os.getenv("DEBUG_STAC", "0") == "1"
DEBUG_S2 = os.getenv("DEBUG_S2", "0") == "1"

# colección STAC (Planetary Computer)
S2_COLLECTION = os.getenv("S2_STAC_COLLECTION", "sentinel-2-l2a")

# tamaño salida
NDVI_MAX_DIM = int(os.getenv("NDVI_MAX_DIM", "2048"))
NDVI_COMPOSITE = os.getenv("NDVI_COMPOSITE", "max").lower()  # max | median

# En PC, SCL está en 0..11; valores inválidos típicos:
INVALID_SCL = {0, 1, 3, 7, 8, 9, 10, 11}  # nodata/sat/shadow/cloud/cirrus/snow


# -----------------------------
# Util: replace con reintentos (Windows locks)
# -----------------------------
def atomic_replace_with_retry(src_tmp: str, dst: str, tries: int = 8, sleep_s: float = 0.35):
    """
    Windows puede bloquear el destino si está abierto.
    Reintentamos os.replace; si no se puede, dejamos el tmp movido a un nombre alternativo.
    """
    dst_path = Path(dst)
    last_err = None
    for i in range(tries):
        try:
            os.replace(src_tmp, dst)
            return dst
        except PermissionError as e:
            last_err = e
            time.sleep(sleep_s * (i + 1))
        except OSError as e:
            last_err = e
            time.sleep(sleep_s * (i + 1))

    alt = str(dst_path.with_name(dst_path.stem + "_new" + dst_path.suffix))
    try:
        os.replace(src_tmp, alt)
        print(f"[NDVI] WARNING: destino bloqueado. Guardado alternativo: {alt}")
        return alt
    except Exception as e:
        print(f"[NDVI] ERROR: no pude mover tmp ni al destino ni alternativo. tmp={src_tmp} err={e}")
        raise last_err


# -----------------------------
# ROI (manteniendo tu patrón bbox)
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
# STAC (Planetary Computer)
# -----------------------------
def open_pc_catalog():
    url = "https://planetarycomputer.microsoft.com/api/stac/v1"
    cat = Client.open(url)
    if DEBUG_STAC:
        cols = list(cat.get_collections())
        print(f"[STAC] Abierto PC: {url} | colecciones: {len(cols)}")
        print("[STAC] Ejemplos:", [c.id for c in cols[:20]])
    return cat


def sign_item_if_needed(item):
    if pc is None:
        return item
    try:
        return pc.sign(item)
    except Exception:
        # si por lo que sea falla, devolvemos tal cual
        return item


def _cloud(item):
    return float((item.properties or {}).get("eo:cloud_cover", 999.0))


def _tile(item):
    # Planetary Computer sentinel-2-l2a: normalmente "s2:mgrs_tile" o "mgrs:utm_zone" etc.
    props = item.properties or {}
    return props.get("s2:mgrs_tile") or props.get("mgrs:tile") or props.get("s2:tile_id") or "UNKNOWN"


def search_items(catalog, geom_geojson, bbox, start_dt, end_dt):
    # Intersects primero, si el API peta, fallback a bbox
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
        print(f"[NDVI] WARNING: search(intersects) falló: {e}")

    if not items:
        search = catalog.search(
            collections=[S2_COLLECTION],
            bbox=list(bbox),
            datetime=f"{start_dt.isoformat()}/{end_dt.isoformat()}",
            limit=FETCH_LIMIT,
        )
        items = list(search.items())

    if DEBUG_S2:
        print(f"[NDVI] Colección usada: {S2_COLLECTION}")
        print(f"[NDVI] Items encontrados (sin filtrar): {len(items)}")
        if items:
            it0 = items[0]
            print("[NDVI] Ejemplo ID:", it0.id)
            print("[NDVI] Ejemplo datetime:", it0.datetime)
            print("[NDVI] Ejemplo cloud:", (it0.properties or {}).get("eo:cloud_cover"))
            print("[NDVI] Ejemplo tile:", _tile(it0))
            print("[NDVI] Assets keys ejemplo:", list(it0.assets.keys())[:40])
    return items


def pick_items_balanced(items):
    # 1) filtra por nube
    items = [it for it in items if _cloud(it) <= CLOUD_MAX]

    # 2) orden: menor nubosidad y más reciente
    def dt(it):
        return it.datetime or datetime(1970, 1, 1, tzinfo=timezone.utc)

    items.sort(key=lambda it: (_cloud(it), -dt(it).timestamp()))

    # 3) balance por tile
    per_tile = {}
    picked = []
    for it in items:
        t = _tile(it)
        per_tile.setdefault(t, 0)
        if per_tile[t] >= PER_TILE:
            continue
        picked.append(it)
        per_tile[t] += 1
        if len(picked) >= MAX_ITEMS:
            break

    if DEBUG_S2:
        print("[NDVI] Tiles en picked:", list(per_tile.keys()))
        print(f"[NDVI] picked total: {len(picked)} (<= {MAX_ITEMS})")
        print(f"[NDVI] Items tras filtro nube<= {CLOUD_MAX}: {len(items)}")

    return picked


# -----------------------------
# Raster reproyección remota
# -----------------------------
def _href_readable(href: str) -> str:
    # En Planetary Computer suelen ser https, y pc.sign ya mete token
    if href.startswith("s3://"):
        return "/vsis3/" + href[len("s3://"):]
    return href


def reproject_to_grid(href, dst_transform, dst_crs, width, height, resampling, dtype=np.float32, nodata=np.nan):
    href = _href_readable(href)
    env_opts = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR")
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
# NDVI -> PNG (RGBA)
#   - imagen completa del bbox
#   - no recortamos a ROI
# -----------------------------
def ndvi_to_rgba(ndvi):
    h, w = ndvi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    valid = np.isfinite(ndvi)
    if not np.any(valid):
        # todo no-data: dejamos transparente pero del tamaño bbox
        return rgba

    v = np.clip(ndvi, -0.2, 0.9)
    t = (v + 0.2) / 1.1  # 0..1

    # paleta simple (tierra->verde)
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
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)  # transparente solo donde no-data
    return rgba


# -----------------------------
# BBDD: recintos para stats
# -----------------------------
def fetch_recintos_geojson():
    sql = text("""
        SELECT id_recinto, ST_AsGeoJSON(geometry) AS geojson
        FROM public.recintos
        WHERE geometry IS NOT NULL
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
        bbox = (minx, miny, maxx, maxy)

        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(days=DAYS_BACK)
        end_dt = now

        print(f"[NDVI] Ventana: {start_dt.isoformat()} -> {end_dt.isoformat()}")
        print(f"[NDVI] Cloud max: {CLOUD_MAX} | max_items: {MAX_ITEMS} | per_tile: {PER_TILE} | fetch_limit: {FETCH_LIMIT}")

        # búsqueda STAC
        catalog = open_pc_catalog()
        geom = mapping(box(minx, miny, maxx, maxy))  # ojo: bbox geom para asegurar cobertura
        items_all = search_items(catalog, geom, bbox, start_dt, end_dt)
        picked = pick_items_balanced(items_all)

        if not picked:
            print("[NDVI] No hay escenas candidatas; no se actualiza.")
            return 0

        width, height = compute_output_shape(minx, miny, maxx, maxy, max_dim=NDVI_MAX_DIM)
        dst_crs = "EPSG:4326"
        dst_transform = from_bounds(minx, miny, maxx, maxy, width, height)

        ndvi_stack = []
        used_items = []

        for it in picked:
            it = sign_item_if_needed(it)
            a = it.assets

            # En PC las bandas son B04/B08 y SCL en mayúsculas
            if "B04" not in a or "B08" not in a:
                if DEBUG_S2:
                    print(f"[NDVI] Skip {it.id}: faltan B04/B08")
                continue

            try:
                red = reproject_to_grid(a["B04"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
                nir = reproject_to_grid(a["B08"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)

                red = red.astype(np.float32)
                nir = nir.astype(np.float32)
                red[red == 0] = np.nan
                nir[nir == 0] = np.nan

                if "SCL" in a:
                    scl = reproject_to_grid(a["SCL"].href, dst_transform, dst_crs, width, height, Resampling.nearest)
                    scl_i = np.nan_to_num(scl, nan=0).astype(np.int32)
                    bad = np.isin(scl_i, list(INVALID_SCL))
                    red[bad] = np.nan
                    nir[bad] = np.nan

                ndvi = compute_ndvi(red, nir)
                ndvi_stack.append(ndvi)
                used_items.append(it)

            except Exception as e:
                print(f"[NDVI] Error leyendo {it.id}: {e}")

        if not ndvi_stack:
            print("[NDVI] No se pudo calcular NDVI (sin datos legibles).")
            return 0

        stack = np.stack(ndvi_stack, axis=0)
        if NDVI_COMPOSITE == "median":
            comp = np.nanmedian(stack, axis=0)
        else:
            comp = np.nanmax(stack, axis=0)

        if not np.any(np.isfinite(comp)):
            print("[NDVI] Composite NDVI vacío (todo NaN).")
            return 0

        # -----------------------------
        # Guardar raster histórico + latest png (bbox completo)
        # -----------------------------
        static_ndvi_dir = Path(app.root_path) / "static" / "ndvi"
        static_ndvi_dir.mkdir(parents=True, exist_ok=True)

        date_tag = now.strftime("%Y%m%d")
        tif_path = static_ndvi_dir / f"ndvi_{date_tag}.tif"
        latest_png = static_ndvi_dir / "ndvi_latest.png"
        meta_json = static_ndvi_dir / f"ndvi_{date_tag}.json"

        # GeoTIFF tmp
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

        final_tif = atomic_replace_with_retry(tmp_tif, str(tif_path))
        print(f"OK: NDVI GeoTIFF -> {final_tif}")

        # PNG tmp
        rgba = ndvi_to_rgba(comp)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png", dir=str(static_ndvi_dir)) as tmp:
            tmp_png = tmp.name
        Image.fromarray(rgba, mode="RGBA").save(tmp_png, format="PNG", optimize=True)

        final_png = atomic_replace_with_retry(tmp_png, str(latest_png))
        print(f"OK: NDVI generado -> {final_png}")

        # meta
        meta = {
            "updated_utc": now.isoformat(),
            "window": [start_dt.isoformat(), end_dt.isoformat()],
            "collection": S2_COLLECTION,
            "items_total_found": len(items_all),
            "items_used": [it.id for it in used_items],
            "bbox": [minx, miny, maxx, maxy],
            "size": [width, height],
            "cloud_max": CLOUD_MAX,
            "per_tile": PER_TILE,
            "composite": NDVI_COMPOSITE,
            "tif": str(final_tif),
            "png": str(final_png),
        }
        meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # -----------------------------
        # Insertar en BBDD: public.imagenes + public.indices_raster
        # -----------------------------
        try:
            # bbox geom (EPSG:4326)
            wkt_bbox = f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))"

            # 1) insertar imagen (cumpliendo CHECK origen)
            sql_img = text("""
                INSERT INTO public.imagenes
                  (origen, fecha_adquisicion, epsg, sensor, resolucion_m, bbox, ruta_archivo)
                VALUES
                  (:origen, :fecha, :epsg, :sensor, :res, ST_GeomFromText(:wkt, 4326), :ruta)
                RETURNING id_imagen
            """)

            sensor_txt = f"Sentinel-2 L2A (Planetary Computer) | composite={NDVI_COMPOSITE} | cloud_max={CLOUD_MAX} | items={len(used_items)}"
            id_imagen = db.session.execute(sql_img, {
                "origen": "satelite",                 # <- cumple imagenes_origen_check
                "fecha": now,
                "epsg": 4326,
                "sensor": sensor_txt,
                "res": 10.0,                          # NDVI con B04/B08 a 10m (aprox)
                "wkt": wkt_bbox,
                "ruta": str(final_tif),
            }).scalar()

            # 2) stats por recinto
            recintos = fetch_recintos_geojson()
            inserted = 0

            with rasterio.open(final_tif) as ds:
                for id_recinto, gj in recintos:
                    geom_rec = shape(json.loads(gj))
                    stats = zonal_stats_for_geom(ds, geom_rec)
                    if not stats:
                        continue

                    # OJO: tu tabla tiene id_parcela con FK raro; lo rellenamos igual que id_recinto para evitar líos.
                    sql_idx = text("""
                        INSERT INTO public.indices_raster
                          (id_imagen, id_recinto, id_parcela, tipo_indice, fecha_calculo, epsg, resolucion_m,
                           valor_medio, valor_min, valor_max, desviacion_std, ruta_raster)
                        VALUES
                          (:id_imagen, :id_recinto, :id_parcela, :tipo, :fecha, :epsg, :res,
                           :mean, :min, :max, :std, :ruta)
                    """)

                    db.session.execute(sql_idx, {
                        "id_imagen": int(id_imagen),
                        "id_recinto": int(id_recinto),
                        "id_parcela": int(id_recinto),
                        "tipo": "NDVI",
                        "fecha": now,
                        "epsg": 4326,
                        "res": 10.0,
                        "mean": stats["mean"],
                        "min": stats["min"],
                        "max": stats["max"],
                        "std": stats["std"],
                        "ruta": str(final_tif),
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