"""
Generador de Thumbnail NDVI - VERSIÓN ORGANIZADA POR FECHAS
✓ Solo genera thumbnails si el recinto tiene datos NDVI reales
✓ NO rellena recintos vacíos con color uniforme
✓ Fondo transparente
✓ Borde negro
✓ Recorte exacto
✓ NUEVO: Organiza thumbnails en subcarpetas por fecha (YYYYMMDD)
✓ COLORES DISCRETOS: Usa el mismo método que ndvi_diax.py y ndvi_completo.py
"""

import os
import sys
import json
import numpy as np
import rasterio
from rasterio.windows import Window
from shapely import wkb
from shapely.ops import transform as shapely_transform
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as mpatches
# ── CAMBIO: sustituido psycopg2 por SQLAlchemy ──────────────────────────────
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from webapp.config import Config
# ────────────────────────────────────────────────────────────────────────────
from pyproj import Transformer
from scipy.ndimage import gaussian_filter
import gc
from datetime import datetime

# ==================== CONFIGURACIÓN ====================

# ── CAMBIO: motor SQLAlchemy en lugar de DB_CONFIG dict ─────────────────────
engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)
# ────────────────────────────────────────────────────────────────────────────

# Directorio base de thumbnails (ahora se crearán subcarpetas por fecha)
THUMBNAILS_BASE_DIR = 'webapp/static/thumbnails'

# Archivos NDVI de entrada
NDVI_BASE = '../data/processed/ndvi_composite/ndvi_pc_20260316_mosaic_3857.tif'
NDVI_META = '../data/processed/ndvi_composite/ndvi_pc_20260316_mosaic.json'

START_FROM_ID = 0
SKIP_EXISTING = True
LOG_INTERVAL = 1000
IMAGE_PADDING = 0.0

MIN_VALID_PIXELS_PERCENT = 5.0  

RASTER_CACHE = None
TRANSFORMER_CACHE = {}

# ==================== FECHA NDVI ====================
def get_ndvi_date_from_json():
    """Extrae la fecha del NDVI desde el archivo metadata JSON"""
    if not os.path.exists(NDVI_META):
        return datetime.now().strftime("%Y%m%d")

    with open(NDVI_META, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    if meta.get('ndvi_date_formatted'):
        return meta['ndvi_date_formatted']

    for key in ['ndvi_date', 'updated_utc']:
        if meta.get(key):
            dt = datetime.fromisoformat(meta[key].replace('Z', '+00:00'))
            return dt.strftime("%Y%m%d")

    return datetime.now().strftime("%Y%m%d")


NDVI_DATE_STR = get_ndvi_date_from_json()

# *** NUEVO: Crear directorio de salida específico para esta fecha ***
OUTPUT_DIR = os.path.join(THUMBNAILS_BASE_DIR, NDVI_DATE_STR)

# ==================== CACHE RASTER ====================
def cargar_raster_en_memoria():
    global RASTER_CACHE

    if RASTER_CACHE is not None:
        return RASTER_CACHE

    print("📦 Cargando raster NDVI en memoria...")

    with rasterio.open(NDVI_BASE) as src:
        RASTER_CACHE = {
            'data': src.read(1),
            'transform': src.transform,
            'crs': src.crs.to_epsg(),
            'width': src.width,
            'height': src.height
        }

    return RASTER_CACHE


def get_transformer(geom_srid, raster_crs):
    key = (geom_srid, raster_crs)
    if key not in TRANSFORMER_CACHE:
        TRANSFORMER_CACHE[key] = Transformer.from_crs(
            f"EPSG:{geom_srid}",
            f"EPSG:{raster_crs}",
            always_xy=True
        )
    return TRANSFORMER_CACHE[key]

# ==================== RELLENO INTELIGENTE DE NaN ====================
def rellenar_ndvi_inteligente(ndvi_array):
    """
    ✓ Solo rellena NaN si hay suficientes datos válidos
    ✓ Si menos del 5% son válidos → devuelve None (no generar thumbnail)
    ✓ Si hay datos → rellena huecos pequeños con interpolación
    """
    total_pixels = ndvi_array.size
    valid_pixels = np.sum(~np.isnan(ndvi_array))
    valid_percent = (valid_pixels / total_pixels) * 100
    
    # Filtro principal: Si casi todo es NaN, no generar thumbnail
    if valid_percent < MIN_VALID_PIXELS_PERCENT:
        return None
    
    # Si hay suficientes datos, rellenar huecos pequeños
    filled = ndvi_array.copy()
    media = np.nanmean(filled)
    
    # Solo rellenar NaN, no cambiar valores válidos
    nan_mask = np.isnan(filled)
    filled[nan_mask] = media
    
    # Suavizar solo las áreas rellenadas para que se integren mejor
    if np.any(nan_mask):
        filled = gaussian_filter(filled, sigma=1.0)
    
    return filled


# ==================== CONVERSIÓN NDVI A RGBA DISCRETA ====================
def ndvi_to_rgba_discrete(ndvi):
    """
    Convertir NDVI a imagen RGBA usando el MISMO MÉTODO que ndvi_diax.py y ndvi_completo.py
    
    MÉTODO DISCRETO: Asignación directa de colores por rangos (sin gradientes)
    """
    h, w = ndvi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid = np.isfinite(ndvi)
    
    if not np.any(valid):
        return rgba

    # MISMOS RANGOS Y COLORES que los scripts de procesamiento
    # los he sacao de aqui no se si estan bien https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/ndvi-on-vegetation-natural_colours/
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
    
    # Valores por debajo de -0.2 → negro
    rgba[valid & (ndvi < -0.2)] = [0, 0, 0, 255]
    
    # Asignar color DISCRETO para cada rango
    for vmin, vmax, color in ranges_colors:
        mask = valid & (ndvi >= vmin) & (ndvi < vmax)
        if np.any(mask):
            rgba[mask] = [*color, 255]  # Color sólido para todo el rango
    
    # Valores >= 1.0 → verde oscuro
    rgba[valid & (ndvi >= 1.0)] = [0, 104, 55, 255]
    
    # Transparente donde no hay datos
    rgba[~valid, 3] = 0
    
    return rgba


# 
def extraer_ventana_raster(geometria, padding=0.0):
    """Extrae ventana del raster"""
    raster = RASTER_CACHE

    minx, miny, maxx, maxy = geometria.bounds

    transform = raster['transform']
    col_start, row_start = ~transform * (minx, maxy)
    col_end, row_end = ~transform * (maxx, miny)

    col_start = max(0, int(col_start))
    row_start = max(0, int(row_start))
    col_end = min(raster['width'], int(col_end) + 1)
    row_end = min(raster['height'], int(row_end) + 1)

    if col_end <= col_start or row_end <= row_start:
        return None, None

    window_data = raster['data'][row_start:row_end, col_start:col_end]

    window_transform = rasterio.windows.transform(
        Window(col_start, row_start, col_end - col_start, row_end - row_start),
        transform
    )

    return window_data, window_transform


# ==================== EXTRAER POLÍGONOS ====================
def get_polygons_from_geometry(geometria):
    """Extrae lista de polígonos de cualquier geometría"""
    if geometria.geom_type == 'Polygon':
        return [geometria]
    elif geometria.geom_type == 'MultiPolygon':
        return list(geometria.geoms)
    else:
        return []


# el DPI hace que las imagenes se generen mas grandes y a major calidad, 100 o asi esta bien, pero tarda mcho, para probar bajar
def generar_thumbnail_optimizado(ndvi_data, window_transform, geometria, output_path, dpi=75):
    """
    Genera thumbnail con colores DISCRETOS (no gradientes)
    mismo metodo que ndvi_diax.py y ndvi_completo.py creo
    """

    # Verificar datos válidos ANTES de generar imagen
    ndvi_filled = rellenar_ndvi_inteligente(ndvi_data)
    
    if ndvi_filled is None:
        # No hay suficientes datos válidos, no generar thumbnail
        return None
    
    # Procesar con datos válidos
    ndvi_clean = np.clip(ndvi_filled, -0.2, 1.0)

    # *** NUEVA LÓGICA: Convertir NDVI a RGBA usando método discreto ***
    rgba_image = ndvi_to_rgba_discrete(ndvi_clean)

    # FONDO TRANSPARENTE
    fig, ax = plt.subplots(figsize=(6, 6), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)

    # EXTENT REAL DEL RASTER
    h, w = ndvi_clean.shape
    xmin = window_transform.c
    xmax = xmin + window_transform.a * w
    ymax = window_transform.f
    ymin = ymax + window_transform.e * h

    # mostrar imagen RGBA directamente sin leyenda ni hostias  ***
    im = ax.imshow(
        rgba_image,
        extent=[xmin, xmax, ymin, ymax],
        interpolation='nearest',  # Sin interpolación para mantener colores discretos
        zorder=1
    )

    # MÁSCARA PARA RECORTAR EXACTAMENTE AL RECINTO
    polygons = get_polygons_from_geometry(geometria)
    
    if len(polygons) > 0:
        all_verts = []
        all_codes = []
        
        for poly in polygons:
            coords = np.array(poly.exterior.coords)
            codes = [Path.MOVETO] + [Path.LINETO] * (len(coords) - 2) + [Path.CLOSEPOLY]
            all_verts.append(coords)
            all_codes.extend(codes)
        
        combined_verts = np.vstack(all_verts)
        combined_path = Path(combined_verts, all_codes)
        
        clip_patch = mpatches.PathPatch(
            combined_path,
            facecolor='none',
            edgecolor='none',
            transform=ax.transData
        )
        ax.add_patch(clip_patch)
        im.set_clip_path(clip_patch)

    # CONTORNO NEGRO
    for poly in polygons:
        x, y = poly.exterior.xy
        ax.plot(x, y, color='black', linewidth=1.5, zorder=3)

    # LÍMITES EXACTOS
    minx_plot, miny_plot, maxx_plot, maxy_plot = geometria.bounds
    ax.set_xlim(minx_plot, maxx_plot)
    ax.set_ylim(miny_plot, maxy_plot)

    ax.axis('off')
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    
    plt.savefig(
        output_path, 
        dpi=dpi, 
        bbox_inches='tight', 
        pad_inches=0,
        transparent=True,
        facecolor='none'
    )
    plt.close(fig)

    del fig, ax, ndvi_filled, ndvi_clean, rgba_image

    # Calcular media de valores ORIGINALES válidos
    valid_mask = ~np.isnan(ndvi_data) & np.isfinite(ndvi_data)
    if np.any(valid_mask):
        return float(np.mean(ndvi_data[valid_mask]))
    else:
        return None


# ==================== RECINTO ====================
def procesar_recinto_optimizado(id_recinto, geom_wkb):
    """
    Procesa un recinto y genera su thumbnail.
    ruta a la carpeta de la fecha
    Formato: webapp/static/thumbnails/YYYYMMDD/{id_recinto}.png
    """
    # *** Nombre sin fecha, solo ID del recinto ***
    output_png = os.path.join(OUTPUT_DIR, f"{id_recinto}.png")
    
    if SKIP_EXISTING and os.path.exists(output_png):
        return 'skipped'

    if isinstance(geom_wkb, str):
        geom_wkb = bytes.fromhex(geom_wkb)

    geometria = wkb.loads(geom_wkb)

    raster_crs = RASTER_CACHE['crs']
    geom_srid = 4326

    if geom_srid != raster_crs:
        transformer = get_transformer(geom_srid, raster_crs)
        geometria = shapely_transform(transformer.transform, geometria)

    ndvi_data, window_transform = extraer_ventana_raster(geometria)

    if ndvi_data is None:
        return 'no_overlap'

    # generar_thumbnail devuelve None si no hay datos suficientes
    result = generar_thumbnail_optimizado(ndvi_data, window_transform, geometria, output_png)
    
    if result is None:
        return 'insufficient_data'
    
    return 'success'


# ==================== MAIN ====================
if __name__ == "__main__":

    if not os.path.exists(NDVI_BASE):
        print("✗ Raster NDVI no encontrado")
        sys.exit(1)

    cargar_raster_en_memoria()
    
    # Crear directorio de salida para esta fecha
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print(f"\n{'='*70}")
    print(f"GENERADOR DE THUMBNAILS NDVI - COLORES DISCRETOS")
    print(f"{'='*70}")
    print(f"✓ Fecha NDVI: {NDVI_DATE_STR}")
    print(f"✓ Directorio de salida: {OUTPUT_DIR}")
    print(f"✓ Método de colores: DISCRETO (igual que scripts de procesamiento)")
    print(f"✓ Umbral mínimo de datos válidos: {MIN_VALID_PIXELS_PERCENT}%")

    # ── CAMBIO: sesión SQLAlchemy en lugar de psycopg2.connect + cursor ──────
    session = Session()
    resultado = session.execute(
        text("SELECT id_recinto, geom FROM recintos WHERE id_recinto >= :start ORDER BY id_recinto"),
        {"start": START_FROM_ID}
    )
    recintos = resultado.fetchall()
    session.close()
    # ─────────────────────────────────────────────────────────────────────────

    total = len(recintos)
    print(f"✓ Recintos a procesar: {total}")

    # Contadores
    stats = {
        'success': 0,
        'skipped': 0,
        'no_overlap': 0,
        'insufficient_data': 0,
        'error': 0
    }

    for idx, (id_recinto, geom_wkb) in enumerate(recintos, 1):

        try:
            result = procesar_recinto_optimizado(id_recinto, geom_wkb)
            stats[result] = stats.get(result, 0) + 1
        except Exception as e:
            print(f"Error en recinto {id_recinto}: {e}")
            stats['error'] += 1
            continue

        if idx % LOG_INTERVAL == 0 or idx == total:
            print(f"\n{idx}/{total} procesados")
            print(f"  ✓ Exitosos: {stats['success']}")
            print(f"  ⊘ Sin datos suficientes: {stats['insufficient_data']}")
            print(f"  ⊘ Sin solapamiento: {stats['no_overlap']}")
            print(f"  → Omitidos (ya existen): {stats['skipped']}")
            print(f"  ✗ Errores: {stats['error']}")

        if idx % 500 == 0:
            gc.collect()

    print("\n" + "="*70)
    print("✓ PROCESO TERMINADO")
    print("="*70)
    print(f"Total procesados: {total}")
    print(f"Thumbnails generados: {stats['success']}")
    print(f"Recintos sin datos NDVI válidos: {stats['insufficient_data'] + stats['no_overlap']}")
    print(f"Ya existentes (omitidos): {stats['skipped']}")
    print(f"Errores: {stats['error']}")
    print(f"\n📁 Thumbnails guardados en: {OUTPUT_DIR}")