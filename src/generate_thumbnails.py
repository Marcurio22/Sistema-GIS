"""
Generador de Thumbnail NDVI - VERSIÓN OPTIMIZADA
✓ Precarga raster en memoria
✓ Conexión BD persistente
✓ Log cada 1000 recintos
✓ Padding en imágenes
✓ 5-10x MÁS RÁPIDO
✓ Lee fecha correcta del JSON
✓ Carpeta thumbnails/
"""

import os
import sys
import json
import platform
import subprocess
import numpy as np
import rasterio
from rasterio.windows import Window
from shapely import wkb
from shapely.ops import transform as shapely_transform
import matplotlib
matplotlib.use('Agg')  # Backend sin GUI = MÁS RÁPIDO
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
from matplotlib.patches import Polygon as MPLPolygon
import psycopg2
from pyproj import Transformer
from scipy.ndimage import gaussian_filter
import gc
from datetime import datetime
import time

# ==================== CONFIGURACIÓN ====================
DB_CONFIG = {
    'dbname': 'gisdb',
    'user': 'postgres',
    'password': 'postgres',
    'host': 'localhost',
    'port': '5432'
}

OUTPUT_DIR = 'webapp/static/thumbnails'  # CAMBIO: carpeta thumbnails
NDVI_BASE = './webapp/static/ndvi/ndvi2_latest_utm.tif'  # Usar latest para procesar
NDVI_META = './webapp/static/ndvi/ndvi2_latest.json'  # Metadatos con fecha

# ⚠️ CONFIGURACIÓN
START_FROM_ID = 0      # Empezar desde el principio
SKIP_EXISTING = True   # Saltar archivos existentes
LOG_INTERVAL = 1000    # Log cada 1000 recintos
IMAGE_PADDING = 0.08   # 8% de padding en la imagen

# APAGADO AUTOMÁTICO
AUTO_SHUTDOWN = False  # Desactivado por defecto
SHUTDOWN_DELAY = 30

# ==================== CACHE GLOBAL ====================
RASTER_CACHE = None
TRANSFORMER_CACHE = {}


# ==================== FUNCIONES DE APAGADO ====================
def apagar_ordenador(delay_seconds=30):
    """Apaga el ordenador después de un delay"""
    sistema = platform.system()
    
    print("\n" + "="*60)
    print("⚠️  APAGADO AUTOMÁTICO PROGRAMADO")
    print("="*60)
    print(f"El ordenador se apagará en {delay_seconds} segundos")
    print("Presiona Ctrl+C para cancelar")
    print("="*60 + "\n")
    
    try:
        if sistema == "Windows":
            subprocess.run(['shutdown', '/s', '/t', str(delay_seconds)], check=True)
        elif sistema == "Linux":
            subprocess.run(['sudo', 'shutdown', '-h', f'+{delay_seconds//60}'], check=True)
        elif sistema == "Darwin":
            subprocess.run(['sudo', 'shutdown', '-h', f'+{delay_seconds//60}'], check=True)
        else:
            print(f"⚠️  Sistema no reconocido: {sistema}")
            return False
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def cancelar_apagado():
    """Cancela el apagado programado"""
    sistema = platform.system()
    try:
        if sistema == "Windows":
            subprocess.run(['shutdown', '/a'], check=True)
        elif sistema in ["Linux", "Darwin"]:
            subprocess.run(['sudo', 'shutdown', '-c'], check=True)
        print("\n✓ Apagado cancelado")
    except:
        pass


# ==================== FECHA NDVI DESDE JSON ====================
def get_ndvi_date_from_json():
    """
    Lee la fecha del NDVI desde el archivo JSON de metadatos.
    Prioriza 'ndvi_date_formatted', luego 'ndvi_date', luego 'generated_utc'.
    """
    if not os.path.exists(NDVI_META):
        print(f"⚠ No se encontró {NDVI_META}, usando fecha actual")
        return datetime.now().strftime("%Y%m%d")
    
    try:
        with open(NDVI_META, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        
        # 1. Buscar ndvi_date_formatted (formato YYYYMMDD)
        if 'ndvi_date_formatted' in meta and meta['ndvi_date_formatted']:
            fecha = meta['ndvi_date_formatted']
            print(f"✓ Fecha NDVI desde JSON (ndvi_date_formatted): {fecha}")
            return fecha
        
        # 2. Buscar ndvi_date (ISO format)
        if 'ndvi_date' in meta and meta['ndvi_date']:
            dt = datetime.fromisoformat(meta['ndvi_date'].replace('Z', '+00:00'))
            fecha = dt.strftime("%Y%m%d")
            print(f"✓ Fecha NDVI desde JSON (ndvi_date): {fecha}")
            return fecha
        
        # 3. Fallback: generated_utc o updated_utc
        for key in ['generated_utc', 'updated_utc']:
            if key in meta and meta[key]:
                dt = datetime.fromisoformat(meta[key].replace('Z', '+00:00'))
                fecha = dt.strftime("%Y%m%d")
                print(f"⚠ Usando {key} como fecha NDVI: {fecha}")
                return fecha
        
        print("⚠ No se encontró fecha en JSON, usando fecha actual")
        return datetime.now().strftime("%Y%m%d")
        
    except Exception as e:
        print(f"✗ Error leyendo {NDVI_META}: {e}")
        return datetime.now().strftime("%Y%m%d")


# CARGAR FECHA AL INICIO
NDVI_DATE_STR = get_ndvi_date_from_json()


# ==================== OPTIMIZACIÓN: CACHE RASTER ====================
def cargar_raster_en_memoria():
    """🚀 PRECARGA el raster completo en RAM - MUCHO MÁS RÁPIDO"""
    global RASTER_CACHE
    
    if RASTER_CACHE is not None:
        return RASTER_CACHE
    
    print("📦 Cargando raster NDVI en memoria...")
    inicio = time.time()
    
    with rasterio.open(NDVI_BASE) as src:
        RASTER_CACHE = {
            'data': src.read(1),
            'transform': src.transform,
            'crs': src.crs.to_epsg(),
            'bounds': src.bounds,
            'width': src.width,
            'height': src.height
        }
    
    print(f"✓ Raster cargado en {time.time()-inicio:.1f}s")
    return RASTER_CACHE


def get_transformer(geom_srid, raster_crs):
    """Cache de transformadores de coordenadas"""
    key = (geom_srid, raster_crs)
    if key not in TRANSFORMER_CACHE:
        TRANSFORMER_CACHE[key] = Transformer.from_crs(
            f"EPSG:{geom_srid}",
            f"EPSG:{raster_crs}",
            always_xy=True
        )
    return TRANSFORMER_CACHE[key]


# ==================== PROCESAMIENTO ====================
def rellenar_ndvi_rapido(ndvi_array):
    """Rellena NaN de forma rápida"""
    if not np.any(~np.isnan(ndvi_array)):
        return np.full_like(ndvi_array, 0.3)
    
    filled = ndvi_array.copy()
    media = np.nanmean(filled)
    filled[np.isnan(filled)] = media
    filled = gaussian_filter(filled, sigma=1.5)
    
    return filled


def extraer_ventana_raster(geometria, padding=0.08):
    """Extrae datos del raster precargado usando una ventana"""
    raster = RASTER_CACHE
    
    minx, miny, maxx, maxy = geometria.bounds
    
    # Añadir padding
    width = maxx - minx
    height = maxy - miny
    buffer = max(width, height) * padding
    
    minx -= buffer
    miny -= buffer
    maxx += buffer
    maxy += buffer
    
    # Convertir a coordenadas de píxel
    transform = raster['transform']
    col_start, row_start = ~transform * (minx, maxy)
    col_end, row_end = ~transform * (maxx, miny)
    
    # Asegurar límites válidos
    col_start = max(0, int(col_start))
    row_start = max(0, int(row_start))
    col_end = min(raster['width'], int(col_end))
    row_end = min(raster['height'], int(row_end))
    
    if col_end <= col_start or row_end <= row_start:
        return None, None
    
    # Extraer ventana
    window_data = raster['data'][row_start:row_end, col_start:col_end]
    
    # Transform de la ventana
    window_transform = rasterio.windows.transform(
        Window(col_start, row_start, col_end - col_start, row_end - row_start),
        transform
    )
    
    return window_data, window_transform


def generar_thumbnail_optimizado(ndvi_data, geometria, output_path, dpi=50):
    """Genera thumbnail con padding - OPTIMIZADO"""
    
    # 1. RELLENAR NaN
    ndvi_relleno = rellenar_ndvi_rapido(ndvi_data)
    
    # 2. FIGURA
    fig, ax = plt.subplots(figsize=(6, 6), dpi=dpi, facecolor='white')
    
    # 3. COLORMAP
    colors = [
        '#000000', '#a50026', '#d73027', '#f46d43', '#fdae61', '#fee08b',
        '#ffffbf', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850', '#006837',
    ]
    boundaries = [-0.2, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    cmap = LinearSegmentedColormap.from_list('ndvi_tabla', colors, N=len(colors))
    norm = BoundaryNorm(boundaries, len(colors))
    
    # 4. CALCULAR BOUNDS CON PADDING
    minx, miny, maxx, maxy = geometria.bounds
    width = maxx - minx
    height = maxy - miny
    padding = max(width, height) * IMAGE_PADDING
    
    plot_minx = minx - padding
    plot_maxx = maxx + padding
    plot_miny = miny - padding
    plot_maxy = maxy + padding
    
    # 5. PLOTEAR
    im = ax.imshow(
        ndvi_relleno,
        cmap=cmap,
        norm=norm,
        extent=[plot_minx, plot_maxx, plot_miny, plot_maxy],
        interpolation='nearest',
        aspect='equal',
        zorder=1
    )
    
    # 6. CLIP PATH
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
    
    # 7. CONTORNO
    if geometria.geom_type == 'Polygon':
        x, y = geometria.exterior.xy
        ax.plot(x, y, color='black', linewidth=2, alpha=0.8, zorder=3)
    elif geometria.geom_type == 'MultiPolygon':
        for poly in geometria.geoms:
            x, y = poly.exterior.xy
            ax.plot(x, y, color='black', linewidth=2, alpha=0.8, zorder=3)
    
    # 8. CONFIGURACIÓN
    ax.set_xlim(plot_minx, plot_maxx)
    ax.set_ylim(plot_miny, plot_maxy)
    ax.set_aspect('equal')
    ax.axis('off')
    
    # 9. GUARDAR
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight', pad_inches=0, facecolor='white')
    plt.close(fig)
    
    # Limpiar
    del fig, ax, ndvi_relleno
    
    return float(np.nanmean(ndvi_data))


def procesar_recinto_optimizado(id_recinto, nombre, geom_wkb, conn_cursor):
    """Procesa UN recinto - VERSIÓN OPTIMIZADA"""
    
    # Verificar si existe (usa NDVI_DATE_STR desde JSON)
    output_png = os.path.join(OUTPUT_DIR, f"{NDVI_DATE_STR}_{id_recinto}.png")
    if SKIP_EXISTING and os.path.exists(output_png):
        return {'status': 'skipped'}
    
    try:
        # 1. GEOMETRÍA
        if isinstance(geom_wkb, str):
            geom_wkb = bytes.fromhex(geom_wkb)
        geometria = wkb.loads(geom_wkb)
        
        # Detectar SRID
        geom_srid = 4326
        try:
            import struct
            if len(geom_wkb) > 8:
                srid_bytes = geom_wkb[5:9]
                geom_srid = struct.unpack('<I', srid_bytes)[0]
        except:
            pass
        
        # 2. TRANSFORMAR SI ES NECESARIO
        raster_crs = RASTER_CACHE['crs']
        if geom_srid != raster_crs:
            transformer = get_transformer(geom_srid, raster_crs)
            geometria = shapely_transform(transformer.transform, geometria)
        
        # 3. EXTRAER VENTANA DEL RASTER PRECARGADO
        ndvi_data, _ = extraer_ventana_raster(geometria, padding=IMAGE_PADDING)
        
        if ndvi_data is None or ndvi_data.size == 0:
            return {'status': 'error', 'msg': 'Ventana vacía'}
        
        # 4. GENERAR THUMBNAIL
        mean_ndvi = generar_thumbnail_optimizado(ndvi_data, geometria, output_png)
        
        # Limpiar
        del ndvi_data, geometria
        
        return {'status': 'success', 'mean': mean_ndvi}
        
    except Exception as e:
        return {'status': 'error', 'msg': str(e)}


# ==================== PROCESO PRINCIPAL ====================
def procesar_todos_los_recintos():
    """Procesa TODOS los recintos desde START_FROM_ID"""
    
    print("="*60)
    print("🚀 GENERADOR DE THUMBNAILS NDVI - OPTIMIZADO")
    print("="*60)
    
    # 1. PRECARGAR RASTER
    cargar_raster_en_memoria()
    
    # 2. CREAR DIRECTORIO
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 3. CONEXIÓN BD PERSISTENTE
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # 4. OBTENER RECINTOS
    query = """
        SELECT id_recinto, nombre, superficie_ha, geom 
        FROM recintos 
        WHERE id_recinto >= %s 
        ORDER BY id_recinto
    """
    cursor.execute(query, (START_FROM_ID,))
    recintos = cursor.fetchall()
    
    total = len(recintos)
    print(f"\n✓ Recintos a procesar: {total}")
    print(f"✓ Desde ID: {START_FROM_ID}")
    print(f"✓ Fecha NDVI (desde JSON): {NDVI_DATE_STR}")
    print(f"✓ Carpeta salida: {OUTPUT_DIR}")
    print(f"✓ Saltar existentes: {SKIP_EXISTING}")
    print(f"✓ Padding: {IMAGE_PADDING*100:.0f}%")
    print(f"✓ Log cada: {LOG_INTERVAL} recintos\n")
    
    # 5. PROCESAR
    exitosos = 0
    errores = 0
    saltados = 0
    tiempo_inicio = time.time()
    
    for idx, (id_recinto, nombre, superficie, geom_wkb) in enumerate(recintos, 1):
        
        resultado = procesar_recinto_optimizado(id_recinto, nombre, geom_wkb, cursor)
        
        if resultado['status'] == 'success':
            exitosos += 1
        elif resultado['status'] == 'skipped':
            saltados += 1
        else:
            errores += 1
            if idx % 100 == 0:  # Solo mostrar errores cada 100
                print(f"  ✗ Error en {id_recinto}: {resultado.get('msg', 'Unknown')}")
        
        # LOG CADA LOG_INTERVAL
        if idx % LOG_INTERVAL == 0 or idx == total:
            tiempo_transcurrido = time.time() - tiempo_inicio
            velocidad = idx / tiempo_transcurrido
            tiempo_restante = (total - idx) / velocidad if velocidad > 0 else 0
            
            print(f"\n{'='*60}")
            print(f"Progreso: {idx}/{total} ({idx/total*100:.1f}%)")
            print(f"Exitosos: {exitosos} | Saltados: {saltados} | Errores: {errores}")
            print(f"Velocidad: {velocidad:.1f} recintos/seg")
            print(f"Tiempo transcurrido: {tiempo_transcurrido/60:.1f} min")
            print(f"Tiempo estimado restante: {tiempo_restante/60:.1f} min")
            print(f"{'='*60}\n")
            
            # Limpieza de memoria periódica
            gc.collect()
    
    # 6. CERRAR BD
    cursor.close()
    conn.close()
    
    # 7. RESUMEN FINAL
    tiempo_total = time.time() - tiempo_inicio
    print("\n" + "="*60)
    print("📊 RESUMEN FINAL")
    print("="*60)
    print(f"Fecha NDVI: {NDVI_DATE_STR}")
    print(f"Total procesados: {total}")
    print(f"✓ Exitosos: {exitosos}")
    print(f"⏭️  Saltados: {saltados}")
    print(f"✗ Errores: {errores}")
    print(f"⏱️  Tiempo total: {tiempo_total/60:.1f} minutos")
    print(f"🚀 Velocidad media: {total/tiempo_total:.1f} recintos/seg")
    print(f"📁 Directorio: {OUTPUT_DIR}")
    print(f"📄 Ejemplo: {NDVI_DATE_STR}_1.png")
    print("="*60)
    
    return exitosos, errores, total


# ==================== MAIN ====================
if __name__ == "__main__":
    try:
        # Verificar raster
        if not os.path.exists(NDVI_BASE):
            print(f"\n✗ ERROR: No se encontró {NDVI_BASE}")
            exit(1)
        
        print("="*60)
        print(f"🚀 INICIO - Fecha NDVI: {NDVI_DATE_STR}")
        print(f"📊 Desde recinto ID: {START_FROM_ID}")
        print("="*60 + "\n")
        
        # PROCESAR
        exitosos, errores, total = procesar_todos_los_recintos()
        
        # APAGAR
        if AUTO_SHUTDOWN and exitosos > 0:
            print("\n" + "🔌 "*20)
            print("Proceso completado. Apagando...")
            print("🔌 "*20)
            apagar_ordenador(SHUTDOWN_DELAY)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrumpido por el usuario")
        cancelar_apagado()
        sys.exit(0)
        
    except Exception as e:
        print(f"\n✗ ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)