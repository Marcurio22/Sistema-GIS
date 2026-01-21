"""
Generador de Thumbnail NDVI - TODOS LOS RECINTOS
Lee la fecha del NDVI desde meta.json y nombra los archivos correctamente
APAGA EL ORDENADOR al finalizar
"""

import os
import sys
import json
import platform
import subprocess
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

OUTPUT_DIR = 'webapp/static/ndvi_simple'
NDVI_BASE = './webapp/static/ndvi/ndvi2_latest_utm.tif'
NDVI_META = './webapp/static/ndvi/ndvi2_latest.json'

# CONFIGURACIÓN DE APAGADO
AUTO_SHUTDOWN = True  # Cambiar a False para desactivar el apagado automático
SHUTDOWN_DELAY = 30   # Segundos de espera antes de apagar (para cancelar si es necesario)


# -----------------------------
# FUNCIÓN DE APAGADO
# -----------------------------
def apagar_ordenador(delay_seconds=30):
    """
    Apaga el ordenador después de un delay.
    Compatible con Windows, Linux y macOS
    """
    sistema = platform.system()
    
    print("\n" + "="*60)
    print("⚠️  APAGADO AUTOMÁTICO PROGRAMADO")
    print("="*60)
    print(f"El ordenador se apagará en {delay_seconds} segundos")
    print("Presiona Ctrl+C para cancelar el apagado")
    print("="*60 + "\n")
    
    try:
        if sistema == "Windows":
            # Windows: shutdown con delay
            subprocess.run(['shutdown', '/s', '/t', str(delay_seconds)], check=True)
            print(f"✓ Comando de apagado ejecutado (Windows)")
            
        elif sistema == "Linux":
            # Linux: shutdown con delay
            subprocess.run(['sudo', 'shutdown', '-h', f'+{delay_seconds//60}'], check=True)
            print(f"✓ Comando de apagado ejecutado (Linux)")
            print("  (puede requerir permisos sudo)")
            
        elif sistema == "Darwin":  # macOS
            # macOS: shutdown con delay
            subprocess.run(['sudo', 'shutdown', '-h', f'+{delay_seconds//60}'], check=True)
            print(f"✓ Comando de apagado ejecutado (macOS)")
            print("  (puede requerir permisos sudo)")
            
        else:
            print(f"⚠️  Sistema operativo no reconocido: {sistema}")
            print("   No se puede apagar automáticamente")
            return False
            
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Error al ejecutar comando de apagado: {e}")
        print("  Es posible que necesites permisos de administrador")
        return False
    except FileNotFoundError:
        print(f"✗ Comando de apagado no encontrado en el sistema")
        return False


def cancelar_apagado():
    """
    Cancela el apagado programado
    """
    sistema = platform.system()
    
    try:
        if sistema == "Windows":
            subprocess.run(['shutdown', '/a'], check=True)
            print("\n✓ Apagado cancelado")
            
        elif sistema in ["Linux", "Darwin"]:
            subprocess.run(['sudo', 'shutdown', '-c'], check=True)
            print("\n✓ Apagado cancelado")
            
    except Exception as e:
        print(f"\n⚠️  No se pudo cancelar el apagado: {e}")


# -----------------------------
# LEER FECHA DEL NDVI
# -----------------------------
def get_ndvi_date():
    """
    Lee la fecha del NDVI desde el meta.json
    Retorna formato YYYYMMDD para usar en nombres de archivo
    """
    if not os.path.exists(NDVI_META):
        from datetime import datetime
        print(f"⚠ WARNING: No se encontró {NDVI_META}, usando fecha actual")
        return datetime.now().strftime("%Y%m%d")
    
    try:
        with open(NDVI_META, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        
        # Primero intentar con el campo formateado
        fecha_formateada = meta.get('ndvi_date_formatted')
        if fecha_formateada:
            return fecha_formateada
        
        # Si no existe, parsear desde ndvi_date
        fecha_iso = meta.get('ndvi_date')
        if fecha_iso:
            from datetime import datetime
            dt = datetime.fromisoformat(fecha_iso.replace('Z', '+00:00'))
            return dt.strftime("%Y%m%d")
        
        # Fallback: usar updated_utc
        fecha_iso = meta.get('updated_utc', '')
        if fecha_iso:
            from datetime import datetime
            dt = datetime.fromisoformat(fecha_iso.replace('Z', '+00:00'))
            return dt.strftime("%Y%m%d")
        
    except Exception as e:
        print(f"⚠ ERROR leyendo meta.json: {e}")
    
    # Si todo falla, usar fecha actual
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d")


# Variable global con la fecha del NDVI
NDVI_DATE_STR = get_ndvi_date()
print("="*60)
print(f"Fecha del NDVI: {NDVI_DATE_STR}")
print(f"Formato de archivos: {NDVI_DATE_STR}_{{id_recinto}}.png")
print("="*60 + "\n")


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


def generar_thumbnail_ndvi(ndvi_data, geometria, nombre, id_recinto, output_path, dpi=150):
    """
    Genera thumbnail limpio - SOLO IMAGEN, sin título ni colorbar
    """
    print(f"\nGenerando thumbnail NDVI...")
    print(f"  Shape original: {ndvi_data.shape}")
    print(f"  NaN originales: {np.isnan(ndvi_data).sum()}")
    
    # 1. RELLENAR TODO (no queda ningún NaN)
    ndvi_relleno = rellenar_ndvi_completo(ndvi_data)
    print(f"  NaN después relleno: {np.isnan(ndvi_relleno).sum()}")
    
    # 2. CREAR FIGURA SIN MÁRGENES
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
        interpolation='nearest',
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
    
    # 7. CONFIGURACIÓN - SIN TÍTULO, SIN COLORBAR, SIN EJES
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect('equal')
    ax.axis('off')
    
    # 8. GUARDAR SIN PADDING NI MÁRGENES
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight', pad_inches=0,
                facecolor='white')
    plt.close()
    
    print(f"✓ Thumbnail guardado: {output_path}")
    
    # Calcular estadísticas para el log
    mean_ndvi = float(np.nanmean(ndvi_data))
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
    
    # 3. GENERAR THUMBNAIL CON FECHA DEL NDVI
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # USAR LA FECHA GLOBAL DEL NDVI (leída del meta.json)
    output_png = os.path.join(OUTPUT_DIR, f"{NDVI_DATE_STR}_{id_recinto}.png")
    
    stats = generar_thumbnail_ndvi(ndvi_data, geometria, nombre, id_recinto, output_png)
    
    print(f"  ✓ Thumbnail: {output_png} | NDVI medio: {stats['mean']:.3f}")


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
    print(f"✓ Fecha del NDVI: {NDVI_DATE_STR}")
    print(f"✓ Raster fuente: {NDVI_BASE}")
    print(f"✓ Directorio salida: {OUTPUT_DIR}\n")
    
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
    print(f"Fecha del NDVI: {NDVI_DATE_STR}")
    print(f"Total procesados: {total}")
    print(f"Exitosos: {exitosos}")
    print(f"Errores: {errores}")
    print(f"Directorio de salida: {OUTPUT_DIR}")
    print(f"\nNombres de archivo: {NDVI_DATE_STR}_{{id_recinto}}.png")
    print("="*60)
    
    return exitosos, errores, total


if __name__ == "__main__":
    try:
        # Verificar que existe el raster
        if not os.path.exists(NDVI_BASE):
            print(f"\n✗ ERROR: No se encontró el raster NDVI en: {NDVI_BASE}")
            print("   Ejecuta primero el script de descarga NDVI")
            exit(1)
        
        # Verificar que existe el meta.json
        if not os.path.exists(NDVI_META):
            print(f"\n⚠ WARNING: No se encontró {NDVI_META}")
            print("   Se usará la fecha actual en lugar de la fecha de las imágenes")
        
        # PROCESAR TODOS LOS RECINTOS
        exitosos, errores, total = procesar_todos_los_recintos()
        
        # APAGAR ORDENADOR SI ESTÁ ACTIVADO
        if AUTO_SHUTDOWN and exitosos > 0:
            print("\n" + "🔌 "*20)
            print("Proceso completado. Iniciando apagado automático...")
            print("🔌 "*20)
            apagar_ordenador(SHUTDOWN_DELAY)
        elif not AUTO_SHUTDOWN:
            print("\n⚠️  Apagado automático desactivado (AUTO_SHUTDOWN = False)")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso interrumpido por el usuario")
        cancelar_apagado()
        sys.exit(0)
        
    except Exception as e:
        print(f"\n✗ ERROR GENERAL: {e}")
        import traceback
        traceback.print_exc()
        
        # No apagar si hay error
        print("\n⚠️  No se apagará el ordenador debido al error")
        sys.exit(1)