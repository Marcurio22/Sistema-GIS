"""
Generador de Thumbnail NDVI - MÉTODO DEFINITIVO
Lee el BBOX completo, rellena TODO, luego enmascara
"""

import os
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from shapely import wkb
from shapely.ops import transform as shapely_transform
from shapely.geometry import mapping, box
from rasterio.features import rasterize
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
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

ID_RECINTO = 289269
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


def generar_thumbnail_ndvi(ndvi_data, geometria, nombre, output_path, dpi=150):
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
    
    # 3. COLORMAP NDVI
    colors = [
        '#a40026',  # Rojo oscuro
        '#d63027',  # Rojo
        '#f46d43',  # Naranja
        '#fdae61',  # Naranja claro
        '#fede8f',  # Amarillo claro
        '#fffebd',  # Amarillo muy claro
        '#d9ef8b',  # Verde amarillento
        '#9ed569',  # Verde claro
    ]
    cmap = LinearSegmentedColormap.from_list('ndvi', colors, N=256)
    
    # 4. PLOTEAR (sin NaN, todo tiene color)
    bounds = geometria.bounds
    im = ax.imshow(
        ndvi_relleno,
        cmap=cmap,
        vmin=-0.2,
        vmax=0.9,
        extent=[bounds[0], bounds[2], bounds[1], bounds[3]],
        interpolation='nearest',  # PIXELADO - se ven los píxeles individuales
        aspect='auto',
        zorder=1
    )
    
    # 5. CREAR MÁSCARA BLANCA PARA OCULTAR LO DE FUERA
    # Convertir bounds a coordenadas de la imagen
    minx, miny, maxx, maxy = bounds
    
    # Crear polígono de recorte (INVERTIDO para ocultar exterior)
    # Polígono grande (todo) menos polígono del recinto = área a ocultar
    exterior_box = box(minx - (maxx-minx)*0.1, 
                       miny - (maxy-miny)*0.1,
                       maxx + (maxx-minx)*0.1, 
                       maxy + (maxy-miny)*0.1)
    
    # Aplicar clip_path para que solo se vea el interior del recinto
    if geometria.geom_type == 'Polygon':
        coords = list(geometria.exterior.coords)
        patch = MPLPolygon(coords, facecolor='none', edgecolor='none', closed=True)
        ax.add_patch(patch)
        im.set_clip_path(patch)
    elif geometria.geom_type == 'MultiPolygon':
        # Para MultiPolygon, usar el primero o combinar
        for poly in geometria.geoms:
            coords = list(poly.exterior.coords)
            patch = MPLPolygon(coords, facecolor='none', edgecolor='none', closed=True)
            ax.add_patch(patch)
            im.set_clip_path(patch)
            break  # Solo el primero por simplicidad
    
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
    titulo = f"{nombre}\nNDVI: {mean_ndvi:.2f}"
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
    Proceso completo
    """
    print("="*60)
    print("GENERADOR DE THUMBNAIL NDVI")
    print("="*60)
    
    # 1. OBTENER GEOMETRÍA
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    query = "SELECT geom, nombre, superficie_ha FROM recintos WHERE id_recinto = %s"
    cursor.execute(query, (id_recinto,))
    result = cursor.fetchone()
    
    if not result:
        print(f"✗ Recinto {id_recinto} no encontrado")
        return
    
    geom_wkb, nombre, superficie = result
    print(f"\n✓ Recinto: {nombre} ({superficie:.2f} ha)")
    
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
        print(f"✗ NDVI no encontrado: {NDVI_BASE}")
        return
    
    print(f"\n✓ Abriendo NDVI: {NDVI_BASE}")
    
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
        
        # Leer ventana del BBOX (no crop por polígono, solo bbox rectangular)
        minx, miny, maxx, maxy = geometria.bounds
        
        # Añadir pequeño buffer
        buffer = max((maxx - minx), (maxy - miny)) * 0.05
        window = from_bounds(
            minx - buffer, miny - buffer,
            maxx + buffer, maxy + buffer,
            src.transform
        )
        
        # Leer datos de la ventana
        ndvi_data = src.read(1, window=window)
        
        # Transform para esta ventana
        window_transform = src.window_transform(window)
        
        # Actualizar geometría bounds para que coincida con la ventana leída
        window_bounds = rasterio.windows.bounds(window, src.transform)
        
        print(f"  Ventana: {ndvi_data.shape}")
        print(f"  NaN: {np.isnan(ndvi_data).sum()} de {ndvi_data.size}")
    
    # 3. GENERAR THUMBNAIL
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    nombre_limpio = nombre.replace('/', '_').replace('\\', '_')
    output_png = os.path.join(OUTPUT_DIR, f"ndvi_{nombre_limpio}.png")
    
    stats = generar_thumbnail_ndvi(ndvi_data, geometria, nombre, output_png)
    
    # 4. RESUMEN
    print("\n" + "="*60)
    print("✓ COMPLETADO")
    print("="*60)
    print(f"Archivo: {output_png}")
    print(f"NDVI medio: {stats['mean']:.3f}")
    print(f"Rango: [{stats['min']:.3f}, {stats['max']:.3f}]")


if __name__ == "__main__":
    try:
        procesar_recinto(ID_RECINTO)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()