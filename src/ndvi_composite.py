#!/usr/bin/env python3
"""
NDVI COMPOSITE COMPLETO - Planetary Computer
Genera un NDVI completo del ROI usando MÚLTIPLES TILES de Sentinel-2.

"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import numpy as np
import geopandas as gpd
from shapely.geometry import box, mapping
from scipy import ndimage
from scipy.interpolate import griddata

from PIL import Image

import math
import rasterio
from rasterio.warp import (
    reproject, Resampling, transform_bounds, calculate_default_transform
)
from rasterio.transform import from_bounds
from rasterio.windows import from_bounds as window_from_bounds
from rasterio.merge import merge

from dotenv import load_dotenv
from sqlalchemy import text
from webapp import create_app, db

# Planetary Computer
from pystac_client import Client
import planetary_computer as pc


print("[NDVI-COMPOSITE-FULL] Script de NDVI Composite - Cobertura Completa")
print("="*80)

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

ROI_PATH = os.getenv(
    "ROI_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg")
)

# VENTANA TEMPORAL
LOOKBACK_DAYS = int(os.getenv("NDVI_LOOKBACK_DAYS", "200"))
END_DATE = datetime.now(timezone.utc)
START_DATE = END_DATE - timedelta(days=LOOKBACK_DAYS)

# PARÁMETROS DE BÚSQUEDA
CLOUD_MAX = float(os.getenv("S2_CLOUD_MAX", "40"))  # Aumentado para tener más opciones
MAX_IMAGES_PER_TILE = int(os.getenv("MAX_COMPOSITE_IMAGES", "30"))

# PARÁMETROS DE CALIDAD
CLOUD_BUFFER_PIXELS = int(os.getenv("CLOUD_BUFFER_PIXELS", "3"))
FILL_LARGE_GAPS = os.getenv("FILL_LARGE_GAPS", "1") == "1"
MAX_GAP_SIZE_PIXELS = int(os.getenv("MAX_GAP_SIZE_PIXELS", "50"))  # Más agresivo

# PARÁMETROS DE PROCESAMIENTO
NDVI_RES_M = float(os.getenv("NDVI_RES_M", "10"))
NDVI_MAX_DIM = int(os.getenv("NDVI_MAX_DIM", "15000"))  # Aumentado
DEBUG_MODE = os.getenv("DEBUG_MODE", "1") == "1"

# CLOUD MASKING
INVALID_SCL = {0, 1, 3, 8, 9, 10, 11}  # Removido 7 (nubes baja prob) para más cobertura
SHADOW_SCL = {2, 3}

# PESOS DE CALIDAD PARA COMPOSITE
QUALITY_WEIGHTS = {
    4: 1.0,   # Vegetación
    5: 1.0,   # Suelo desnudo
    6: 0.95,  # Agua
    7: 0.7,   # Nubes baja prob - ahora SÍ se usa
    11: 0.8,  # Nieve/hielo
    2: 0.4,   # Sombras oscuras - último recurso
}


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


def apply_cloud_buffer(cloud_mask, buffer_pixels=3):
    """Expande máscara de nubes"""
    if buffer_pixels <= 0:
        return cloud_mask
    
    structure = ndimage.generate_binary_structure(2, 2)
    return ndimage.binary_dilation(cloud_mask, structure=structure, iterations=buffer_pixels)


def enhanced_cloud_mask(scl, buffer_pixels=3):
    """Máscara de nubes mejorada"""
    scl_int = np.nan_to_num(scl, nan=0).astype(np.int32)
    invalid = np.isin(scl_int, list(INVALID_SCL))
    
    if buffer_pixels > 0:
        invalid = apply_cloud_buffer(invalid, buffer_pixels)
    
    return invalid


def compute_pixel_quality_score(scl):
    """Calcula score de calidad para cada píxel [0-1]"""
    scl_int = np.nan_to_num(scl, nan=0).astype(np.int32)
    scores = np.zeros_like(scl, dtype=np.float32)
    
    for scl_class, weight in QUALITY_WEIGHTS.items():
        mask = (scl_int == scl_class)
        scores[mask] = weight
    
    return scores


def compute_ndvi(red, nir):
    """Calcular NDVI robusto"""
    den = nir + red
    return np.where(den == 0, np.nan, (nir - red) / den)


def fill_gaps_aggressive(ndvi, max_gap_size=50):
    """
    Rellena gaps de forma MÁS AGRESIVA usando interpolación espacial.
    Esencial para composite multi-tile.
    """
    if not FILL_LARGE_GAPS:
        return ndvi
    
    filled = ndvi.copy()
    invalid_mask = ~np.isfinite(filled)
    
    if not np.any(invalid_mask):
        return filled
    
    # Etiquetar regiones de gaps
    labeled_gaps, num_gaps = ndimage.label(invalid_mask)
    
    print(f"[GAPS] Detectados {num_gaps} grupos de píxeles inválidos")
    
    filled_count = 0
    large_gaps_count = 0
    
    for gap_id in range(1, num_gaps + 1):
        gap_mask = (labeled_gaps == gap_id)
        gap_size = gap_mask.sum()
        
        # Rellenar gaps pequeños y medianos
        if gap_size > max_gap_size:
            large_gaps_count += 1
            continue
        
        # Dilatar más para gaps grandes
        dilation_iters = min(5, max(2, int(np.sqrt(gap_size) / 2)))
        structure = ndimage.generate_binary_structure(2, 2)
        dilated = ndimage.binary_dilation(gap_mask, structure=structure, iterations=dilation_iters)
        
        neighbor_mask = dilated & ~gap_mask & np.isfinite(filled)
        
        if not np.any(neighbor_mask):
            continue
        
        neighbor_coords = np.column_stack(np.where(neighbor_mask))
        neighbor_values = filled[neighbor_mask]
        gap_coords = np.column_stack(np.where(gap_mask))
        
        try:
            # Usar linear para gaps pequeños, nearest para grandes
            method = 'linear' if gap_size < 100 else 'nearest'
            interpolated = griddata(neighbor_coords, neighbor_values, gap_coords, method=method)
            
            # Fallback a nearest si linear falla
            if np.any(~np.isfinite(interpolated)):
                interpolated = griddata(neighbor_coords, neighbor_values, gap_coords, method='nearest')
            
            filled[gap_mask] = interpolated
            filled_count += gap_size
            
        except Exception as e:
            if DEBUG_MODE:
                print(f"[GAPS] Error interpolando gap {gap_id} (size={gap_size}): {e}")
            continue
    
    if filled_count > 0:
        print(f"[GAPS] ✓ Rellenados {filled_count:,} píxeles")
    if large_gaps_count > 0:
        print(f"[GAPS] ⚠ {large_gaps_count} gaps grandes (>{max_gap_size} px) sin rellenar")
    
    return filled


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
    """Leer ROI y expandir bbox ligeramente para asegurar cobertura"""
    roi_path = Path(ROI_PATH)
    if not roi_path.exists():
        raise FileNotFoundError(f"ROI no existe: {roi_path.resolve()}")

    roi = gpd.read_file(roi_path).to_crs(4326)
    minx, miny, maxx, maxy = roi.total_bounds
    
    # EXPANDIR BBOX 2% para asegurar cobertura completa
    dx = (maxx - minx) * 0.02
    dy = (maxy - miny) * 0.02
    
    bbox = (
        float(minx - dx), 
        float(miny - dy), 
        float(maxx + dx), 
        float(maxy + dy)
    )
    
    print(f"[ROI] BBox original: ({minx:.6f}, {miny:.6f}, {maxx:.6f}, {maxy:.6f})")
    print(f"[ROI] BBox expandido: {bbox}")
    
    return bbox


# ============================================================================
# PLANETARY COMPUTER - BÚSQUEDA MEJORADA
# ============================================================================

def search_planetary_computer_all_tiles(bbox, start_date, end_date, cloud_max, max_per_tile):
    """
    Buscar TODAS las imágenes que cubren el ROI, incluyendo múltiples tiles.
    Agrupa por fecha para combinar tiles del mismo día.
    
    Returns:
        dict: {fecha: [lista de items de esa fecha]}
    """
    try:
        print(f"[SEARCH] Conectando con Planetary Computer...")
        print(f"[SEARCH] Ventana temporal: {start_date.strftime('%Y-%m-%d')} a {end_date.strftime('%Y-%m-%d')}")
        print(f"[SEARCH] BBox: {bbox}")
        print(f"[SEARCH] BUSCANDO EN TODAS LAS TILES QUE INTERSECTAN EL ROI")
        
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace
        )
        
        date_range = f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
        
        # Búsqueda SIN limit para obtener TODAS las imágenes
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=date_range,
            limit=500  # Aumentado significativamente
        )
        
        items = list(search.items())
        
        print(f"[SEARCH] ✓ Items encontrados: {len(items)}")
        
        if not items:
            return {}
        
        # Filtrar por nubes
        filtered_items = [
            item for item in items 
            if item.properties.get('eo:cloud_cover', 999) <= cloud_max
        ]
        
        print(f"[SEARCH] ✓ Items con nubes <= {cloud_max}%: {len(filtered_items)}")
        
        # Agrupar por FECHA (combinar tiles del mismo día)
        items_by_date = defaultdict(list)
        
        for item in filtered_items:
            item_date = datetime.fromisoformat(item.properties['datetime'].replace('Z', '+00:00'))
            date_key = item_date.date()
            items_by_date[date_key].append(item)
        
        print(f"[SEARCH] ✓ Fechas únicas encontradas: {len(items_by_date)}")
        
        # Mostrar información por fecha
        sorted_dates = sorted(items_by_date.keys(), reverse=True)
        
        print(f"\n[SEARCH] Imágenes por fecha (tiles por día):")
        for i, date_key in enumerate(sorted_dates[:15], 1):
            items_list = items_by_date[date_key]
            tiles = [item.properties.get('s2:mgrs_tile', 'N/A') for item in items_list]
            avg_clouds = np.mean([item.properties.get('eo:cloud_cover', 0) for item in items_list])
            print(f"[SEARCH]   {i}. {date_key} | {len(items_list)} tiles ({', '.join(set(tiles))}) | Nubes promedio: {avg_clouds:.1f}%")
        
        if len(sorted_dates) > 15:
            print(f"[SEARCH]   ... y {len(sorted_dates) - 15} fechas más")
        
        # Limitar fechas pero mantener TODAS las tiles de cada fecha
        selected_dates = sorted_dates[:max_per_tile]
        final_items_by_date = {d: items_by_date[d] for d in selected_dates}
        
        total_items = sum(len(items) for items in final_items_by_date.values())
        print(f"\n[SEARCH] ✓ SELECCIONADAS: {len(final_items_by_date)} fechas con {total_items} tiles totales")
        
        return final_items_by_date
        
    except Exception as e:
        print(f"[SEARCH] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return {}


# ============================================================================
# LECTURA DE BANDAS
# ============================================================================

def read_band_window_cog(item, band_key, bbox_4326, dst_transform, dst_crs, width, height):
    """Lee banda con manejo robusto de variantes"""
    
    variants_map = {
        'B04': ['B04', 'red', 'b04'],
        'B08': ['B08', 'nir', 'b08', 'nir08'],
        'SCL': ['SCL', 'scl'],
    }
    
    asset = None
    for variant in variants_map.get(band_key, [band_key]):
        if variant in item.assets:
            asset = item.assets[variant]
            break
    
    if not asset:
        return None
    
    href = asset.href
    
    try:
        with rasterio.open(href) as src:
            src_bbox = transform_bounds("EPSG:4326", src.crs, *bbox_4326, densify_pts=21)
            window = window_from_bounds(*src_bbox, transform=src.transform)
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
# COMPOSITE MULTI-TILE
# ============================================================================

def merge_tiles_same_date(items, bbox_4326, dst_transform, dst_crs, width, height, date_key):
    """
    Combina múltiples tiles del mismo día en un NDVI único.
    CLAVE para solucionar el problema de corte.
    """
    print(f"\n[MERGE] Combinando {len(items)} tiles de {date_key}")
    
    # Arrays para acumular
    merged_ndvi = np.full((height, width), np.nan, dtype=np.float32)
    merged_quality = np.zeros((height, width), dtype=np.float32)
    
    for idx, item in enumerate(items, 1):
        tile_id = item.properties.get('s2:mgrs_tile', f'tile{idx}')
        clouds = item.properties.get('eo:cloud_cover', -1)
        
        print(f"[MERGE]   Tile {idx}/{len(items)}: {tile_id} | Nubes: {clouds:.1f}%")
        
        # Leer bandas
        red = read_band_window_cog(item, 'B04', bbox_4326, dst_transform, dst_crs, width, height)
        nir = read_band_window_cog(item, 'B08', bbox_4326, dst_transform, dst_crs, width, height)
        scl = read_band_window_cog(item, 'SCL', bbox_4326, dst_transform, dst_crs, width, height)
        
        if red is None or nir is None:
            print(f"[MERGE]     ✗ Faltan bandas - OMITIDA")
            continue
        
        # Normalizar
        red = red.astype(np.float32) / 10000.0
        nir = nir.astype(np.float32) / 10000.0
        
        red[(red <= 0) | (red > 1)] = np.nan
        nir[(nir <= 0) | (nir > 1)] = np.nan
        
        # Cloud masking
        if scl is not None:
            invalid = enhanced_cloud_mask(scl, CLOUD_BUFFER_PIXELS)
            red[invalid] = np.nan
            nir[invalid] = np.nan
            quality_scores = compute_pixel_quality_score(scl)
        else:
            quality_scores = np.ones((height, width), dtype=np.float32) * 0.5
        
        # NDVI
        ndvi = compute_ndvi(red, nir)
        valid = np.isfinite(ndvi)
        
        if not np.any(valid):
            print(f"[MERGE]     ✗ Sin píxeles válidos")
            continue
        
        valid_count = valid.sum()
        print(f"[MERGE]     ✓ Píxeles válidos: {valid_count:,}")
        
        # Actualizar donde el nuevo score es mejor O donde no hay datos
        update_mask = valid & ((quality_scores > merged_quality) | ~np.isfinite(merged_ndvi))
        
        merged_ndvi[update_mask] = ndvi[update_mask]
        merged_quality[update_mask] = quality_scores[update_mask]
    
    # Estadísticas del merge
    final_valid = np.isfinite(merged_ndvi)
    coverage = 100 * final_valid.sum() / merged_ndvi.size
    
    print(f"[MERGE] ✓ Cobertura del día: {coverage:.2f}%")
    
    return merged_ndvi, merged_quality


def build_multi_tile_composite(items_by_date, bbox_4326, dst_transform, dst_crs, width, height):
    """
    Construye composite usando MÚLTIPLES FECHAS, cada una con MÚLTIPLES TILES.
    Solución definitiva al problema de corte.
    """
    
    print(f"\n{'='*80}")
    print(f"CONSTRUYENDO COMPOSITE MULTI-TILE")
    print(f"{'='*80}")
    
    # Arrays finales
    best_ndvi = np.full((height, width), np.nan, dtype=np.float32)
    best_score = np.zeros((height, width), dtype=np.float32)
    best_date_idx = np.zeros((height, width), dtype=np.int16)
    
    sorted_dates = sorted(items_by_date.keys(), reverse=True)  # Más recientes primero
    
    dates_processed = 0
    dates_used = 0
    total_tiles = 0
    
    for idx, date_key in enumerate(sorted_dates):
        items = items_by_date[date_key]
        total_tiles += len(items)
        
        print(f"\n[DATE {idx+1}/{len(sorted_dates)}] Procesando: {date_key} ({len(items)} tiles)")
        
        # MERGE: Combinar todas las tiles de este día
        day_ndvi, day_quality = merge_tiles_same_date(
            items, bbox_4326, dst_transform, dst_crs, width, height, date_key
        )
        
        dates_processed += 1
        
        # ¿Hay datos válidos en este día?
        valid = np.isfinite(day_ndvi)
        if not np.any(valid):
            print(f"[DATE {idx+1}] ✗ Sin datos válidos después del merge")
            continue
        
        dates_used += 1
        
        # Pesos temporales (más reciente = mejor)
        temporal_weight = 1.0 - (idx / len(sorted_dates)) * 0.3  # [1.0 ... 0.7]
        combined_score = day_quality * temporal_weight
        
        # Actualizar píxeles donde el score es mejor
        update_mask = valid & (combined_score > best_score)
        
        best_ndvi[update_mask] = day_ndvi[update_mask]
        best_score[update_mask] = combined_score[update_mask]
        best_date_idx[update_mask] = idx
        
        pixels_updated = update_mask.sum()
        print(f"[DATE {idx+1}] ✓ Píxeles actualizados en composite final: {pixels_updated:,}")
    
    # Estadísticas finales
    final_valid = np.isfinite(best_ndvi)
    coverage = 100 * final_valid.sum() / best_ndvi.size
    
    print(f"\n{'='*80}")
    print(f"ESTADÍSTICAS DE COMPOSITE")
    print(f"{'='*80}")
    print(f"Fechas procesadas:       {dates_processed}/{len(sorted_dates)}")
    print(f"Fechas con datos:        {dates_used}")
    print(f"Total tiles procesados:  {total_tiles}")
    print(f"Cobertura ANTES gaps:    {coverage:.2f}%")
    
    if coverage < 50:
        print(f"\n⚠️ ADVERTENCIA: Cobertura baja ({coverage:.1f}%)")
        print(f"   Sugerencias:")
        print(f"   - Aumentar LOOKBACK_DAYS (actual: {LOOKBACK_DAYS})")
        print(f"   - Aumentar CLOUD_MAX (actual: {CLOUD_MAX}%)")
        print(f"   - Verificar que el ROI está bien definido")
    
    # Rellenar gaps
    if FILL_LARGE_GAPS and coverage < 99:
        print(f"\n[GAPS] Rellenando gaps...")
        best_ndvi = fill_gaps_aggressive(best_ndvi, MAX_GAP_SIZE_PIXELS)
        
        coverage_after = 100 * np.isfinite(best_ndvi).sum() / best_ndvi.size
        print(f"[GAPS] Cobertura DESPUÉS gaps: {coverage_after:.2f}%")
        improvement = coverage_after - coverage
        if improvement > 0:
            print(f"[GAPS] ✓ Mejora: +{improvement:.2f}%")
    
    # Metadata
    metadata = {
        "dates_searched": len(sorted_dates),
        "dates_processed": dates_processed,
        "dates_used": dates_used,
        "total_tiles": total_tiles,
        "final_coverage_pct": float(100 * np.isfinite(best_ndvi).sum() / best_ndvi.size),
        "dates_used_list": [str(sorted_dates[i]) for i in range(dates_used)],
        "composite_method": "multi_tile_multi_date_best_pixel",
    }
    
    return best_ndvi, metadata


# ============================================================================
# MAIN
# ============================================================================

def main():
    app = create_app()
    
    with app.app_context():
        print(f"\n{'='*80}")
        print("CONFIGURACIÓN")
        print(f"{'='*80}")
        print(f"Fuente: Planetary Computer")
        print(f"Estrategia: MULTI-TILE COMPOSITE (soluciona cortes)")
        print(f"Ventana temporal: {LOOKBACK_DAYS} días")
        print(f"Cobertura nubes máx: {CLOUD_MAX}%")
        print(f"Buffer nubes: {CLOUD_BUFFER_PIXELS}px")
        print(f"Relleno gaps: {'SÍ' if FILL_LARGE_GAPS else 'NO'} (hasta {MAX_GAP_SIZE_PIXELS}px)")
        
        # ROI
        bbox = get_roi_bbox_from_gpkg()
        
        # Buscar
        items_by_date = search_planetary_computer_all_tiles(
            bbox, START_DATE, END_DATE, CLOUD_MAX, MAX_IMAGES_PER_TILE
        )
        
        if not items_by_date:
            print("\n❌ No se encontraron imágenes")
            return 1
        
        # Grid
        dst_crs = "EPSG:25830"
        width, height, dst_transform, _ = compute_grid_from_bbox_meters(
            bbox, dst_crs, NDVI_RES_M, NDVI_MAX_DIM
        )
        
        print(f"\n[GRID] {width} x {height} px | {NDVI_RES_M}m/px | {dst_crs}")
        
        # Composite
        composite, meta = build_multi_tile_composite(
            items_by_date, bbox, dst_transform, dst_crs, width, height
        )
        
        if composite is None:
            print("\n❌ Fallo al crear composite")
            return 1
        
        # Estadísticas
        valid = composite[np.isfinite(composite)]
        
        print(f"\n{'='*80}")
        print("ESTADÍSTICAS FINALES")
        print(f"{'='*80}")
        print(f"  NDVI min:     {valid.min():.3f}")
        print(f"  NDVI max:     {valid.max():.3f}")
        print(f"  NDVI mean:    {valid.mean():.3f}")
        print(f"  NDVI median:  {np.median(valid):.3f}")
        print(f"  Std dev:      {valid.std():.3f}")
        
        # Guardar
        static_ndvi_dir = Path(app.root_path) / "static" / "ndvi"
        static_ndvi_dir.mkdir(parents=True, exist_ok=True)
        
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        
        tif_utm = static_ndvi_dir / f"ndvi_multitile_{ts}_utm.tif"
        tif_3857 = static_ndvi_dir / f"ndvi_multitile_{ts}_3857.tif"
        png = static_ndvi_dir / f"ndvi_multitile_{ts}.png"
        json_file = static_ndvi_dir / f"ndvi_multitile_{ts}.json"
        
        print(f"\n{'='*80}")
        print("GUARDANDO ARCHIVOS")
        print(f"{'='*80}")
        
        # GeoTIFF UTM
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
        
        with rasterio.open(str(tif_utm), "w", **profile) as dst:
            dst.write(composite.astype(np.float32), 1)
        print(f"[✓] {tif_utm.name}")
        
        # 3857
        warp_tif_to_3857(str(tif_utm), str(tif_3857))
        print(f"[✓] {tif_3857.name}")
        
        # PNG
        rgba = ndvi_to_rgba(composite)
        Image.fromarray(rgba, mode="RGBA").save(str(png), format="PNG", optimize=True)
        print(f"[✓] {png.name}")
        
        # JSON metadata
        with rasterio.open(str(tif_3857)) as ds:
            b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
            minx, miny, maxx, maxy = map(float, b)
        
        metadata_full = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "type": "ndvi_composite_multi_tile",
            "source": "Planetary Computer",
            "temporal_window": {
                "start": START_DATE.strftime("%Y-%m-%d"),
                "end": END_DATE.strftime("%Y-%m-%d"),
                "days": LOOKBACK_DAYS,
            },
            "processing": {
                "version": "Multi-Tile Composite v2.0",
                "strategy": "merge_tiles_per_date_then_composite",
                "cloud_masking": "SCL with buffer",
                "cloud_buffer_px": CLOUD_BUFFER_PIXELS,
                "gap_filling": FILL_LARGE_GAPS,
                "max_gap_size_px": MAX_GAP_SIZE_PIXELS,
            },
            "composite_stats": meta,
            "bbox_4326": [minx, miny, maxx, maxy],
            "grid": {"width": width, "height": height, "res_m": NDVI_RES_M},
            "crs": dst_crs,
            "statistics": {
                "min": float(valid.min()),
                "max": float(valid.max()),
                "mean": float(valid.mean()),
                "median": float(np.median(valid)),
                "std": float(valid.std()),
            },
            "files": {
                "utm_tif": tif_utm.name,
                "epsg3857_tif": tif_3857.name,
                "png": png.name,
                "metadata": json_file.name,
            }
        }
        
        json_file.write_text(json.dumps(metadata_full, indent=2), encoding="utf-8")
        print(f"[✓] {json_file.name}")
        
        # DB
        print(f"\n{'='*80}")
        print("GUARDANDO EN BBDD")
        print(f"{'='*80}")
        
        try:
            sql = text("""
                INSERT INTO public.imagenes
                  (origen, fecha_adquisicion, epsg, sensor, resolucion_m, bbox, ruta_archivo)
                VALUES
                  (:origen, :fecha, :epsg, :sensor, :res, 
                   ST_MakeEnvelope(:minx,:miny,:maxx,:maxy,4326), :ruta)
                RETURNING id_imagen
            """)
            
            ruta_rel = str(Path("static") / "ndvi" / tif_utm.name)
            
            most_recent = max([datetime.strptime(d, "%Y-%m-%d") for d in meta["dates_used_list"][:5]])
            
            sensor = (
                f"Sentinel-2 NDVI Multi-Tile Composite | "
                f"{meta['dates_used']} fechas, {meta['total_tiles']} tiles | "
                f"Cobertura: {meta['final_coverage_pct']:.1f}%"
            )
            
            id_img = db.session.execute(sql, {
                "origen": "satelite",
                "fecha": most_recent.date(),
                "epsg": int(dst_crs.split(':')[1]),
                "sensor": sensor,
                "res": float(NDVI_RES_M),
                "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy,
                "ruta": ruta_rel,
            }).scalar()
            
            db.session.commit()
            
            print(f"[✓] Insertado en public.imagenes (ID: {id_img})")
        
        except Exception as e:
            db.session.rollback()
            print(f"[✗] Error BBDD: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"\n{'='*80}")
        print("✅ PROCESO COMPLETADO")
        print(f"{'='*80}")
        print(f"\n🎯 SOLUCIÓN AL PROBLEMA DE CORTE:")
        print(f"   ✓ Búsqueda en TODAS las tiles que cubren el ROI")
        print(f"   ✓ Merge de tiles del mismo día")
        print(f"   ✓ Composite multi-temporal")
        print(f"   ✓ Relleno de gaps")
        print(f"   ✓ Cobertura final: {meta['final_coverage_pct']:.1f}%")
        
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        raise SystemExit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️ Cancelado por usuario")
        raise SystemExit(1)
    except Exception as e:
        print(f"\n{'='*80}")
        print("❌ ERROR FATAL")
        print(f"{'='*80}")
        print(f"{e}")
        import traceback
        traceback.print_exc()
        raise SystemExit(1)