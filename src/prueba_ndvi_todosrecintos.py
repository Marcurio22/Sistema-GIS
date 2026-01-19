"""
Generador de Thumbnail NDVI - TODOS LOS RECINTOS
Colores exactos de la tabla proporcionada
"""

import os
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from shapely import wkb
from shapely.ops import transform as shapely_transform
from shapely.geometry import mapping, box
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

OUTPUT_DIR = 'static/thumbnails'
NDVI_BASE = './webapp/static/ndvi/ndvi_latest_utm.tif'


def rellenar_ndvi_completo(ndvi_array):
    """
    Rellena TODOS los NaN - AGRESIVO
    """
    filled = ndvi_array.copy()
    
    # Si no hay valores válidos, devolver array de 0.3
    if not np.any(~np.isnan(filled)):
        return np.full_like(filled, 0.3)
    
    # Paso 1: Rellenar NaN con media de válidos
    media = np.nanmean(filled)
    filled[np.isnan(filled)] = media
    
    # Paso 2: Suavizar con gaussian
    filled = gaussian_filter(filled, sigma=1.5)
    
    return filled


def generar_thumbnail_ndvi(ndvi_data, geometria, nombre, id_recinto,output_path, dpi=150):
    """
    Genera thumbnail limpio SIN píxeles blancos
    Método: todo relleno + clip visual con el polígono
    """
    print(f"\nGenerando thumbnail NDVI...")
    print(f"  Shape original: {ndvi_data.shape}")
    print(f"  NaN originales: {np.isnan(ndvi_data).sum()}")
    
    # 1. RELLENAR TODO (no queda ningún NaN)
    ndvi_relleno = rellenar_ndvi_completo(ndvi_data)
    print(f"  NaN después relleno: {np.isnan(ndvi_relleno).sum()}")
    
    # 2. CREAR FIGURA
    fig, ax = plt.subplots(figsize=(6, 6), dpi=dpi, facecolor='white')
    
    # 3. COLORMAP NDVI - TABLA EXACTA
    colors = [
        '#000000',  # Negro (NDVI < -0.2)
        '#a50026',  # Rojo oscuro (-0.2 a 0)
        '#d73027',  # Rojo (0 a 0.1)
        '#f46d43',  # Naranja (0.1 a 0.2)
        '#fdae61',  # Naranja claro (0.2 a 0.3)
        '#fee08b',  # Amarillo (0.3 a 0.4)
        '#ffffbf',  # Amarillo claro (0.4 a 0.5)
        '#d9ef8b',  # Verde amarillo (0.5 a 0.6)
        '#a6d96a',  # Verde claro (0.6 a 0.7)
        '#66bd63',  # Verde (0.7 a 0.8)
        '#1a9850',  # Verde oscuro (0.8 a 0.9)
        '#006837',  # Verde muy oscuro (0.9 a 1.0)
    ]
    
    # Límites exactos según la tabla
    boundaries = [-0.2, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    
    cmap = LinearSegmentedColormap.from_list('ndvi_tabla', colors, N=len(colors))
    norm = BoundaryNorm(boundaries, len(colors))
    
    # 4. PLOTEAR (sin NaN, todo tiene color)
    bounds = geometria.bounds
    im = ax.imshow(
        ndvi_relleno,
        cmap=cmap,
        norm=norm,
        extent=[bounds[0], bounds[2], bounds[1], bounds[3]],
        interpolation='nearest',  # PIXELADO - se ven los píxeles individuales
        aspect='auto',
        zorder=1
    )
    
    # 5. APLICAR CLIP_PATH para recortar visualmente
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
    
    # 6. DIBUJAR CONTORNO
    if geometria.geom_type == 'Polygon':
        x, y = geometria.exterior.xy
        ax.plot(x, y, color='black', linewidth=2, alpha=0.8, zorder=3)
    elif geometria.geom_type == 'MultiPolygon':
        for poly in geometria.geoms:
            x, y = poly.exterior.xy
            ax.plot(x, y, color='black', linewidth=2, alpha=0.8, zorder=3)
    
    # 7. CONFIGURACIÓN
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect('equal')
    ax.axis('off')
    
    # 8. TÍTULO
    mean_ndvi = float(np.nanmean(ndvi_data))
    titulo = f"ID: {id_recinto} - {nombre}\nNDVI: {mean_ndvi:.2f}"
    ax.text(0.5, 1.02, titulo, transform=ax.transAxes,
            ha='center', va='bottom', fontsize=11, weight='bold')
    
    # 9. BARRA DE COLOR
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('NDVI', rotation=270, labelpad=15, fontsize=10)
    
    # 10. GUARDAR
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight',
                facecolor='white', pad_inches=0.1)
    plt.close()
    
    print(f"✓ Thumbnail guardado: {output_path}")
    
    return {
        'mean': mean_ndvi,
        'min': float(np.nanmin(ndvi_data)),
        'max': float(np.nanmax(ndvi_data)),
    }


def procesar_recinto(id_recinto):
    """
    Proceso para UN recinto individual
    """
    # 1. OBTENER GEOMETRÍA
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    query = "SELECT geom, nombre, superficie_ha FROM recintos WHERE id_recinto = %s"
    cursor.execute(query, (id_recinto,))
    result = cursor.fetchone()
    
    if not result:
        cursor.close()
        conn.close()
        raise ValueError(f"Recinto {id_recinto} no encontrado")
    
    geom_wkb, nombre, superficie = result
    
    # Convertir WKB
    if isinstance(geom_wkb, str):
        geom_wkb = bytes.fromhex(geom_wkb)
    geometria = wkb.loads(geom_wkb)
    
    # SRID
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
    
    # 2. LEER RASTER
    if not os.path.exists(NDVI_BASE):
        raise FileNotFoundError(f"NDVI no encontrado: {NDVI_BASE}")
    
    with rasterio.open(NDVI_BASE) as src:
        # Reproyectar geometría
        raster_crs = src.crs.to_epsg()
        
        if geom_srid != raster_crs:
            transformer = Transformer.from_crs(
                f"EPSG:{geom_srid}",
                f"EPSG:{raster_crs}",
                always_xy=True
            )
            geometria = shapely_transform(transformer.transform, geometria)
        
        # Leer ventana del BBOX
        minx, miny, maxx, maxy = geometria.bounds
        
        # Añadir pequeño buffer
        buffer = max((maxx - minx), (maxy - miny)) * 0.15
        window = from_bounds(
            minx - buffer, miny - buffer,
            maxx + buffer, maxy + buffer,
            src.transform
        )
        
        # Leer datos de la ventana
        ndvi_data = src.read(1, window=window)
    
    # 3. GENERAR THUMBNAIL
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Usar ID en el nombre para evitar conflictos
    nombre_limpio = f"{id_recinto}_{nombre}".replace('/', '_').replace('\\', '_')[:100]
    output_png = os.path.join(OUTPUT_DIR, f"ndvi_{nombre_limpio}.png")
    
    stats = generar_thumbnail_ndvi(ndvi_data, geometria, nombre, id_recinto, output_png)
    
    print(f"  ✓ Thumbnail guardado | NDVI medio: {stats['mean']:.3f}")


def procesar_todos_los_recintos():
    """
    Procesa TODOS los recintos y genera thumbnails
    """
    print("="*60)
    print("GENERADOR DE THUMBNAILS NDVI - TODOS LOS RECINTOS")
    print("="*60)
    
    # 1. OBTENER TODOS LOS RECINTOS
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    query = "SELECT id_recinto, nombre, superficie_ha FROM recintos ORDER BY id_recinto"
    cursor.execute(query)
    recintos = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    total = len(recintos)
    print(f"\n✓ Total de recintos a procesar: {total}")
    
    # Contadores
    exitosos = 0
    errores = 0
    
    # 2. PROCESAR CADA RECINTO
    for idx, (id_recinto, nombre, superficie) in enumerate(recintos, 1):
        print(f"\n[{idx}/{total}] Procesando recinto {id_recinto}: {nombre}")
        
        try:
            procesar_recinto(id_recinto)
            exitosos += 1
        except Exception as e:
            errores += 1
            print(f"  ✗ ERROR: {e}")
            continue
    
    # 3. RESUMEN FINAL
    print("\n" + "="*60)
    print("RESUMEN FINAL")
    print("="*60)
    print(f"Total procesados: {total}")
    print(f"Exitosos: {exitosos}")
    print(f"Errores: {errores}")
    print(f"Directorio de salida: {OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        # PROCESAR TODOS LOS RECINTOS
        procesar_todos_los_recintos()
    except Exception as e:
        print(f"\n✗ ERROR GENERAL: {e}")
        import traceback
        traceback.print_exc()