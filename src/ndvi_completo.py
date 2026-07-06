#!/usr/bin/env python3
"""
NDVI Temporal Composite con Planetary Computer
===============================================
Genera un composite NDVI óptimo usando imágenes de los últimos 2-3 meses.

CORRECCIONES v1.4:
- ✓ Weighted blend entre tiles (elimina bordes visibles)
- ✓ Solo guarda imagen en BBDD, NO procesa índices_raster
- ✓ Agua preservada correctamente (SCL=6)
- ✓ PNG generado desde EPSG:3857 (cuadrado con el mapa)
- ✓ Sistema de rotación simplificado: 1 latest + máximo 2 copias históricas
- ✓ Eliminada lógica de versiones _v2, _v3, etc.

Autor: Sistema GIS Mejorado
Fecha: 2025
"""

import os
import sys
import json
import shutil
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# PROJ/GDAL del conda antes de geopandas/rasterio
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
from gis_runtime_env import setup_gis_runtime_env  # noqa: E402

setup_gis_runtime_env()

import numpy as np
import geopandas as gpd
from shapely.geometry import box, mapping, shape
from scipy import ndimage

from PIL import Image

import math
import rasterio
from rasterio.warp import (
    reproject, Resampling, transform_bounds, transform_geom, calculate_default_transform
)
from rasterio.transform import from_bounds
from rasterio.windows import from_bounds as window_from_bounds
from rasterio.features import geometry_mask

from dotenv import load_dotenv
from sqlalchemy import text
from webapp import create_app, db

# Planetary Computer
from pystac_client import Client
import planetary_computer as pc


print("[NDVI-TEMPORAL] Script de NDVI - COMPOSITE TEMPORAL ÓPTIMO v1.4")
print("="*70)

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

ROI_PATH = os.getenv(
    "ROI_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "processed" / "ROI.gpkg")
)

# VENTANA TEMPORAL: Últimos 120 días (aprox 4 meses)
TEMPORAL_WINDOW_DAYS = int(os.getenv("TEMPORAL_WINDOW_DAYS", "120"))
END_DATE = datetime.now(timezone.utc)
START_DATE = END_DATE - timedelta(days=TEMPORAL_WINDOW_DAYS)

# Parámetros de búsqueda
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "30"))
MAX_ITEMS = 200

# Parámetros de calidad
CLOUD_BUFFER_PIXELS = int(os.getenv("CLOUD_BUFFER_PIXELS", "8"))
MIN_VALID_COVERAGE_PER_IMAGE = 0.01

# Parámetros de procesamiento
NDVI_RES_M = float(os.getenv("NDVI_RES_M", "10"))
NDVI_MAX_DIM = int(os.getenv("NDVI_MAX_DIM", "12000"))
DEBUG_MODE = os.getenv("DEBUG_MODE", "1") == "1"

# Clasificación SCL
INVALID_SCL = {0, 1, 3, 8, 9, 10, 11}  # SIN agua (6)
SHADOW_SCL = {2, 3}
WATER_SCL = {6}

# Pesos de calidad por clase SCL
QUALITY_WEIGHTS = {
    4: 1.00,   # Vegetación - MÁXIMA CALIDAD
    5: 0.95,   # Suelo desnudo
    6: 0.80,   # Agua - VÁLIDO pero menor prioridad
    7: 0.50,   # Nubes de baja probabilidad
    2: 0.30,   # Sombras oscuras
    11: 0.20,  # Nieve/hielo
}


# ============================================================================
# PLANETARY COMPUTER - BÚSQUEDA TEMPORAL
# ============================================================================

def search_planetary_computer_temporal(bbox, start_date, end_date, cloud_max):
    """Buscar TODAS las imágenes Sentinel-2 L2A en la ventana temporal."""
    try:
        print(f"[SEARCH] Conectando con Planetary Computer...")
        print(f"[SEARCH] Período: {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
        
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace
        )
        
        date_range = f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
        
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=date_range,
            limit=MAX_ITEMS
        )
        
        items = list(search.items())
        print(f"[SEARCH] ✓ Productos encontrados: {len(items)}")
        
        if not items:
            return {}
        
        # Agrupar por fecha y filtrar por nubes
        por_fecha = defaultdict(list)
        
        for item in items:
            item_date = datetime.fromisoformat(item.properties['datetime'].replace('Z', '+00:00'))
            clouds = item.properties.get('eo:cloud_cover', -1)
            
            if clouds <= cloud_max:
                por_fecha[item_date.date()].append({
                    'item': item,
                    'clouds': clouds,
                    'date': item_date
                })
        
        total_tiles = sum(len(items) for items in por_fecha.values())
        print(f"[SEARCH] ✓ Fechas únicas: {len(por_fecha)}")
        print(f"[SEARCH] ✓ Total tiles: {total_tiles}")
        
        return por_fecha
        
    except Exception as e:
        print(f"[SEARCH] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return {}


# ============================================================================
# UTILIDADES
# ============================================================================

def reproject_to_grid(data_array, src_transform, src_crs, dst_transform, dst_crs, 
                     width, height, resampling, src_nodata=None, dst_dtype=np.float32):
    """Reproyectar array a rejilla destino"""
    if np.issubdtype(dst_dtype, np.floating):
        dst_nodata = np.nan
    else:
        dst_nodata = 0
    
    dst = np.full((height, width), dst_nodata, dtype=dst_dtype)
    
    reproject(
        source=data_array,
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=resampling,
        src_nodata=src_nodata,
        dst_nodata=dst_nodata,
    )
    return dst


def apply_cloud_buffer(cloud_mask, buffer_pixels=8):
    """Expande máscara de nubes"""
    if buffer_pixels <= 0:
        return cloud_mask
    
    structure = ndimage.generate_binary_structure(2, 2)
    buffered = ndimage.binary_dilation(cloud_mask, structure=structure, iterations=buffer_pixels)
    return buffered


def enhanced_cloud_mask_water_aware(scl):
    """Máscara de nubes mejorada que PRESERVA agua"""
    scl_int = np.nan_to_num(scl, nan=0).astype(np.int32)
    invalid = np.isin(scl_int, list(INVALID_SCL))
    clouds_only = np.isin(scl_int, [8, 9, 10])
    
    if CLOUD_BUFFER_PIXELS > 0:
        clouds_buffered = apply_cloud_buffer(clouds_only, CLOUD_BUFFER_PIXELS)
        invalid = invalid | clouds_buffered
    
    return invalid


def compute_pixel_quality_weights(scl):
    """Calcula pesos de calidad para composite"""
    scl_int = np.nan_to_num(scl, nan=0).astype(np.int32)
    weights = np.zeros_like(scl, dtype=np.float32)
    
    for scl_class, weight in QUALITY_WEIGHTS.items():
        weights[scl_int == scl_class] = weight
    
    return weights


def compute_ndvi(red, nir):
    """Calcular NDVI"""
    den = nir + red
    return np.where(den == 0, np.nan, (nir - red) / den)


def ndvi_to_rgba(ndvi):
    """Convertir NDVI a imagen RGBA"""
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


def warp_tif_to_3857(src_tif: str, dst_tif: str):
    """Reproyectar a EPSG:3857"""
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


def compute_grid_from_bbox_meters(bbox4326, dst_crs, res_m, max_dim=None):
    """Calcular grid de salida"""
    minx, miny, maxx, maxy = bbox4326
    b = transform_bounds("EPSG:4326", dst_crs, minx, miny, maxx, maxy, densify_pts=21)
    minx_p, miny_p, maxx_p, maxy_p = b

    span_x = maxx_p - minx_p
    span_y = maxy_p - miny_p

    width = int(math.ceil(span_x / res_m))
    height = int(math.ceil(span_y / res_m))

    if max_dim is not None:
        scale = max(width / max_dim, height / max_dim, 1.0)
        width = int(math.ceil(width / scale))
        height = int(math.ceil(height / scale))

    dst_transform = from_bounds(minx_p, miny_p, maxx_p, maxy_p, width, height)
    return width, height, dst_transform, (minx_p, miny_p, maxx_p, maxy_p)


def get_roi_bbox_from_gpkg():
    """Leer ROI desde GeoPackage"""
    roi_path = Path(ROI_PATH)
    if not roi_path.exists():
        raise FileNotFoundError(f"ROI no existe: {roi_path.resolve()}")

    roi = gpd.read_file(roi_path).to_crs(4326)
    minx, miny, maxx, maxy = roi.total_bounds
    bbox = (float(minx), float(miny), float(maxx), float(maxy))
    print(f"[ROI] BBox: {bbox}")
    return bbox


# ============================================================================
# LECTURA DE BANDAS
# ============================================================================

def read_band_window_cog(item, band_key, bbox_4326, dst_transform, dst_crs, width, height):
    """Lee una banda de Sentinel-2 usando COG"""
    
    asset = item.assets.get(band_key)
    
    if not asset:
        variants = {
            'B04': ['red', 'B04', 'b04'],
            'B08': ['nir', 'B08', 'b08', 'nir08'],
            'SCL': ['scl', 'SCL'],
        }
        
        for variant in variants.get(band_key, []):
            if variant in item.assets:
                asset = item.assets[variant]
                break
    
    if not asset:
        return None
    
    href = asset.href
    
    try:
        with rasterio.open(href) as src:
            tile_bounds = src.bounds
            
            src_bbox = transform_bounds(
                "EPSG:4326", src.crs,
                *bbox_4326, densify_pts=21
            )
            
            # Intersección real
            intersection_bbox = (
                max(tile_bounds.left, src_bbox[0]),
                max(tile_bounds.bottom, src_bbox[1]),
                min(tile_bounds.right, src_bbox[2]),
                min(tile_bounds.top, src_bbox[3])
            )
            
            if intersection_bbox[0] >= intersection_bbox[2] or intersection_bbox[1] >= intersection_bbox[3]:
                return None
            
            window = window_from_bounds(*intersection_bbox, transform=src.transform)
            data = src.read(1, window=window)
            src_transform_win = src.window_transform(window)
            src_crs = src.crs
            src_nodata = src.nodata
        
        if band_key == 'SCL':
            resampling_method = Resampling.nearest
            dtype = np.int16
        else:
            resampling_method = Resampling.bilinear
            dtype = np.float32
        
        reprojected = reproject_to_grid(
            data, src_transform_win, src_crs,
            dst_transform, dst_crs, width, height,
            resampling_method,
            src_nodata=src_nodata,
            dst_dtype=dtype
        )
        
        return reprojected
        
    except Exception as e:
        if DEBUG_MODE:
            print(f"[BAND] ✗ Error leyendo {band_key}: {e}")
        return None


# ============================================================================
# PROCESAMIENTO TEMPORAL CON WEIGHTED BLEND
# ============================================================================

def process_item_to_ndvi_temporal(item, bbox_4326, dst_transform, dst_crs, width, height):
    """Procesar STAC Item a NDVI con máscaras de calidad"""
    
    red = read_band_window_cog(item, 'B04', bbox_4326, dst_transform, dst_crs, width, height)
    nir = read_band_window_cog(item, 'B08', bbox_4326, dst_transform, dst_crs, width, height)
    
    if red is None or nir is None:
        return None, None, None
    
    red = red.astype(np.float32)
    nir = nir.astype(np.float32)
    
    # Limpiar valores inválidos
    red[red == 0] = np.nan
    nir[nir == 0] = np.nan
    red[(red < 0) | (red > 10000)] = np.nan
    nir[(nir < 0) | (nir > 10000)] = np.nan
    
    # Convertir a reflectancia
    red = red / 10000.0
    nir = nir / 10000.0
    
    # Leer SCL
    scl = read_band_window_cog(item, 'SCL', bbox_4326, dst_transform, dst_crs, width, height)
    
    quality_weights = np.ones((height, width), dtype=np.float32)
    
    if scl is not None:
        invalid = enhanced_cloud_mask_water_aware(scl)
        red[invalid] = np.nan
        nir[invalid] = np.nan
        quality_weights = compute_pixel_quality_weights(scl)
    
    ndvi = compute_ndvi(red, nir)
    valid_mask = np.isfinite(ndvi)
    
    return ndvi, quality_weights, valid_mask


def create_temporal_weighted_composite(items_por_fecha, bbox_4326, dst_transform, dst_crs, width, height):
    """
    Crear composite temporal usando WEIGHTED AVERAGE.
    
    SOLUCIÓN AL PROBLEMA DE BORDES:
    - En lugar de "winner takes all", hace promedio ponderado
    - Los tiles se mezclan suavemente en las zonas de solapamiento
    - Elimina completamente los bordes visibles entre tiles
    """
    print(f"\n{'='*70}")
    print(f"CREANDO COMPOSITE - WEIGHTED AVERAGE BLEND")
    print(f"{'='*70}")
    print(f"Fechas disponibles: {len(items_por_fecha)}")
    
    # Arrays acumuladores
    ndvi_sum = np.zeros((height, width), dtype=np.float32)
    weight_sum = np.zeros((height, width), dtype=np.float32)
    pixel_count = np.zeros((height, width), dtype=np.int16)
    
    fechas_ordenadas = sorted(items_por_fecha.keys())
    total_tiles = sum(len(items) for items in items_por_fecha.values())
    tiles_procesados = 0
    tiles_validos = 0
    
    print(f"\n[COMPOSITE] Procesando {total_tiles} tiles...", flush=True)
    
    import gc

    for fecha in fechas_ordenadas:
        for img_info in items_por_fecha[fecha]:
            item = img_info['item']
            tiles_procesados += 1
            
            if tiles_procesados % 5 == 0 or tiles_procesados == total_tiles:
                print(f"[COMPOSITE] Progreso: {tiles_procesados}/{total_tiles}...", flush=True)
            
            try:
                ndvi, quality_weights, valid_mask = process_item_to_ndvi_temporal(
                    item, bbox_4326, dst_transform, dst_crs, width, height
                )
            except Exception as exc:
                print(f"[COMPOSITE] [AVISO] Tile {tiles_procesados} omitido: {exc}", flush=True)
                continue
            
            if ndvi is None or not np.any(valid_mask):
                del ndvi, quality_weights, valid_mask
                continue
            
            tiles_validos += 1
            
            # CLAVE: Weighted average en lugar de "best pixel"
            ndvi_safe = np.nan_to_num(ndvi, nan=0.0)
            weights = quality_weights.copy()
            weights[~valid_mask] = 0.0
            
            # Acumular
            ndvi_sum += ndvi_safe * weights
            weight_sum += weights
            pixel_count[valid_mask] += 1

            del ndvi, quality_weights, valid_mask, ndvi_safe, weights
            if tiles_procesados % 3 == 0:
                gc.collect()
    
    print(f"\n[COMPOSITE] Tiles procesados: {tiles_procesados}", flush=True)
    print(f"[COMPOSITE] Tiles válidos: {tiles_validos}", flush=True)
    
    # Calcular composite final
    composite = np.where(weight_sum > 0, ndvi_sum / weight_sum, np.nan)
    
    valid_composite = composite[np.isfinite(composite)]
    valid_frac = len(valid_composite) / composite.size if composite.size > 0 else 0
    
    print(f"\n[COMPOSITE] ✓ Composite completado")
    print(f"[COMPOSITE] Cobertura: {valid_frac*100:.1f}%")
    print(f"[COMPOSITE] Píxeles válidos: {len(valid_composite):,}")
    
    if len(valid_composite) > 0:
        print(f"[COMPOSITE] NDVI - min: {valid_composite.min():.3f}, max: {valid_composite.max():.3f}, mean: {valid_composite.mean():.3f}")
    
    avg_obs = np.mean(pixel_count[pixel_count > 0]) if np.any(pixel_count > 0) else 0
    max_obs = np.max(pixel_count)
    print(f"[COMPOSITE] Observaciones/píxel - promedio: {avg_obs:.1f}, máximo: {max_obs}")
    
    return composite, pixel_count


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

def clear_ndvi_latest_outputs(ndvi_dir: Path) -> int:
    """Elimina ndvi_latest.* (p. ej. copiados de otra instancia o ejecución fallida)."""
    removed = 0
    for fname in (
        "ndvi_latest_utm.tif",
        "ndvi_latest_3857.tif",
        "ndvi_latest.png",
        "ndvi_latest.json",
    ):
        p = ndvi_dir / fname
        if p.exists():
            try:
                p.unlink()
                removed += 1
                print(f"[INIT] Eliminado residual: {fname}", flush=True)
            except OSError as e:
                print(f"[INIT] [AVISO] No se pudo borrar {fname}: {e}", flush=True)
    return removed


def _old_latest_date_suffix(ndvi_dir: Path) -> str | None:
    latest_json = ndvi_dir / "ndvi_latest.json"
    if not latest_json.is_file():
        return None
    try:
        meta = json.loads(latest_json.read_text(encoding="utf-8"))
        ts = meta.get("generated_utc", "")
        if ts:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%Y%m%d")
    except Exception:
        pass
    return datetime.fromtimestamp(latest_json.stat().st_mtime).strftime("%Y%m%d")


def _archive_previous_latest(ndvi_dir: Path, old_date_suffix: str) -> None:
    """Copia latest → histórico (sin renombrar; evita WinError 5 si hay bloqueo)."""
    pairs = [
        ("ndvi_latest_utm.tif", f"ndvi_{old_date_suffix}_utm.tif"),
        ("ndvi_latest_3857.tif", f"ndvi_{old_date_suffix}_3857.tif"),
        ("ndvi_latest.png", f"ndvi_{old_date_suffix}.png"),
        ("ndvi_latest.json", f"ndvi_{old_date_suffix}.json"),
    ]
    for src_name, dst_name in pairs:
        src = ndvi_dir / src_name
        dst = ndvi_dir / dst_name
        if not src.is_file() or dst.is_file():
            continue
        try:
            shutil.copy2(src, dst)
            print(f"[ARCHIVO] Copia histórica: {dst_name}", flush=True)
        except OSError as e:
            print(f"[ARCHIVO] [AVISO] {src_name}: {e}", flush=True)


def _publish_latest_files(ndvi_dir: Path, dated: dict[str, Path]) -> bool:
    """Publica ndvi_latest.* copiando desde los archivos fechados (reintentos Windows)."""
    mapping = {
        "utm": "ndvi_latest_utm.tif",
        "3857": "ndvi_latest_3857.tif",
        "png": "ndvi_latest.png",
        "json": "ndvi_latest.json",
    }
    ok_all = True
    for key, latest_name in mapping.items():
        src = dated[key]
        dst = ndvi_dir / latest_name
        published = False
        for attempt in range(6):
            try:
                shutil.copy2(src, dst)
                published = True
                print(f"[PUBLICAR] {src.name} → {latest_name}", flush=True)
                break
            except OSError as e:
                if attempt < 5:
                    print(f"[PUBLICAR] Reintento {attempt + 1}/5 ({latest_name})...", flush=True)
                    time.sleep(2)
                else:
                    print(f"[PUBLICAR] [AVISO] Sin acceso a {latest_name}: {e}", flush=True)
                    ok_all = False
        if not published:
            ok_all = False
    return ok_all


def main():
    app = create_app()
    
    with app.app_context():
        ndvi_dir = Path(__file__).resolve().parents[1] / "data" / "raw" / "ndvi_composite"
        ndvi_dir.mkdir(parents=True, exist_ok=True)

        if os.getenv("NDVI_CLEAR_LATEST", "").strip() in ("1", "true", "yes"):
            n = clear_ndvi_latest_outputs(ndvi_dir)
            if n:
                print(f"[INIT] Limpieza previa: {n} archivo(s) ndvi_latest.*", flush=True)

        print(f"\n{'='*70}")
        print("CONFIGURACIÓN")
        print(f"{'='*70}")
        print(f"Fuente: Planetary Computer")
        print(f"Modo: TEMPORAL WEIGHTED COMPOSITE")
        print(f"Período: {START_DATE.strftime('%Y-%m-%d')} → {END_DATE.strftime('%Y-%m-%d')}")
        print(f"Duración: {TEMPORAL_WINDOW_DAYS} días")
        print(f"Buffer nubes: {CLOUD_BUFFER_PIXELS}px (~{CLOUD_BUFFER_PIXELS*10}m)")
        print(f"Resolución: {NDVI_RES_M}m/píxel")
        
        # ROI
        bbox = get_roi_bbox_from_gpkg()
        
        # Buscar imágenes
        items_por_fecha = search_planetary_computer_temporal(
            bbox, START_DATE, END_DATE, CLOUD_MAX
        )
        
        if not items_por_fecha:
            print("\n[ERROR] No se encontraron imágenes")
            return 1
        
        total_items = sum(len(items) for items in items_por_fecha.values())
        print(f"\n{'='*70}")
        print(f"IMÁGENES: {len(items_por_fecha)} fechas, {total_items} tiles")
        print(f"{'='*70}")
        
        # Grid
        dst_crs = "EPSG:25830"
        width, height, dst_transform, dst_bounds_proj = compute_grid_from_bbox_meters(
            bbox, dst_crs, NDVI_RES_M, NDVI_MAX_DIM
        )
        
        print(f"\n[GRID] {width} x {height} píxeles @ {NDVI_RES_M}m - {dst_crs}")
        
        # Crear composite
        composite, pixel_count = create_temporal_weighted_composite(
            items_por_fecha, bbox, dst_transform, dst_crs, width, height
        )
        
        if composite is None or not np.any(np.isfinite(composite)):
            print(f"\n[ERROR] No se pudo crear el composite")
            return 1
        
        # Estadísticas
        valid_ndvi = composite[np.isfinite(composite)]
        
        print(f"\n{'='*70}")
        print("ESTADÍSTICAS FINALES")
        print(f"{'='*70}")
        print(f"  Píxeles válidos: {len(valid_ndvi):,}")
        print(f"  Cobertura:       {100*len(valid_ndvi)/composite.size:.1f}%")
        print(f"  NDVI mínimo:     {valid_ndvi.min():.3f}")
        print(f"  NDVI máximo:     {valid_ndvi.max():.3f}")
        print(f"  NDVI promedio:   {valid_ndvi.mean():.3f}")
        print(f"  NDVI mediana:    {np.median(valid_ndvi):.3f}")
        
        # Directorio de salida
        ndvi_dir.mkdir(parents=True, exist_ok=True)
        
        fecha_str = END_DATE.strftime("%Y%m%d")
        date_display = f"{START_DATE.strftime('%Y-%m-%d')} a {END_DATE.strftime('%Y-%m-%d')}"

        old_suffix = _old_latest_date_suffix(ndvi_dir)
        if old_suffix and old_suffix != fecha_str:
            _archive_previous_latest(ndvi_dir, old_suffix)

        tif_dated = ndvi_dir / f"ndvi_{fecha_str}_utm.tif"
        tif_3857_dated = ndvi_dir / f"ndvi_{fecha_str}_3857.tif"
        png_dated = ndvi_dir / f"ndvi_{fecha_str}.png"
        meta_dated = ndvi_dir / f"ndvi_{fecha_str}.json"

        print(f"\n{'='*70}")
        print("GUARDANDO ARCHIVOS")
        print(f"{'='*70}")
        print(f"[OUTPUT] Generación fechada: {fecha_str}")

        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": "float32",
            "crs": dst_crs,
            "transform": dst_transform,
            "nodata": np.nan,
            "compress": "deflate",
        }

        with rasterio.open(str(tif_dated), "w", **profile) as dst:
            dst.write(composite.astype(np.float32), 1)
        print(f"[OUTPUT] ✓ GeoTIFF UTM -> {tif_dated.name}")

        warp_tif_to_3857(str(tif_dated), str(tif_3857_dated))
        print(f"[OUTPUT] ✓ GeoTIFF 3857 -> {tif_3857_dated.name}")

        print(f"[OUTPUT] Generando PNG desde EPSG:3857...")
        with rasterio.open(str(tif_3857_dated)) as src_3857:
            composite_3857 = src_3857.read(1)

        rgba = ndvi_to_rgba(composite_3857)
        Image.fromarray(rgba, mode="RGBA").save(str(png_dated), format="PNG", optimize=True)
        print(f"[OUTPUT] ✓ PNG (EPSG:3857) -> {png_dated.name}")

        with rasterio.open(str(tif_3857_dated)) as ds:
            b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
            minx2, miny2, maxx2, maxy2 = map(float, b)

        metadata = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "temporal_range": {
                "start": START_DATE.isoformat(),
                "end": END_DATE.isoformat(),
                "days": TEMPORAL_WINDOW_DAYS,
            },
            "date_display": date_display,
            "source": "Planetary Computer",
            "processing": {
                "version": "Weighted Blend Composite v1.4",
                "method": "weighted_average",
                "blend_type": "smooth_transitions",
                "dates_used": len(items_por_fecha),
                "total_tiles": total_items,
                "cloud_buffer_pixels": CLOUD_BUFFER_PIXELS,
                "water_preserved": True,
            },
            "bbox_4326": [minx2, miny2, maxx2, maxy2],
            "bounds_leaflet": [[miny2, minx2], [maxy2, maxx2]],
            "grid_size": [width, height],
            "resolution_m": NDVI_RES_M,
            "crs": dst_crs,
            "statistics": {
                "min": float(valid_ndvi.min()),
                "max": float(valid_ndvi.max()),
                "mean": float(valid_ndvi.mean()),
                "median": float(np.median(valid_ndvi)),
                "std": float(valid_ndvi.std()),
                "valid_pixels": int(len(valid_ndvi)),
                "coverage_pct": float(100 * len(valid_ndvi) / composite.size),
            },
            "files": {
                "utm_tif": tif_dated.name,
                "epsg3857_tif": tif_3857_dated.name,
                "png": png_dated.name,
                "metadata": meta_dated.name,
                "dated_utm_tif": tif_dated.name,
                "dated_3857_tif": tif_3857_dated.name,
                "dated_png": png_dated.name,
                "latest_utm_tif": "ndvi_latest_utm.tif",
                "latest_3857_tif": "ndvi_latest_3857.tif",
                "latest_png": "ndvi_latest.png",
            },
        }

        meta_dated.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OUTPUT] ✓ Metadata -> {meta_dated.name}")

        dated_files = {
            "utm": tif_dated,
            "3857": tif_3857_dated,
            "png": png_dated,
            "json": meta_dated,
        }
        if not _publish_latest_files(ndvi_dir, dated_files):
            print(
                "[AVISO] ndvi_latest.* bloqueado (¿servicio GIS en marcha?). "
                "Para el servicio NSSM y vuelve a ejecutar, o usa los archivos fechados.",
                flush=True,
            )

        tif_path = tif_dated
        meta_path = meta_dated
        # ========================================================================
        # GUARDAR SOLO IMAGEN EN BBDD (NO índices_raster)
        # ========================================================================
        print(f"\n{'='*70}")
        print("GUARDANDO IMAGEN EN BASE DE DATOS")
        print(f"{'='*70}")
        
        try:
            sql_img = text("""
                INSERT INTO public.imagenes
                  (origen, fecha_adquisicion, epsg, sensor, resolucion_m, bbox, ruta_archivo)
                VALUES
                  (:origen, :fecha, :epsg, :sensor, :res, 
                   ST_MakeEnvelope(:minx,:miny,:maxx,:maxy,4326), :ruta)
                RETURNING id_imagen
            """)
            
            ruta_rel = str(Path("data") / "raw" / "ndvi_composite" / tif_path.name)
            sensor_desc = f"S2 L2A Temporal Composite ({len(items_por_fecha)} dates, {total_items} tiles)"
            
            id_imagen = db.session.execute(sql_img, {
                "origen": "satelite",
                "fecha": END_DATE.date(),
                "epsg": int(dst_crs.split(':')[1]),
                "sensor": sensor_desc,
                "res": float(NDVI_RES_M),
                "minx": minx2, "miny": miny2, "maxx": maxx2, "maxy": maxy2,
                "ruta": ruta_rel,
            }).scalar()
            
            db.session.commit()
            
            print(f"[BBDD] ✓ Imagen guardada - ID: {id_imagen}")
            print(f"[BBDD] ℹ  NO se procesaron índices_raster (solo imagen)")
        
        except Exception as e:
            db.session.rollback()
            print(f"[BBDD] ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"\n{'='*70}")
        print("✓ PROCESO COMPLETADO")
        print(f"{'='*70}")
        print(f"✓ Composite temporal creado")
        print(f"✓ Método: Weighted average blend (sin bordes)")
        print(f"✓ Período: {TEMPORAL_WINDOW_DAYS} días")
        print(f"✓ Fechas usadas: {len(items_por_fecha)}")
        print(f"✓ Cobertura: {100*len(valid_ndvi)/composite.size:.1f}%")
        
        # Mostrar ruta de forma segura (absoluta o relativa al proyecto)
        try:
            project_root = Path(__file__).resolve().parents[1]
            display_path = ndvi_dir.relative_to(project_root)
        except ValueError:
            display_path = ndvi_dir
        
        print(f"\n📁 ARCHIVOS GUARDADOS EN: {display_path}")
        print(f"   ├── {tif_dated.name}          (GeoTIFF UTM)")
        print(f"   ├── {tif_3857_dated.name}     (GeoTIFF Web Mercator)")
        print(f"   ├── {png_dated.name}          (Visualización)")
        print(f"   └── {meta_dated.name}         (Metadata)")
        print(f"   (+ copia a ndvi_latest.* si no hay bloqueo de archivos)")
        
        # Mostrar archivos históricos si existen
        historical_files = sorted([f for f in ndvi_dir.glob("ndvi_*.tif") if "latest" not in f.name])
        if historical_files:
            print(f"\n📚 ARCHIVOS HISTÓRICOS ({len(historical_files)//2} versiones):")
            timestamps = sorted(set(
                f.stem.split('_')[1]
                for f in historical_files
                if '_' in f.stem and len(f.stem.split('_')) >= 2
            ))
            for ts in timestamps[-3:]:  # Mostrar últimas 3
                print(f"   └── ndvi_{ts}_*.tif")
        
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        raise SystemExit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[INTERRUPT] Cancelado")
        raise SystemExit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise SystemExit(1)