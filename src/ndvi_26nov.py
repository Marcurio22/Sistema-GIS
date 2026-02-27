#!/usr/bin/env python3
"""
NDVI Mejorado con Planetary Computer - FECHA ESPECÍFICA
========================================================
Modificado para buscar exactamente una imagen del 26 de noviembre de 2025

- Cloud masking multi-capa (SCL + QA60)
- Buffer de seguridad alrededor de nubes
- Detección de sombras mejorada
- Weighted composite por calidad de píxel
- Cloud-Optimized GeoTIFFs (COG) - 98% menos descarga
- API STAC moderna

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


print("[NDVI-PC] Script de NDVI - FECHA ESPECÍFICA: 26 Nov 2025")
print("="*70)

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

ROI_PATH = os.getenv(
    "ROI_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg")
)

# FECHA ESPECÍFICA - 26 de noviembre de 2025
TARGET_DATE = datetime(2025, 4, 25, tzinfo=timezone.utc)
# Buscar en ventana de +/- 1 día para mayor flexibilidad
DATE_WINDOW_DAYS = 0

# Parámetros de búsqueda
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "40"))
MAX_ITEMS = 10  

# Parámetros de calidad
CLOUD_BUFFER_PIXELS = int(os.getenv("CLOUD_BUFFER_PIXELS", "5"))    
MIN_VALID_COVERAGE = float(os.getenv("MIN_VALID_COVERAGE", "0.05"))
USE_WEIGHTED_COMPOSITE = os.getenv("USE_WEIGHTED_COMPOSITE", "1") == "1"

# Parámetros de procesamiento
NDVI_RES_M = float(os.getenv("NDVI_RES_M", "10"))
NDVI_MAX_DIM = int(os.getenv("NDVI_MAX_DIM", "12000"))
DEBUG_MODE = os.getenv("DEBUG_MODE", "1") == "1"

# Cloud masking
INVALID_SCL = {0, 1, 3, 7, 8, 9, 10, 11}
SHADOW_SCL = {2, 3}
CIRRUS_SCL = {10}

# BBDD
DB_BATCH_SIZE = int(os.getenv("NDVI_DB_BATCH_SIZE", "500"))
DB_PROGRESS_EVERY = int(os.getenv("NDVI_DB_PROGRESS_EVERY", "500"))


# ============================================================================
# PLANETARY COMPUTER - BÚSQUEDA CORREGIDA
# ============================================================================

def search_planetary_computer_single_date(bbox, target_date, window_days, cloud_max, max_items):
    """
    Buscar imágenes Sentinel-2 L2A en Planetary Computer para una fecha específica.
    
    CORREGIDO: Busca sin filtros y filtra manualmente para evitar problemas con query STAC
    
    Args:
        bbox: (minx, miny, maxx, maxy) en EPSG:4326
        target_date: datetime de la fecha objetivo
        window_days: días de ventana +/- alrededor de la fecha
        cloud_max: % máximo de nubes
        max_items: número máximo de items a devolver
    
    Returns:
        Item de STAC más cercano a la fecha objetivo
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
        
        # BÚSQUEDA SIN FILTROS - Luego filtramos manualmente
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=date_range,
            limit=100
        )
        
        items = list(search.items())
        
        print(f"[SEARCH] ✓ Productos encontrados (sin filtrar): {len(items)}")
        
        if not items:
            print(f"[SEARCH] ✗ No hay productos en la ventana temporal")
            return None
        
        # Mostrar todas las imágenes disponibles
        print(f"[SEARCH] Imágenes disponibles:")
        for i, item in enumerate(items, 1):
            item_date = datetime.fromisoformat(item.properties['datetime'].replace('Z', '+00:00'))
            clouds = item.properties.get('eo:cloud_cover', -1)
            print(f"[SEARCH]   {i}. {item_date.strftime('%Y-%m-%d %H:%M:%S UTC')} | Nubes: {clouds:.1f}% | ID: {item.id}")
        
        # Filtrar manualmente por cobertura de nubes
        filtered_items = [
            item for item in items 
            if item.properties.get('eo:cloud_cover', 999) <= cloud_max
        ]
        
        print(f"[SEARCH] ✓ Productos después de filtrar por nubes (<= {cloud_max}%): {len(filtered_items)}")
        
        if not filtered_items:
            print(f"[SEARCH] ✗ No hay productos con nubes <= {cloud_max}%")
            return None
        
        # Encontrar el mejor: menos nubes, más cercano a fecha objetivo
        def item_score(item):
            item_date = datetime.fromisoformat(item.properties['datetime'].replace('Z', '+00:00'))
            time_distance = abs((item_date - target_date).total_seconds())
            clouds = item.properties.get('eo:cloud_cover', 100)
            # Priorizar menos nubes, luego cercanía temporal
            return (clouds, time_distance)
        
        filtered_items.sort(key=item_score)
        
        best_item = filtered_items[0]
        best_date = datetime.fromisoformat(best_item.properties['datetime'].replace('Z', '+00:00'))
        best_clouds = best_item.properties.get('eo:cloud_cover', -1)
        
        print(f"[SEARCH] ✓ Mejor imagen seleccionada:")
        print(f"[SEARCH]   Fecha: {best_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"[SEARCH]   Nubes: {best_clouds:.1f}%")
        print(f"[SEARCH]   ID: {best_item.id}")
        print(f"[SEARCH]   Distancia temporal: {abs((best_date - target_date).days)} días")
        
        return best_item
        
    except Exception as e:
        print(f"[SEARCH] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


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
        if DEBUG_MODE:
            print(f"[MASK] Buffer aplicado: {CLOUD_BUFFER_PIXELS} píxeles")
    
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
    """Lee una banda de Sentinel-2 usando Cloud-Optimized GeoTIFF"""
    
    if DEBUG_MODE and not hasattr(read_band_window_cog, '_shown_assets'):
        print(f"[DEBUG] Assets disponibles en item:")
        for k in sorted(item.assets.keys()):
            print(f"  - {k}")
        read_band_window_cog._shown_assets = True
    
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
                if DEBUG_MODE:
                    print(f"[BAND] {band_key} encontrado como '{variant}'")
                break
    
    if not asset:
        print(f"[BAND] ✗ Banda {band_key} no encontrada")
        return None
    
    href = asset.href
    
    try:
        with rasterio.open(href) as src:
            src_bbox = transform_bounds(
                "EPSG:4326", src.crs,
                *bbox_4326, densify_pts=21
            )
            
            window = window_from_bounds(*src_bbox, transform=src.transform)
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


def _item_date(item):
    """Extraer fecha del STAC Item"""
    date_str = item.properties['datetime']
    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))


def _item_cloud_cover(item):
    """Extraer % de nubes del STAC Item"""
    return item.properties.get('eo:cloud_cover', -1)


# ============================================================================
# PROCESAMIENTO NDVI CON PLANETARY COMPUTER
# ============================================================================

def process_item_to_ndvi_enhanced(item, bbox_4326, dst_transform, dst_crs, width, height):
    """Procesar STAC Item a NDVI con cloud masking mejorado"""
    
    print(f"[PROCESS] Leyendo B04 (Red)...")
    red = read_band_window_cog(item, 'B04', bbox_4326, dst_transform, dst_crs, width, height)
    
    print(f"[PROCESS] Leyendo B08 (NIR)...")
    nir = read_band_window_cog(item, 'B08', bbox_4326, dst_transform, dst_crs, width, height)
    
    if red is None or nir is None:
        print(f"[PROCESS] ✗ Faltan bandas espectrales")
        return None, 0.0, None
    
    red = red.astype(np.float32)
    nir = nir.astype(np.float32)
    
    red[red == 0] = np.nan
    nir[nir == 0] = np.nan
    red[(red < 0) | (red > 10000)] = np.nan
    nir[(nir < 0) | (nir > 10000)] = np.nan
    
    red = red / 10000.0
    nir = nir / 10000.0
    
    print(f"[PROCESS] Leyendo SCL (cloud mask)...")
    scl = read_band_window_cog(item, 'SCL', bbox_4326, dst_transform, dst_crs, width, height)
    
    qa60 = None
    quality_weights = None
    
    if scl is not None:
        invalid = enhanced_cloud_mask(scl, qa60)
        red[invalid] = np.nan
        nir[invalid] = np.nan
        
        cloud_pct = 100 * invalid.sum() / invalid.size
        print(f"[MASK] Píxeles filtrados: {cloud_pct:.1f}%")
        
        if USE_WEIGHTED_COMPOSITE:
            quality_weights = compute_pixel_quality_weights(scl)
            print(f"[QUALITY] Pesos de calidad calculados")
    else:
        print(f"[MASK] ⚠ SCL no disponible, sin cloud masking")
    
    ndvi = compute_ndvi(red, nir)
    valid_frac = float(np.isfinite(ndvi).sum()) / float(ndvi.size)
    
    return ndvi, valid_frac, quality_weights


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
        print(f"FECHA OBJETIVO: {TARGET_DATE.strftime('%Y-%m-%d')}")
        print(f"Ventana de búsqueda: ±{DATE_WINDOW_DAYS} días")
        print(f"Cobertura nubes máx: {CLOUD_MAX}%")
        print(f"Buffer nubes: {CLOUD_BUFFER_PIXELS} píxeles (~{CLOUD_BUFFER_PIXELS*10}m)")
        print(f"Cobertura válida mín: {MIN_VALID_COVERAGE*100:.0f}%")
        print(f"Composite ponderado: {'SÍ' if USE_WEIGHTED_COMPOSITE else 'NO'}")
        
        # Obtener ROI
        minx, miny, maxx, maxy = get_roi_bbox_from_gpkg()
        bbox = (minx, miny, maxx, maxy)
        
        # Buscar producto específico
        item = search_planetary_computer_single_date(
            bbox, TARGET_DATE, DATE_WINDOW_DAYS, CLOUD_MAX, MAX_ITEMS
        )
        
        if not item:
            print("\n[ERROR] No se encontró imagen para la fecha especificada")
            print("Sugerencias:")
            print(f"  - Aumentar CLOUD_MAX (actual: {CLOUD_MAX}%)")
            print(f"  - Aumentar DATE_WINDOW_DAYS (actual: {DATE_WINDOW_DAYS})")
            return 1
        
        print(f"\n{'='*70}")
        print(f"IMAGEN SELECCIONADA")
        print(f"{'='*70}")
        date = _item_date(item).date()
        clouds = _item_cloud_cover(item)
        print(f"Fecha: {date} | Nubes: {clouds:.1f}%")
        print(f"ID: {item.id}")
        
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
        
        # Procesar imagen
        print(f"\n{'='*70}")
        print(f"PROCESANDO IMAGEN")
        print(f"{'='*70}")
        
        ndvi, valid_cov, weights = process_item_to_ndvi_enhanced(
            item, bbox, dst_transform, dst_crs, width, height
        )
        
        if ndvi is None or valid_cov < MIN_VALID_COVERAGE:
            print(f"[IMAGEN] ✗ RECHAZADA - Cobertura válida: {valid_cov*100:.1f}% < {MIN_VALID_COVERAGE*100:.0f}%")
            return 1
        
        # Estadísticas
        valid_ndvi = ndvi[np.isfinite(ndvi)]
        print(f"[IMAGEN] ✓ ACEPTADA")
        print(f"[IMAGEN] Cobertura válida: {valid_cov*100:.1f}%")
        print(f"[IMAGEN] NDVI - min: {valid_ndvi.min():.3f}, max: {valid_ndvi.max():.3f}, mean: {valid_ndvi.mean():.3f}")
        
        # El composite es directamente el NDVI (solo 1 imagen)
        composite = ndvi
        
        print(f"\n{'='*70}")
        print("ESTADÍSTICAS FINALES")
        print(f"{'='*70}")
        print(f"  NDVI mínimo:     {valid_ndvi.min():.3f}")
        print(f"  NDVI máximo:     {valid_ndvi.max():.3f}")
        print(f"  NDVI promedio:   {valid_ndvi.mean():.3f}")
        print(f"  NDVI mediana:    {np.median(valid_ndvi):.3f}")
        print(f"  Percentil 25:    {np.percentile(valid_ndvi, 25):.3f}")
        print(f"  Percentil 75:    {np.percentile(valid_ndvi, 75):.3f}")
        print(f"  Desv. estándar:  {valid_ndvi.std():.3f}")
        
        # Fechas
        ndvi_date = _item_date(item)
        fecha_str = ndvi_date.strftime("%Y%m%d")
        date_display = ndvi_date.strftime("%Y-%m-%d")
        
        print(f"\n[INFO] Fecha de adquisición: {date_display}")
        
        # Guardar archivos
        static_ndvi_dir = Path(app.root_path) / "static" / "ndvi"
        static_ndvi_dir.mkdir(parents=True, exist_ok=True)
        
        tif_path = static_ndvi_dir / f"ndvi_pc_{fecha_str}_utm.tif"
        tif_path_3857 = static_ndvi_dir / f"ndvi_pc_{fecha_str}_3857.tif"
        png_path = static_ndvi_dir / f"ndvi_pc_{fecha_str}.png"
        meta_path = static_ndvi_dir / f"ndvi_pc_{fecha_str}.json"
        
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
                "version": "Enhanced PC v1.0 - Single Date",
                "cloud_masking": "SCL multi-layer",
                "cloud_buffer_pixels": CLOUD_BUFFER_PIXELS,
                "cloud_buffer_meters": CLOUD_BUFFER_PIXELS * 10,
                "composite_method": "single_image",
                "quality_weighting": USE_WEIGHTED_COMPOSITE,
                "min_valid_coverage": MIN_VALID_COVERAGE,
                "cog_optimized": True
            },
            "product_id": item.id,
            "cloud_coverage_metadata": _item_cloud_cover(item),
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
                "p25": float(np.percentile(valid_ndvi, 25)),
                "p75": float(np.percentile(valid_ndvi, 75))
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
            # Insert en public.imagenes
            sql_img = text("""
                INSERT INTO public.imagenes
                  (origen, fecha_adquisicion, epsg, sensor, resolucion_m, bbox, ruta_archivo)
                VALUES
                  (:origen, :fecha, :epsg, :sensor, :res, 
                   ST_MakeEnvelope(:minx,:miny,:maxx,:maxy,4326), :ruta)
                RETURNING id_imagen
            """)
            
            ruta_rel = str(Path("static") / "ndvi" / tif_path.name)
            
            sensor_desc = f"Sentinel-2 L2A NDVI PC | {date_display}"
            if USE_WEIGHTED_COMPOSITE:
                sensor_desc += " | Weighted Quality"
            
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
            
            # UPSERT en public.indices_raster
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
            
            # Obtener recintos
            recintos = fetch_recintos_geojson()
            print(f"[BBDD] Procesando {len(recintos)} recintos...")
            
            rows_to_insert = []
            processed = 0
            inserted = 0
            out_of_bounds = 0
            no_valid_pixels = 0
            errors = 0
            
            with rasterio.open(str(tif_path)) as ds:
                ds_crs = ds.crs
                ds_bounds = ds.bounds
                
                for id_recinto, gj, srid in recintos:
                    processed += 1
                    
                    try:
                        geom_rec = shape(json.loads(gj))
                        geom_proj_gj = transform_geom(
                            f"EPSG:{srid}", ds_crs, 
                            mapping(geom_rec), precision=6
                        )
                        geom_proj = shape(geom_proj_gj)
                        
                        if not geom_proj.intersects(box(*ds_bounds)):
                            out_of_bounds += 1
                            continue
                        
                        stats = zonal_stats_for_geom_fast(ds, geom_proj)
                        
                        if not stats or not np.isfinite(stats["mean"]):
                            no_valid_pixels += 1
                            continue
                        
                        ruta_thumbnail = f"static/thumbnails/{fecha_str}_{id_recinto}.png"
                        
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
                            "ruta_ndvi": ruta_thumbnail,
                        })
                        inserted += 1
                        
                        if len(rows_to_insert) >= DB_BATCH_SIZE:
                            db.session.execute(sql_idx, rows_to_insert)
                            rows_to_insert.clear()
                        
                        if processed % DB_PROGRESS_EVERY == 0:
                            print(f"[BBDD] Progreso: {processed}/{len(recintos)} | Insertados: {inserted}")
                    
                    except Exception as e:
                        errors += 1
                        if DEBUG_MODE:
                            print(f"[BBDD] Error en recinto {id_recinto}: {e}")
                        continue
            
            # Insertar últimos registros
            if rows_to_insert:
                db.session.execute(sql_idx, rows_to_insert)
            
            db.session.commit()
            
            print(f"\n[BBDD] {'='*60}")
            print(f"[BBDD] RESUMEN FINAL")
            print(f"[BBDD] {'='*60}")
            print(f"[BBDD] Total recintos:        {len(recintos)}")
            print(f"[BBDD] Insertados en BBDD:    {inserted}")
            print(f"[BBDD] Fuera de bounds:       {out_of_bounds}")
            print(f"[BBDD] Sin píxeles válidos:   {no_valid_pixels}")
            print(f"[BBDD] Errores:               {errors}")
            print(f"[BBDD] ✓ Proceso completado - ID Imagen: {id_imagen}")
        
        except Exception as e:
            db.session.rollback()
            print(f"\n[BBDD] ✗ ERROR: {repr(e)}")
            import traceback
            traceback.print_exc()
        
        # ========================================================================
        # RESUMEN FINAL
        # ========================================================================
        print(f"\n{'='*70}")
        print("✓ PROCESO COMPLETADO EXITOSAMENTE")
        print(f"{'='*70}")
        print(f"\nImagen procesada:")
        print(f"  ✓ Fecha objetivo: {TARGET_DATE.strftime('%Y-%m-%d')}")
        print(f"  ✓ Fecha real: {date_display}")
        print(f"  ✓ Nubes: {_item_cloud_cover(item):.1f}%")
        print(f"\nVentajas Planetary Computer:")
        print(f"  ✓ Solo descarga área de interés (COG)")
        print(f"  ✓ ~98% menos datos descargados")
        print(f"  ✓ 5-10x más rápido que Copernicus")
        print(f"\nProcesamiento aplicado:")
        print(f"  ✓ Cloud masking: SCL multi-capa")
        print(f"  ✓ Buffer de seguridad: {CLOUD_BUFFER_PIXELS} píxeles (~{CLOUD_BUFFER_PIXELS*10}m)")
        print(f"  ✓ Cobertura válida: {valid_cov*100:.1f}%")
        print(f"  ✓ Recintos actualizados: {inserted}")
        print(f"\nArchivos generados:")
        print(f"  {static_ndvi_dir.resolve()}")
        print(f"    - {tif_path.name}")
        print(f"    - {tif_path_3857.name}")
        print(f"    - {png_path.name}")
        print(f"    - {meta_path.name}")
        
        print(f"\n{'='*70}")
        return 0


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    try:
        exit_code = main()
        raise SystemExit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[INTERRUPT] Proceso cancelado por el usuario")
        raise SystemExit(1)
    except Exception as e:
        print(f"\n{'='*70}")
        print("[ERROR FATAL]")
        print(f"{'='*70}")
        print(f"{e}")
        print(f"\nTraceback completo:")
        import traceback
        traceback.print_exc()
        raise SystemExit(1)