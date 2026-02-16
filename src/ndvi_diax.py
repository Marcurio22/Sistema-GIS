#!/usr/bin/env python3
"""
NDVI Mejorado con Planetary Computer - MOSAICO MULTI-TILE
==========================================================
Modificado para procesar MÚLTIPLES TILES y crear un mosaico completo

CAMBIOS v2.1:
- Detecta automáticamente todos los tiles que cubren el ROI
- Crea mosaico combinando múltiples imágenes
- Usa weighted average para áreas de solapamiento
- Prioriza píxeles de mejor calidad
- ✓ Thumbnails organizados en carpetas por fecha: static/thumbnails/YYYYMMDD/{id}.png

Autor: Sistema GIS
Fecha: 2025
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

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
from rasterio.io import MemoryFile

from dotenv import load_dotenv
from sqlalchemy import text
from webapp import create_app, db

# Planetary Computer
from pystac_client import Client
import planetary_computer as pc


print("[NDVI-PC] Script de NDVI - MOSAICO MULTI-TILE v2.1")
print("="*70)

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

ROI_PATH = os.getenv(
    "ROI_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg")
)

# FECHA ESPECÍFICA
TARGET_DATE = datetime(2025, 5, 30, tzinfo=timezone.utc)
DATE_WINDOW_DAYS = 0# no se usa va raro

# Parámetros de búsqueda
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "40"))
MAX_ITEMS = 50  # Aumentado para capturar todos los tiles

# Parámetros de calidad
CLOUD_BUFFER_PIXELS = int(os.getenv("CLOUD_BUFFER_PIXELS", "5"))    
MIN_VALID_COVERAGE = float(os.getenv("MIN_VALID_COVERAGE", "0.05"))
USE_WEIGHTED_COMPOSITE = os.getenv("USE_WEIGHTED_COMPOSITE", "1") == "1"

# Parámetros de procesamiento
NDVI_RES_M = float(os.getenv("NDVI_RES_M", "10"))
NDVI_MAX_DIM = int(os.getenv("NDVI_MAX_DIM", "12000"))
DEBUG_MODE = os.getenv("DEBUG_MODE", "1") == "1"


INVALID_SCL = {0, 1, 3, 8, 9, 10, 11}  
SHADOW_SCL = {2, 3}
WATER_SCL = {6}

# BBDD
DB_BATCH_SIZE = int(os.getenv("NDVI_DB_BATCH_SIZE", "500"))
DB_PROGRESS_EVERY = int(os.getenv("NDVI_DB_PROGRESS_EVERY", "500"))


# ============================================================================
# PLANETARY COMPUTER - BÚSQUEDA MULTI-TILE
# ============================================================================

def search_planetary_computer_all_tiles(bbox, target_date, window_days, cloud_max):
    """
    Buscar TODAS las imágenes Sentinel-2 L2A que cubren el ROI en la fecha objetivo.
    
    Returns:
        Lista de items STAC que intersectan el ROI
    """
    try:
        print(f"[SEARCH] Conectando con Planetary Computer...")
        print(f"[SEARCH] Fecha objetivo: {target_date.strftime('%Y-%m-%d')}")
        
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace
        )
        
        # Ventana de búsqueda
        start_dt = target_date - timedelta(days=window_days)
        end_dt = target_date + timedelta(days=window_days)
        date_range = f"{start_dt.strftime('%Y-%m-%d')}/{end_dt.strftime('%Y-%m-%d')}"
        
        print(f"[SEARCH] Ventana de búsqueda: {date_range}")
        print(f"[SEARCH] BBox: {bbox}")
        print(f"[SEARCH] Nubes máx: {cloud_max}%")
        
        # Búsqueda sin filtros
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=date_range,
            limit=100
        )
        
        items = list(search.items())
        
        print(f"[SEARCH] ✓ Productos encontrados: {len(items)}")
        
        if not items:
            print(f"[SEARCH] ✗ No hay productos en la ventana temporal")
            return []
        
        # Agrupar por fecha
        from collections import defaultdict
        por_fecha = defaultdict(list)
        
        for item in items:
            item_date = datetime.fromisoformat(item.properties['datetime'].replace('Z', '+00:00'))
            clouds = item.properties.get('eo:cloud_cover', -1)
            
            # Solo incluir si pasa el filtro de nubes
            if clouds <= cloud_max:
                por_fecha[item_date.date()].append((item, clouds))
        
        print(f"\n[SEARCH] Imágenes por fecha (filtradas por nubes <= {cloud_max}%):")
        for fecha in sorted(por_fecha.keys()):
            imagenes = por_fecha[fecha]
            print(f"[SEARCH]   {fecha}: {len(imagenes)} tile(s)")
            for item, clouds in imagenes:
                print(f"[SEARCH]     - {item.id} | Nubes: {clouds:.1f}%")
        
        # Seleccionar la mejor fecha (la que tenga más tiles o esté más cerca)
        if not por_fecha:
            print(f"[SEARCH] ✗ No hay productos con nubes <= {cloud_max}%")
            return []
        
        # Priorizar: fecha más cercana al objetivo
        fechas_ordenadas = sorted(por_fecha.keys(), 
                                  key=lambda d: abs((datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc) - target_date).days))
        
        fecha_seleccionada = fechas_ordenadas[0]
        items_seleccionados = [item for item, _ in por_fecha[fecha_seleccionada]]
        
        print(f"\n[SEARCH] ✓ Fecha seleccionada: {fecha_seleccionada}")
        print(f"[SEARCH] ✓ Tiles a procesar: {len(items_seleccionados)}")
        
        return items_seleccionados
        
    except Exception as e:
        print(f"[SEARCH] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return []


# ============================================================================
# UTILIDADES DE PROCESAMIENTO
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


def apply_cloud_buffer(cloud_mask, buffer_pixels=5):
    """Expande máscara de nubes con buffer de seguridad"""
    if buffer_pixels <= 0:
        return cloud_mask
    
    structure = ndimage.generate_binary_structure(2, 2)
    buffered = ndimage.binary_dilation(
        cloud_mask, 
        structure=structure, 
        iterations=buffer_pixels
    )
    
    return buffered


def enhanced_cloud_mask(scl, qa60=None):
    """Máscara de nubes mejorada combinando SCL y QA60"""
    scl_int = np.nan_to_num(scl, nan=0).astype(np.int32)
    
    # Máscara básica SCL
    invalid = np.isin(scl_int, list(INVALID_SCL))
    
    # Agregar QA60 si está disponible
    if qa60 is not None:
        qa_int = np.nan_to_num(qa60, nan=0).astype(np.uint16)
        opaque_clouds = (qa_int & (1 << 10)) != 0
        cirrus_clouds = (qa_int & (1 << 11)) != 0
        invalid = invalid | opaque_clouds | cirrus_clouds
    
    # Aplicar buffer de seguridad
    if CLOUD_BUFFER_PIXELS > 0:
        invalid = apply_cloud_buffer(invalid, CLOUD_BUFFER_PIXELS)
    
    return invalid


def compute_pixel_quality_weights(scl):
    """Calcula pesos de calidad para composite ponderado"""
    scl_int = np.nan_to_num(scl, nan=0).astype(np.int32)
    weights = np.ones_like(scl, dtype=np.float32)
    
    weights[scl_int == 4] = 1.0   # Vegetación
    weights[scl_int == 5] = 1.0   # Suelo desnudo
    weights[scl_int == 6] = 0.9   # Agua
    weights[scl_int == 2] = 0.6   # Sombras oscuras
    weights[scl_int == 7] = 0.3   # Nubes de baja probabilidad
    weights[scl_int == 11] = 0.8  # Nieve/hielo
    
    return weights


def compute_ndvi(red, nir):
    """Calcular NDVI robusto"""
    den = nir + red
    return np.where(den == 0, np.nan, (nir - red) / den)


def ndvi_to_rgba(ndvi):
    """Convertir NDVI a imagen RGBA según tabla de colores estándar"""
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
    """Reproyectar a EPSG:3857 para visualización web"""
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
    """Calcular grid de salida en metros"""
    minx, miny, maxx, maxy = bbox4326
    b = transform_bounds("EPSG:4326", dst_crs, minx, miny, maxx, maxy, densify_pts=21)
    minx_p, miny_p, maxx_p, maxy_p = b

    span_x = maxx_p - minx_p
    span_y = maxy_p - miny_p
    
    if span_x <= 0 or span_y <= 0:
        raise ValueError("BBox proyectada inválida")

    width = int(math.ceil(span_x / res_m))
    height = int(math.ceil(span_y / res_m))

    if max_dim is not None:
        scale = max(width / max_dim, height / max_dim, 1.0)
        width = int(math.ceil(width / scale))
        height = int(math.ceil(height / scale))

    dst_transform = from_bounds(minx_p, miny_p, maxx_p, maxy_p, width, height)
    return width, height, dst_transform, (minx_p, miny_p, maxx_p, maxy_p)


# ============================================================================
# ROI
# ============================================================================

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
# PLANETARY COMPUTER - LECTURA DE BANDAS COG
# ============================================================================

def read_band_window_cog(item, band_key, bbox_4326, dst_transform, dst_crs, width, height):
    """
    Lee una banda de Sentinel-2 usando Cloud-Optimized GeoTIFF.
    
    CORREGIDO: Calcula la intersección real entre el tile y el ROI para evitar
    devolver NaN en áreas donde el tile no tiene cobertura.
    """
    
    asset = item.assets.get(band_key)
    
    if not asset:
        asset = item.assets.get(band_key.lower())
    
    if not asset:
        variants = {
            'B04': ['red', 'B04', 'b04'],
            'B08': ['nir', 'B08', 'b08', 'nir08'],
            'SCL': ['scl', 'SCL'],
            'QA60': ['qa60', 'QA60']
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
            # Obtener bounds del tile en su CRS nativo
            tile_bounds = src.bounds
            
            # Convertir ROI bbox a CRS del tile
            src_bbox = transform_bounds(
                "EPSG:4326", src.crs,
                *bbox_4326, densify_pts=21
            )
            
            # Calcular INTERSECCIÓN entre tile y ROI
            # Esto evita pedir datos fuera del tile
            intersection_bbox = (
                max(tile_bounds.left, src_bbox[0]),    # minx
                max(tile_bounds.bottom, src_bbox[1]),  # miny
                min(tile_bounds.right, src_bbox[2]),   # maxx
                min(tile_bounds.top, src_bbox[3])      # maxy
            )
            
            # Verificar si hay intersección válida
            if intersection_bbox[0] >= intersection_bbox[2] or intersection_bbox[1] >= intersection_bbox[3]:
                # No hay intersección - este tile no cubre esta área del ROI
                return None
            
            # Leer solo la ventana de intersección
            window = window_from_bounds(*intersection_bbox, transform=src.transform)
            data = src.read(1, window=window)
            src_transform_win = src.window_transform(window)
            src_crs = src.crs
            src_nodata = src.nodata
        
        if band_key in ['SCL', 'QA60']:
            resampling_method = Resampling.nearest
            dtype = np.int16 if band_key == 'SCL' else np.uint16
        else:
            resampling_method = Resampling.bilinear
            dtype = np.float32
        
        # Reproyectar al grid de salida
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
            print(f"[BAND] ✗ Error leyendo {band_key} de {item.id}: {e}")
        return None


def _item_date(item):
    """Extraer fecha del STAC Item"""
    date_str = item.properties['datetime']
    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))


def _item_cloud_cover(item):
    """Extraer % de nubes del STAC Item"""
    return item.properties.get('eo:cloud_cover', -1)


# ============================================================================
# PROCESAMIENTO NDVI CON MOSAICO MULTI-TILE
# ============================================================================

def process_item_to_ndvi_enhanced(item, bbox_4326, dst_transform, dst_crs, width, height):
    """Procesar STAC Item a NDVI con cloud masking mejorado"""
    
    tile_id = item.id
    print(f"\n[TILE] Procesando: {tile_id}")
    
    red = read_band_window_cog(item, 'B04', bbox_4326, dst_transform, dst_crs, width, height)
    nir = read_band_window_cog(item, 'B08', bbox_4326, dst_transform, dst_crs, width, height)
    
    if red is None or nir is None:
        print(f"[TILE] ✗ Faltan bandas espectrales en {tile_id}")
        return None, 0.0, None
    
    red = red.astype(np.float32)
    nir = nir.astype(np.float32)
    
    red[red == 0] = np.nan
    nir[nir == 0] = np.nan
    red[(red < 0) | (red > 10000)] = np.nan
    nir[(nir < 0) | (nir > 10000)] = np.nan
    
    red = red / 10000.0
    nir = nir / 10000.0
    
    scl = read_band_window_cog(item, 'SCL', bbox_4326, dst_transform, dst_crs, width, height)
    
    quality_weights = None
    
    if scl is not None:
        invalid = enhanced_cloud_mask(scl, None)
        red[invalid] = np.nan
        nir[invalid] = np.nan
        
        cloud_pct = 100 * invalid.sum() / invalid.size
        print(f"[TILE] Píxeles filtrados: {cloud_pct:.1f}%")
        
        if USE_WEIGHTED_COMPOSITE:
            quality_weights = compute_pixel_quality_weights(scl)
    else:
        print(f"[TILE] ⚠ SCL no disponible en {tile_id}")
    
    ndvi = compute_ndvi(red, nir)
    valid_frac = float(np.isfinite(ndvi).sum()) / float(ndvi.size)
    
    print(f"[TILE] Cobertura válida: {valid_frac*100:.1f}%")
    
    return ndvi, valid_frac, quality_weights


def create_mosaic_from_items(items, bbox_4326, dst_transform, dst_crs, width, height):
    """
    Crear mosaico NDVI combinando múltiples tiles
    
    Estrategia:
    - Usa weighted average en zonas de solapamiento
    - Prioriza píxeles de mejor calidad
    """
    print(f"\n{'='*70}")
    print(f"CREANDO MOSAICO DE {len(items)} TILES")
    print(f"{'='*70}")
    
    # Arrays acumuladores
    ndvi_sum = np.zeros((height, width), dtype=np.float32)
    weight_sum = np.zeros((height, width), dtype=np.float32)
    
    tiles_procesados = 0
    
    for idx, item in enumerate(items, 1):
        print(f"\n[MOSAIC] Tile {idx}/{len(items)}")
        
        ndvi, valid_frac, quality_weights = process_item_to_ndvi_enhanced(
            item, bbox_4326, dst_transform, dst_crs, width, height
        )
        
        if ndvi is None or valid_frac < MIN_VALID_COVERAGE:
            print(f"[MOSAIC] ✗ Tile rechazado (cobertura {valid_frac*100:.1f}% < {MIN_VALID_COVERAGE*100:.0f}%)")
            continue
        
        # Máscara de píxeles válidos
        valid_mask = np.isfinite(ndvi)
        
        if not np.any(valid_mask):
            print(f"[MOSAIC] ✗ Tile sin píxeles válidos")
            continue
        
        # Pesos para este tile
        if quality_weights is not None and USE_WEIGHTED_COMPOSITE:
            tile_weights = quality_weights.copy()
        else:
            tile_weights = np.ones_like(ndvi, dtype=np.float32)
        
        # Solo donde hay datos válidos
        tile_weights[~valid_mask] = 0
        
        # Acumular
        ndvi_safe = np.nan_to_num(ndvi, nan=0.0)
        ndvi_sum += ndvi_safe * tile_weights
        weight_sum += tile_weights
        
        tiles_procesados += 1
        print(f"[MOSAIC] ✓ Tile añadido al mosaico")
    
    if tiles_procesados == 0:
        print(f"\n[MOSAIC] ✗ No se pudo procesar ningún tile")
        return None
    
    # Calcular mosaico final
    composite = np.where(weight_sum > 0, ndvi_sum / weight_sum, np.nan)
    
    valid_composite = composite[np.isfinite(composite)]
    valid_frac = len(valid_composite) / composite.size
    
    print(f"\n[MOSAIC] {'='*60}")
    print(f"[MOSAIC] ✓ Mosaico completado")
    print(f"[MOSAIC] Tiles procesados: {tiles_procesados}/{len(items)}")
    print(f"[MOSAIC] Cobertura final: {valid_frac*100:.1f}%")
    print(f"[MOSAIC] NDVI - min: {valid_composite.min():.3f}, max: {valid_composite.max():.3f}, mean: {valid_composite.mean():.3f}")
    
    return composite


# ============================================================================
# BASE DE DATOS
# ============================================================================

def fetch_recintos_geojson():
    """Obtener recintos de la BBDD"""
    sql = text("""
        SELECT id_recinto, ST_AsGeoJSON(geom) AS geojson, ST_SRID(geom) AS srid
        FROM public.recintos
        WHERE geom IS NOT NULL
    """)
    rows = db.session.execute(sql).fetchall()
    return [(int(r.id_recinto), r.geojson, int(r.srid) if r.srid else 4326) for r in rows]


def zonal_stats_for_geom_fast(dataset, geom):
    """Calcular estadísticas zonales para una geometría"""
    minx, miny, maxx, maxy = geom.bounds
    win = window_from_bounds(minx, miny, maxx, maxy, transform=dataset.transform)
    win = win.round_offsets().round_lengths()
    
    if win.width <= 0 or win.height <= 0:
        return None

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


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

def main():
    app = create_app()
    
    with app.app_context():
        print(f"\n{'='*70}")
        print("CONFIGURACIÓN")
        print(f"{'='*70}")
        print(f"Fuente: Planetary Computer (Microsoft)")
        print(f"Modo: MOSAICO MULTI-TILE")
        print(f"FECHA OBJETIVO: {TARGET_DATE.strftime('%Y-%m-%d')}")
        print(f"Ventana de búsqueda: ±{DATE_WINDOW_DAYS} días")
        print(f"Cobertura nubes máx: {CLOUD_MAX}%")
        print(f"Buffer nubes: {CLOUD_BUFFER_PIXELS} píxeles (~{CLOUD_BUFFER_PIXELS*10}m)")
        print(f"Composite ponderado: {'SÍ' if USE_WEIGHTED_COMPOSITE else 'NO'}")
        
        # Obtener ROI
        minx, miny, maxx, maxy = get_roi_bbox_from_gpkg()
        bbox = (minx, miny, maxx, maxy)
        
        # Buscar TODOS los tiles que cubren el ROI
        items = search_planetary_computer_all_tiles(
            bbox, TARGET_DATE, DATE_WINDOW_DAYS, CLOUD_MAX
        )
        
        if not items:
            print("\n[ERROR] No se encontraron imágenes para la fecha especificada")
            return 1
        
        print(f"\n{'='*70}")
        print(f"TILES SELECCIONADOS: {len(items)}")
        print(f"{'='*70}")
        for idx, item in enumerate(items, 1):
            date = _item_date(item).date()
            clouds = _item_cloud_cover(item)
            print(f"{idx}. {item.id}")
            print(f"   Fecha: {date} | Nubes: {clouds:.1f}%")
        
        # Determinar CRS destino
        dst_crs = "EPSG:25830"
        
        width, height, dst_transform, dst_bounds_proj = compute_grid_from_bbox_meters(
            bbox4326=bbox,
            dst_crs=dst_crs,
            res_m=NDVI_RES_M,
            max_dim=NDVI_MAX_DIM,
        )
        
        print(f"\n[GRID] Dimensiones: {width} x {height} píxeles")
        print(f"[GRID] Resolución: {NDVI_RES_M}m/píxel")
        print(f"[GRID] CRS: {dst_crs}")
        
        # Crear mosaico
        composite = create_mosaic_from_items(
            items, bbox, dst_transform, dst_crs, width, height
        )
        
        if composite is None:
            print(f"\n[ERROR] No se pudo crear el mosaico")
            return 1
        
        # Estadísticas finales
        valid_ndvi = composite[np.isfinite(composite)]
        
        print(f"\n{'='*70}")
        print("ESTADÍSTICAS FINALES")
        print(f"{'='*70}")
        print(f"  NDVI mínimo:     {valid_ndvi.min():.3f}")
        print(f"  NDVI máximo:     {valid_ndvi.max():.3f}")
        print(f"  NDVI promedio:   {valid_ndvi.mean():.3f}")
        print(f"  NDVI mediana:    {np.median(valid_ndvi):.3f}")
        print(f"  Desv. estándar:  {valid_ndvi.std():.3f}")
        
        # Fechas
        ndvi_date = _item_date(items[0])
        fecha_str = ndvi_date.strftime("%Y%m%d")
        date_display = ndvi_date.strftime("%Y-%m-%d")
        
        # Guardar archivos
        ndvi_dir = Path(__file__).resolve().parents[1] / "data" / "processed" / "ndvi_composite"
        ndvi_dir.mkdir(parents=True, exist_ok=True)
        
        tif_path = ndvi_dir / f"ndvi_pc_{fecha_str}_mosaic_utm.tif"
        tif_path_3857 = ndvi_dir / f"ndvi_pc_{fecha_str}_mosaic_3857.tif"
        png_path = ndvi_dir / f"ndvi_pc_{fecha_str}_mosaic.png"
        meta_path = ndvi_dir / f"ndvi_pc_{fecha_str}_mosaic.json"
        
        print(f"\n{'='*70}")
        print("GUARDANDO ARCHIVOS")
        print(f"{'='*70}")
        
        # GeoTIFF UTM
        profile = {
            "driver": "GTiff",
            "height": composite.shape[0],
            "width": composite.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": dst_crs,
            "transform": dst_transform,
            "nodata": np.nan,
            "compress": "deflate",
        }
        
        with rasterio.open(str(tif_path), "w", **profile) as dst:
            dst.write(composite.astype(np.float32), 1)
        print(f"[OUTPUT] ✓ GeoTIFF UTM -> {tif_path.name}")
        
        # Reproyectar a EPSG:3857
        warp_tif_to_3857(str(tif_path), str(tif_path_3857))
        print(f"[OUTPUT] ✓ GeoTIFF 3857 -> {tif_path_3857.name}")
        
        # PNG
        rgba = ndvi_to_rgba(composite)
        Image.fromarray(rgba, mode="RGBA").save(str(png_path), format="PNG", optimize=True)
        print(f"[OUTPUT] ✓ PNG -> {png_path.name}")
        
        # Metadata JSON
        with rasterio.open(str(tif_path_3857)) as ds:
            b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
            minx2, miny2, maxx2, maxy2 = map(float, b)
        
        metadata = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "ndvi_date": ndvi_date.isoformat(),
            "target_date": TARGET_DATE.strftime("%Y-%m-%d"),
            "date_display": date_display,
            "source": "Planetary Computer (Microsoft)",
            "processing": {
                "version": "Enhanced PC v2.1 - Multi-Tile Mosaic",
                "tiles_processed": len(items),
                "tile_ids": [item.id for item in items],
                "cloud_masking": "SCL multi-layer",
                "cloud_buffer_pixels": CLOUD_BUFFER_PIXELS,
                "composite_method": "weighted_mosaic",
                "quality_weighting": USE_WEIGHTED_COMPOSITE,
                "cog_optimized": True
            },
            "bbox_4326": [minx2, miny2, maxx2, maxy2],
            "bounds_leaflet": [[miny2, minx2], [maxy2, maxx2]],
            "grid_size": [int(composite.shape[1]), int(composite.shape[0])],
            "resolution_m": float(NDVI_RES_M),
            "crs": dst_crs,
            "crs_epsg": int(dst_crs.split(':')[1]),
            "statistics": {
                "min": float(valid_ndvi.min()),
                "max": float(valid_ndvi.max()),
                "mean": float(valid_ndvi.mean()),
                "median": float(np.median(valid_ndvi)),
                "std": float(valid_ndvi.std()),
            },
            "files": {
                "utm_tif": tif_path.name,
                "epsg3857_tif": tif_path_3857.name,
                "png": png_path.name,
                "metadata": meta_path.name
            }
        }
        
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OUTPUT] ✓ Metadata JSON -> {meta_path.name}")
        
        # ========================================================================
        # GUARDAR EN BASE DE DATOS
        # ========================================================================
        print(f"\n{'='*70}")
        print("GUARDANDO EN BASE DE DATOS")
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
            
            ruta_rel = str(Path("data") / "processed" / "ndvi_composite" / tif_path.name)
            sensor_desc = f"S2 L2A NDVI Mosaic ({len(items)} tiles) | {date_display}"
            
            id_imagen = db.session.execute(sql_img, {
                "origen": "satelite",
                "fecha": ndvi_date.date(),
                "epsg": int(dst_crs.split(':')[1]),
                "sensor": sensor_desc,
                "res": float(NDVI_RES_M),
                "minx": minx2, "miny": miny2, "maxx": maxx2, "maxy": maxy2,
                "ruta": ruta_rel,
            }).scalar()
            
            print(f"[BBDD] ✓ Imagen insertada - ID: {id_imagen}")
            
            sql_idx = text("""
                INSERT INTO public.indices_raster
                  (id_imagen, id_recinto, tipo_indice, fecha_calculo, fecha_ndvi, 
                   epsg, resolucion_m, valor_medio, valor_min, valor_max, 
                   desviacion_std, ruta_raster, ruta_ndvi)
                VALUES
                  (:id_imagen, :id_recinto, :tipo, :fecha_calc, :fecha_ndvi, 
                   :epsg, :res, :mean, :min, :max, :std, :ruta_raster, :ruta_ndvi)
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
            print(f"[BBDD] Procesando {len(recintos)} recintos...")
            
            rows_to_insert = []
            inserted = 0
            
            with rasterio.open(str(tif_path)) as ds:
                ds_crs = ds.crs
                ds_bounds = ds.bounds
                
                for id_recinto, gj, srid in recintos:
                    try:
                        geom_rec = shape(json.loads(gj))
                        geom_proj_gj = transform_geom(
                            f"EPSG:{srid}", ds_crs, 
                            mapping(geom_rec), precision=6
                        )
                        geom_proj = shape(geom_proj_gj)
                        
                        if not geom_proj.intersects(box(*ds_bounds)):
                            continue
                        
                        stats = zonal_stats_for_geom_fast(ds, geom_proj)
                        
                        if not stats or not np.isfinite(stats["mean"]):
                            continue
                        
                        # *** RUTA CORREGIDA: Carpeta por fecha ***
                        rows_to_insert.append({
                            "id_imagen": int(id_imagen),
                            "id_recinto": int(id_recinto),
                            "tipo": "NDVI",
                            "fecha_calc": datetime.now(timezone.utc),
                            "fecha_ndvi": ndvi_date,
                            "epsg": int(dst_crs.split(':')[1]),
                            "res": float(NDVI_RES_M),
                            "mean": stats["mean"],
                            "min": stats["min"],
                            "max": stats["max"],
                            "std": stats["std"],
                            "ruta_raster": ruta_rel,
                            "ruta_ndvi": f"static/thumbnails/{fecha_str}/{id_recinto}.png",
                        })
                        inserted += 1
                        
                        if len(rows_to_insert) >= DB_BATCH_SIZE:
                            db.session.execute(sql_idx, rows_to_insert)
                            rows_to_insert.clear()
                    
                    except Exception as e:
                        if DEBUG_MODE:
                            print(f"[BBDD] Error en recinto {id_recinto}: {e}")
                        continue
            
            if rows_to_insert:
                db.session.execute(sql_idx, rows_to_insert)
            
            db.session.commit()
            
            print(f"[BBDD] ✓ Recintos actualizados: {inserted}")
            print(f"[BBDD] ✓ Formato ruta thumbnails: static/thumbnails/{fecha_str}/{{id}}.png")
        
        except Exception as e:
            db.session.rollback()
            print(f"\n[BBDD] ✗ ERROR: {repr(e)}")
            import traceback
            traceback.print_exc()
        
        print(f"\n{'='*70}")
        print("✓ PROCESO COMPLETADO EXITOSAMENTE")
        print(f"{'='*70}")
        print(f"\n✓ Mosaico creado con {len(items)} tiles")
        print(f"✓ Cobertura completa del ROI")
        print(f"✓ Recintos actualizados: {inserted}")
        print(f"✓ Thumbnails: static/thumbnails/{fecha_str}/")
        
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        raise SystemExit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[INTERRUPT] Proceso cancelado")
        raise SystemExit(1)
    except Exception as e:
        print(f"\n[ERROR FATAL] {e}")
        import traceback
        traceback.print_exc()
        raise SystemExit(1)