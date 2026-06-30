"""
Generador de Thumbnail NDVI — varias fechas y procesamiento paralelo.

Uso:
  cd src
  python generate_thumbnails.py
  python generate_thumbnails.py --fechas 20260219,20260224,20260301
  python generate_thumbnails.py --fechas 19/02/2026,24/02/2026,01/03/2026 --force
  python generate_thumbnails.py --recintos 12,45,78 --workers 8
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from multiprocessing import shared_memory

import numpy as np
import rasterio
from PIL import Image, ImageDraw
from pyproj import Transformer
from rasterio.windows import Window
from scipy.ndimage import gaussian_filter
from shapely import wkb
from shapely.ops import transform as shapely_transform
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from project_paths import NDVI_COMPOSITE_DIR, PROJECT_ROOT
from webapp.config import Config

# ==================== CONFIGURACIÓN ====================

THUMBNAILS_BASE_DIR = PROJECT_ROOT / "src" / "webapp" / "static" / "thumbnails"

# Fechas por defecto (capturas galería NDVI)
FECHAS_DEFECTO = ("20260219", "20260224", "20260301")

START_FROM_ID = 0
LOG_INTERVAL = 500
MIN_VALID_PIXELS_PERCENT = 5.0

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)

# Estado por proceso hijo (shared memory del raster)
_WORKER: dict = {}


# ==================== FECHAS Y RUTAS ====================

def parse_fecha(s: str) -> str:
    s = s.strip()
    for fmt in ("%Y%m%d", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d %b %Y", "%d %b. %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValueError(f"Fecha no reconocida: {s!r}")


def parse_fechas_list(raw: str | None) -> list[str]:
    if not raw:
        return list(FECHAS_DEFECTO)
    out: list[str] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(parse_fecha(part))
    return out


def resolve_ndvi_tif(fecha_str: str) -> Path | None:
    tif_3857 = NDVI_COMPOSITE_DIR / f"ndvi_pc_{fecha_str}_mosaic_3857.tif"
    if tif_3857.is_file():
        return tif_3857
    tif_utm = NDVI_COMPOSITE_DIR / f"ndvi_pc_{fecha_str}_mosaic_utm.tif"
    if tif_utm.is_file():
        return tif_utm
    return None


def fecha_desde_meta(meta_path: Path, fallback: str) -> str:
    if not meta_path.is_file():
        return fallback
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("ndvi_date_formatted"):
            return meta["ndvi_date_formatted"]
        for key in ("ndvi_date", "updated_utc"):
            if meta.get(key):
                dt = datetime.fromisoformat(meta[key].replace("Z", "+00:00"))
                return dt.strftime("%Y%m%d")
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return fallback


# ==================== NDVI → IMAGEN ====================

def rellenar_ndvi_inteligente(ndvi_array: np.ndarray) -> np.ndarray | None:
    total_pixels = ndvi_array.size
    valid_pixels = np.sum(~np.isnan(ndvi_array))
    valid_percent = (valid_pixels / total_pixels) * 100
    if valid_percent < MIN_VALID_PIXELS_PERCENT:
        return None

    filled = ndvi_array.copy()
    media = np.nanmean(filled)
    nan_mask = np.isnan(filled)
    filled[nan_mask] = media
    if np.any(nan_mask):
        filled = gaussian_filter(filled, sigma=1.0)
    return filled


def ndvi_to_rgba_discrete(ndvi: np.ndarray) -> np.ndarray:
    h, w = ndvi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid = np.isfinite(ndvi)
    if not np.any(valid):
        return rgba

    ranges_colors = [
        (-0.2, 0.0, (165, 0, 38)),
        (0.0, 0.1, (215, 48, 39)),
        (0.1, 0.2, (244, 109, 67)),
        (0.2, 0.3, (253, 174, 97)),
        (0.3, 0.4, (254, 224, 139)),
        (0.4, 0.5, (255, 255, 191)),
        (0.5, 0.6, (217, 239, 139)),
        (0.6, 0.7, (166, 217, 106)),
        (0.7, 0.8, (102, 189, 99)),
        (0.8, 0.9, (26, 152, 80)),
        (0.9, 1.0, (0, 104, 55)),
    ]

    rgba[valid & (ndvi < -0.2)] = [0, 0, 0, 255]
    for vmin, vmax, color in ranges_colors:
        mask = valid & (ndvi >= vmin) & (ndvi < vmax)
        if np.any(mask):
            rgba[mask] = [*color, 255]
    rgba[valid & (ndvi >= 1.0)] = [0, 104, 55, 255]
    rgba[~valid, 3] = 0
    return rgba


def get_polygons_from_geometry(geometria):
    if geometria.geom_type == "Polygon":
        return [geometria]
    if geometria.geom_type == "MultiPolygon":
        return list(geometria.geoms)
    return []


def geo_to_pixel(x: float, y: float, transform) -> tuple[float, float]:
    col = (x - transform.c) / transform.a
    row = (y - transform.f) / transform.e
    return col, row


def extraer_ventana_raster(geometria, raster: dict):
    minx, miny, maxx, maxy = geometria.bounds
    transform = raster["transform"]
    col_start, row_start = ~transform * (minx, maxy)
    col_end, row_end = ~transform * (maxx, miny)

    col_start = max(0, int(col_start))
    row_start = max(0, int(row_start))
    col_end = min(raster["width"], int(col_end) + 1)
    row_end = min(raster["height"], int(row_end) + 1)

    if col_end <= col_start or row_end <= row_start:
        return None, None

    window_data = raster["data"][row_start:row_end, col_start:col_end]
    window_transform = rasterio.windows.transform(
        Window(col_start, row_start, col_end - col_start, row_end - row_start),
        transform,
    )
    return window_data, window_transform


def generar_thumbnail_pil(
    ndvi_data: np.ndarray,
    window_transform,
    geometria,
    output_path: str,
    border_px: int = 2,
) -> float | None:
    """Genera PNG con PIL (mucho más rápido que matplotlib)."""
    ndvi_filled = rellenar_ndvi_inteligente(ndvi_data)
    if ndvi_filled is None:
        return None

    rgba = ndvi_to_rgba_discrete(np.clip(ndvi_filled, -0.2, 1.0))
    h, w = rgba.shape[:2]
    img = Image.fromarray(rgba, "RGBA")

    mask = Image.new("L", (w, h), 0)
    draw_mask = ImageDraw.Draw(mask)
    polygons = get_polygons_from_geometry(geometria)

    for poly in polygons:
        pts = [geo_to_pixel(x, y, window_transform) for x, y in poly.exterior.coords]
        draw_mask.polygon(pts, fill=255)

    r, g, b, a = img.split()
    a = Image.composite(a, Image.new("L", (w, h), 0), mask)
    img = Image.merge("RGBA", (r, g, b, a))

    minx, miny, maxx, maxy = geometria.bounds
    c0, r0 = geo_to_pixel(minx, maxy, window_transform)
    c1, r1 = geo_to_pixel(maxx, miny, window_transform)
    left = int(min(c0, c1))
    top = int(min(r0, r1))
    right = int(max(c0, c1)) + 1
    bottom = int(max(r0, r1)) + 1

    pad = border_px + 1
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(w, right + pad)
    bottom = min(h, bottom + pad)

    cropped = img.crop((left, top, right, bottom))
    draw = ImageDraw.Draw(cropped)

    for poly in polygons:
        pts = [
            (geo_to_pixel(x, y, window_transform)[0] - left,
             geo_to_pixel(x, y, window_transform)[1] - top)
            for x, y in poly.exterior.coords
        ]
        if len(pts) >= 2:
            draw.line(pts + [pts[0]], fill=(0, 0, 0, 255), width=border_px)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cropped.save(output_path, "PNG", optimize=True)

    valid_mask = ~np.isnan(ndvi_data) & np.isfinite(ndvi_data)
    if np.any(valid_mask):
        return float(np.mean(ndvi_data[valid_mask]))
    return None


# ==================== WORKERS ====================

def _worker_init(
    shm_name: str,
    shape: tuple[int, int],
    dtype_str: str,
    transform_vals: tuple,
    crs: int,
    output_dir: str,
    skip_existing: bool,
    geom_srid: int,
):
    shm = shared_memory.SharedMemory(name=shm_name)
    _WORKER["data"] = np.ndarray(shape, dtype=np.dtype(dtype_str), buffer=shm.buf)
    _WORKER["transform"] = rasterio.Affine(*transform_vals)
    _WORKER["crs"] = crs
    _WORKER["width"] = shape[1]
    _WORKER["height"] = shape[0]
    _WORKER["output_dir"] = output_dir
    _WORKER["skip_existing"] = skip_existing
    _WORKER["geom_srid"] = geom_srid
    _WORKER["transformer"] = (
        Transformer.from_crs(f"EPSG:{geom_srid}", f"EPSG:{crs}", always_xy=True)
        if geom_srid != crs
        else None
    )


def _worker_process(item: tuple[int, bytes]) -> str:
    id_recinto, geom_wkb = item
    output_png = os.path.join(_WORKER["output_dir"], f"{id_recinto}.png")

    if _WORKER["skip_existing"] and os.path.exists(output_png):
        return "skipped"

    geometria = wkb.loads(geom_wkb)
    if _WORKER["transformer"] is not None:
        geometria = shapely_transform(_WORKER["transformer"].transform, geometria)

    raster = {
        "data": _WORKER["data"],
        "transform": _WORKER["transform"],
        "crs": _WORKER["crs"],
        "width": _WORKER["width"],
        "height": _WORKER["height"],
    }

    ndvi_data, window_transform = extraer_ventana_raster(geometria, raster)
    if ndvi_data is None:
        return "no_overlap"

    result = generar_thumbnail_pil(ndvi_data, window_transform, geometria, output_png)
    if result is None:
        return "insufficient_data"
    return "success"


def cargar_recintos(recinto_ids: list[int] | None) -> list[tuple[int, bytes]]:
    session = Session()
    try:
        if recinto_ids:
            rows = session.execute(
                text(
                    "SELECT id_recinto, geom FROM recintos "
                    "WHERE id_recinto = ANY(:ids) ORDER BY id_recinto"
                ),
                {"ids": recinto_ids},
            ).fetchall()
        else:
            rows = session.execute(
                text(
                    "SELECT id_recinto, geom FROM recintos "
                    "WHERE id_recinto >= :start ORDER BY id_recinto"
                ),
                {"start": START_FROM_ID},
            ).fetchall()
    finally:
        session.close()

    out: list[tuple[int, bytes]] = []
    for id_recinto, geom in rows:
        if isinstance(geom, memoryview):
            geom = geom.tobytes()
        elif isinstance(geom, str):
            geom = bytes.fromhex(geom)
        out.append((int(id_recinto), bytes(geom)))
    return out


def procesar_fecha(
    fecha_str: str,
    recintos: list[tuple[int, bytes]],
    *,
    skip_existing: bool,
    workers: int,
) -> dict[str, int]:
    tif_path = resolve_ndvi_tif(fecha_str)
    meta_path = NDVI_COMPOSITE_DIR / f"ndvi_pc_{fecha_str}_mosaic.json"

    if tif_path is None:
        print(f"  ✗ Sin raster NDVI para {fecha_str} en {NDVI_COMPOSITE_DIR}")
        return {"error": 1}

    fecha_out = fecha_desde_meta(meta_path, fecha_str)
    output_dir = str(THUMBNAILS_BASE_DIR / fecha_out)
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'─'*60}")
    print(f"  Fecha NDVI: {fecha_out}  ←  {tif_path.name}")
    print(f"  Salida:     {output_dir}")
    print(f"  Workers:    {workers}")

    t0 = time.perf_counter()

    with rasterio.open(tif_path) as src:
        data = src.read(1)
        transform = src.transform
        crs = src.crs.to_epsg()

    shm = shared_memory.SharedMemory(create=True, size=data.nbytes)
    shared = np.ndarray(data.shape, dtype=data.dtype, buffer=shm.buf)
    np.copyto(shared, data)
    del data

    stats = {
        "success": 0,
        "skipped": 0,
        "no_overlap": 0,
        "insufficient_data": 0,
        "error": 0,
    }

    transform_vals = (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)

    try:
        if workers <= 1:
            _worker_init(
                shm.name,
                shared.shape,
                str(shared.dtype),
                transform_vals,
                crs,
                output_dir,
                skip_existing,
                4326,
            )
            for idx, item in enumerate(recintos, 1):
                try:
                    result = _worker_process(item)
                    stats[result] = stats.get(result, 0) + 1
                except Exception as e:
                    print(f"  Error recinto {item[0]}: {e}")
                    stats["error"] += 1
                if idx % LOG_INTERVAL == 0 or idx == len(recintos):
                    _log_progreso(idx, len(recintos), stats)
        else:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_worker_init,
                initargs=(
                    shm.name,
                    shared.shape,
                    str(shared.dtype),
                    transform_vals,
                    crs,
                    output_dir,
                    skip_existing,
                    4326,
                ),
            ) as pool:
                futures = {pool.submit(_worker_process, item): item[0] for item in recintos}
                done = 0
                for fut in as_completed(futures):
                    done += 1
                    rid = futures[fut]
                    try:
                        result = fut.result()
                        stats[result] = stats.get(result, 0) + 1
                    except Exception as e:
                        print(f"  Error recinto {rid}: {e}")
                        stats["error"] += 1
                    if done % LOG_INTERVAL == 0 or done == len(recintos):
                        _log_progreso(done, len(recintos), stats)
    finally:
        shm.close()
        shm.unlink()
        gc.collect()

    elapsed = time.perf_counter() - t0
    print(f"  ✓ {fecha_out} en {elapsed:.1f}s — generados: {stats['success']}, omitidos: {stats['skipped']}")
    return stats


def _log_progreso(done: int, total: int, stats: dict[str, int]) -> None:
    print(
        f"  … {done}/{total} | ok={stats['success']} "
        f"sin_datos={stats['insufficient_data']} "
        f"sin_solape={stats['no_overlap']} "
        f"omitidos={stats['skipped']} err={stats['error']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera thumbnails NDVI por fecha")
    parser.add_argument(
        "--fechas",
        default=",".join(FECHAS_DEFECTO),
        help="Fechas separadas por coma (YYYYMMDD o DD/MM/YYYY). "
        f"Por defecto: {','.join(FECHAS_DEFECTO)}",
    )
    parser.add_argument(
        "--recintos",
        default="",
        help="Solo estos id_recinto (coma). Vacío = todos.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 4) - 1),
        help="Procesos en paralelo (por fecha)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerar aunque el PNG ya exista",
    )
    args = parser.parse_args()

    try:
        fechas = parse_fechas_list(args.fechas)
    except ValueError as e:
        print(f"✗ {e}")
        return 1

    recinto_ids: list[int] | None = None
    if args.recintos.strip():
        recinto_ids = [int(x.strip()) for x in args.recintos.split(",") if x.strip()]

    recintos = cargar_recintos(recinto_ids)
    if not recintos:
        print("✗ No hay recintos que procesar")
        return 1

    print("=" * 70)
    print("GENERADOR DE THUMBNAILS NDVI — MULTI-FECHA + PARALELO (PIL)")
    print("=" * 70)
    print(f"Fechas:   {', '.join(fechas)}")
    print(f"Recintos: {len(recintos)}")
    print(f"Workers:  {args.workers}")
    print(f"Force:    {args.force}")

    total_stats = {
        "success": 0,
        "skipped": 0,
        "no_overlap": 0,
        "insufficient_data": 0,
        "error": 0,
    }

    t_global = time.perf_counter()
    for fecha in fechas:
        stats = procesar_fecha(
            fecha,
            recintos,
            skip_existing=not args.force,
            workers=args.workers,
        )
        for k, v in stats.items():
            total_stats[k] = total_stats.get(k, 0) + v

    print("\n" + "=" * 70)
    print("PROCESO TERMINADO")
    print("=" * 70)
    print(f"Tiempo total: {time.perf_counter() - t_global:.1f}s")
    print(f"Thumbnails generados: {total_stats['success']}")
    print(f"Omitidos (ya existían): {total_stats['skipped']}")
    print(f"Sin datos / sin solape: {total_stats['insufficient_data'] + total_stats['no_overlap']}")
    print(f"Errores: {total_stats['error']}")
    print(f"Carpeta base: {THUMBNAILS_BASE_DIR}")
    return 0 if total_stats["error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
