"""
Generador de imágenes NDVI simples - SOLO NDVI ALTO
Sin título, sin barra de color - solo la imagen NDVI con contorno
"""

import os
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from shapely import wkb
from shapely.ops import transform as shapely_transform
from shapely.geometry import mapping
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
from matplotlib.patches import Polygon as MPLPolygon
import psycopg2
from pyproj import Transformer
from scipy.ndimage import gaussian_filter

# CONFIGURACIÓN
DB_CONFIG = {
    'dbname': 'gisdb',
    'user': 'postgres',
    'password': 'postgres',
    'host': 'localhost',
    'port': '5432'
}

OUTPUT_DIR = 'static/ndvi_simple'
NDVI_BASE = './webapp/static/ndvi/ndvi_latest_utm.tif'
NDVI_MINIMO = 0.5  # Solo recintos con NDVI > 0.5


def rellenar_ndvi_completo(ndvi_array):
    """Rellena NaN"""
    filled = ndvi_array.copy()
    
    if not np.any(~np.isnan(filled)):
        return np.full_like(filled, 0.3)
    
    media = np.nanmean(filled)
    filled[np.isnan(filled)] = media
    filled = gaussian_filter(filled, sigma=1.5)
    
    return filled


def generar_imagen_ndvi_simple(ndvi_data, geometria, id_recinto, output_path, dpi=150):
    """
    Genera imagen NDVI - sin título, sin barra, CON contorno
    """
    ndvi_relleno = rellenar_ndvi_completo(ndvi_data)
    
    # Crear figura sin márgenes
    fig, ax = plt.subplots(figsize=(6, 6), dpi=dpi, facecolor='white')
    ax.axis('off')
    
    # COLORMAP
    colors = [
        '#000000', '#a50026', '#d73027', '#f46d43', 
        '#fdae61', '#fee08b', '#ffffbf', '#d9ef8b', 
        '#a6d96a', '#66bd63', '#1a9850', '#006837',
    ]
    boundaries = [-0.2, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    
    cmap = LinearSegmentedColormap.from_list('ndvi', colors, N=len(colors))
    norm = BoundaryNorm(boundaries, len(colors))
    
    bounds = geometria.bounds
    im = ax.imshow(
        ndvi_relleno,
        cmap=cmap,
        norm=norm,
        extent=[bounds[0], bounds[2], bounds[1], bounds[3]],
        interpolation='nearest',
        aspect='auto',
        zorder=1
    )
    
    # CLIP PATH
    if geometria.geom_type == 'Polygon':
        coords = list(geometria.exterior.coords)
        patch = MPLPolygon(coords, facecolor='none', edgecolor='none', closed=True)
        ax.add_patch(patch)
        im.set_clip_path(patch)
    elif geometria.geom_type == 'MultiPolygon':
        for poly in geometria.geoms:
            coords = list(poly.exterior.coords)
            patch = MPLPolygon(coords, facecolor='none', edgecolor='none', closed=True)
            ax.add_patch(patch)
            im.set_clip_path(patch)
            break
    
    # CONTORNO NEGRO
    if geometria.geom_type == 'Polygon':
        x, y = geometria.exterior.xy
        ax.plot(x, y, color='black', linewidth=2, alpha=0.8, zorder=3)
    elif geometria.geom_type == 'MultiPolygon':
        for poly in geometria.geoms:
            x, y = poly.exterior.xy
            ax.plot(x, y, color='black', linewidth=2, alpha=0.8, zorder=3)
    
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect('equal')
    
    # GUARDAR
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight', 
                pad_inches=0.1, facecolor='white')
    plt.close()
    
    return float(np.nanmean(ndvi_data))


def procesar_recinto(id_recinto):
    """Procesa un recinto"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    query = "SELECT geom, nombre FROM recintos WHERE id_recinto = %s"
    cursor.execute(query, (id_recinto,))
    result = cursor.fetchone()
    
    if not result:
        cursor.close()
        conn.close()
        return None
    
    geom_wkb, nombre = result
    
    if isinstance(geom_wkb, str):
        geom_wkb = bytes.fromhex(geom_wkb)
    geometria = wkb.loads(geom_wkb)
    
    geom_srid = 4326
    try:
        import struct
        if len(geom_wkb) > 8:
            srid_bytes = geom_wkb[5:9]
            geom_srid = struct.unpack('<I', srid_bytes)[0]
    except:
        pass
    
    cursor.close()
    conn.close()
    
    if not os.path.exists(NDVI_BASE):
        return None
    
    with rasterio.open(NDVI_BASE) as src:
        raster_crs = src.crs.to_epsg()
        
        if geom_srid != raster_crs:
            transformer = Transformer.from_crs(
                f"EPSG:{geom_srid}",
                f"EPSG:{raster_crs}",
                always_xy=True
            )
            geometria = shapely_transform(transformer.transform, geometria)
        
        minx, miny, maxx, maxy = geometria.bounds
        buffer = max((maxx - minx), (maxy - miny)) * 0.15
        
        window = from_bounds(
            minx - buffer, miny - buffer,
            maxx + buffer, maxy + buffer,
            src.transform
        )
        
        ndvi_data = src.read(1, window=window)
    
    # VALIDAR que hay datos válidos
    if not np.any(~np.isnan(ndvi_data)):
        print(f"  ⊘ Sin datos válidos (fuera del raster o todo NaN)")
        return None  # ← CAMBIO: retornar None en lugar de calcular
    
    ndvi_medio = float(np.nanmean(ndvi_data))
    
    # VALIDAR que el NDVI medio es válido
    if np.isnan(ndvi_medio):
        print(f"  ⊘ NDVI inválido (NaN)")
        return None
    
    # FILTRAR por NDVI
    if ndvi_medio < NDVI_MINIMO:
        return ndvi_medio
    
    # GENERAR IMAGEN
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_png = os.path.join(OUTPUT_DIR, f"{id_recinto}.png")
    
    ndvi_final = generar_imagen_ndvi_simple(ndvi_data, geometria, id_recinto, output_png)
    
    print(f"  ✓ Imagen guardada: {output_png} | NDVI: {ndvi_final:.3f}")
    
    return ndvi_final

def procesar_todos():
    """Procesa todos los recintos con NDVI alto"""
    print("="*60)
    print(f"GENERADOR DE IMÁGENES NDVI (NDVI > {NDVI_MINIMO})")
    print("="*60)
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    query = "SELECT id_recinto, nombre FROM recintos ORDER BY id_recinto"
    cursor.execute(query)
    recintos = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    total = len(recintos)
    print(f"\n✓ Total: {total} recintos")
    
    exitosos = 0
    filtrados = 0
    errores = 0
    
    for idx, (id_recinto, nombre) in enumerate(recintos, 1):
        print(f"[{idx}/{total}] {id_recinto}: {nombre}")
        
        try:
            ndvi = procesar_recinto(id_recinto)
            
            if ndvi is None:
                errores += 1
            elif ndvi >= NDVI_MINIMO:
                exitosos += 1
            else:
                filtrados += 1
                print(f"  ⊘ Filtrado (NDVI={ndvi:.3f})")
                
        except Exception as e:
            errores += 1
            print(f"  ✗ ERROR: {e}")
    
    print("\n" + "="*60)
    print("RESUMEN")
    print("="*60)
    print(f"Imágenes generadas: {exitosos}")
    print(f"Filtrados (NDVI bajo): {filtrados}")
    print(f"Errores: {errores}")
    print(f"Directorio: {OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        procesar_todos()
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()