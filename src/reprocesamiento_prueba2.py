import os
import zipfile
import rasterio
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import box
import shutil
from pyproj import Transformer
import numpy as np

# ========== CONFIGURACIÓN ==========
# Carpetas
PROCESSED_FOLDER = "../data/raw"  # Donde están los .zip descargados
OUTPUT_FOLDER = "../data/processed"  # Donde se guardarán los recortes
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Área de interés - BURGOS, ESPAÑA
AOI_BBOX = {
    'minx': -4.6718708208,   # Longitud oeste
    'maxx': -3.8314839480,   # Longitud este
    'miny': 41.7248613835,   # Latitud sur
    'maxy': 42.1274665349    # Latitud norte
}
# EPSG para España
OUTPUT_EPSG = 'EPSG:25830'  # Sistema oficial de España - ETRS89 UTM 30N

# Bandas a procesar - PRIORIZAR RESOLUCIÓN 10m
BANDAS_CONFIG = {
    'B02': '10m',  # Blue
    'B03': '10m',  # Green
    'B04': '10m',  # Red
    'B08': '10m',  # NIR
    # Puedes añadir más:
    # 'B05': '20m',  # Red Edge 1
    # 'B06': '20m',  # Red Edge 2
    # 'B07': '20m',  # Red Edge 3
    # 'B8A': '20m',  # Narrow NIR
    # 'B11': '20m',  # SWIR 1
    # 'B12': '20m',  # SWIR 2
}

# CONFIGURACIÓN NDVI - Filtrado de valores
NDVI_UMBRAL_MINIMO = 0.2  # Solo mostrar valores superiores a este (elimina agua, nubes, suelo desnudo)
# Valores típicos:
# -1 a 0: Agua, nubes, nieve, construcciones
# 0 a 0.2: Suelo desnudo, roca, arena
# 0.2 a 0.4: Vegetación escasa (pasto seco, arbustos dispersos)
# 0.4 a 0.6: Vegetación moderada (cultivos, pasto verde)
# 0.6 a 1.0: Vegetación densa y muy saludable (bosques, cultivos densos)

# ===================================

def descomprimir_producto(zip_path):
    """Descomprimir el archivo ZIP del producto"""
    extract_folder = zip_path.replace('.zip', '')
    
    if os.path.exists(extract_folder):
        print(f"Carpeta ya existe: {extract_folder}")
        return extract_folder
    
    print(f"Descomprimiendo: {zip_path}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_folder)
    
    print(f"Descomprimido en: {extract_folder}")
    return extract_folder

def encontrar_bandas(product_folder, bandas_config):
    """Encontrar las rutas de las bandas específicas en productos L2A con resolución específica"""
    bandas_paths = {}
    
    # En L2A, las bandas están en: GRANULE/*/IMG_DATA/R10m, R20m, R60m
    for banda, resolucion in bandas_config.items():
        carpeta_resolucion = f'R{resolucion}'
        
        for root, dirs, files in os.walk(product_folder):
            # Buscar solo en la carpeta de la resolución específica
            if 'IMG_DATA' in root and carpeta_resolucion in root:
                for file in files:
                    if file.endswith('.jp2'):
                        # Formato L2A: T30TVM_20251116T111341_B04_10m.jp2
                        if f"_{banda}_" in file and f"_{resolucion}.jp2" in file:
                            # Evitar archivos de máscara y TCI
                            if 'MSK_' not in file and 'TCI_' not in file:
                                bandas_paths[banda] = os.path.join(root, file)
                                print(f"  ✓ {banda} ({resolucion}): {file}")
                                break
                if banda in bandas_paths:
                    break
    
    if not bandas_paths:
        print("  ⚠ No se encontraron bandas")
    
    return bandas_paths

def recortar_y_reproyectar(banda_path, banda_name, output_folder, product_name):
    """Recortar banda al área de interés y reproyectar a ETRS89"""
    try:
        with rasterio.open(banda_path) as src:
            print(f"  Procesando {banda_name}...")
            print(f"    CRS original: {src.crs}")
            print(f"    Resolución: {src.res[0]:.1f}m x {src.res[1]:.1f}m")
            print(f"    Dimensiones: {src.width} x {src.height}")
            
            # Crear geometría del bounding box en WGS84
            bbox_geom = box(AOI_BBOX['minx'], AOI_BBOX['miny'], 
                           AOI_BBOX['maxx'], AOI_BBOX['maxy'])
            
            # Transformar bbox a la proyección de la imagen fuente
            transformer = Transformer.from_crs('EPSG:4326', src.crs, always_xy=True)
            minx_t, miny_t = transformer.transform(AOI_BBOX['minx'], AOI_BBOX['miny'])
            maxx_t, maxy_t = transformer.transform(AOI_BBOX['maxx'], AOI_BBOX['maxy'])
            bbox_transformed = box(minx_t, miny_t, maxx_t, maxy_t)
            
            # Recortar
            out_image, out_transform = mask(src, [bbox_transformed], crop=True, filled=False)
            
            # Verificar que el recorte tiene datos
            if out_image.size == 0:
                print(f"    ⚠ El recorte está vacío para {banda_name}")
                return None
            
            print(f"    Dimensiones recorte: {out_image.shape[2]} x {out_image.shape[1]}")
            
            # Guardar con reproyección a ETRS89
            output_path = os.path.join(output_folder, f"{product_name}_{banda_name}.tif")
            
            # Calcular transformación para reproyección
            dst_crs = OUTPUT_EPSG
            transform, width, height = calculate_default_transform(
                src.crs, dst_crs, 
                out_image.shape[2], out_image.shape[1],
                left=out_transform.c, bottom=out_transform.f + out_transform.e * out_image.shape[1],
                right=out_transform.c + out_transform.a * out_image.shape[2], top=out_transform.f
            )
            
            # Configurar metadata de salida
            out_meta = src.meta.copy()
            out_meta.update({
                'driver': 'GTiff',
                'crs': dst_crs,
                'transform': transform,
                'width': width,
                'height': height,
                'compress': 'lzw'
            })
            
            # Crear imagen reproyectada
            with rasterio.open(output_path, 'w', **out_meta) as dest:
                for i in range(1, src.count + 1):
                    reproject(
                        source=rasterio.band(src, i),
                        destination=rasterio.band(dest, i),
                        src_transform=out_transform,
                        src_crs=src.crs,
                        dst_transform=transform,
                        dst_crs=dst_crs,
                        resampling=Resampling.bilinear
                    )
            
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"    ✓ Guardado: {banda_name} ({file_size:.2f} MB)")
            return output_path
            
    except Exception as e:
        print(f"    ✗ Error procesando {banda_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def crear_composicion_rgb(bandas_paths, output_folder, product_name):
    """Crear una composición RGB (True Color) - B04(R), B03(G), B02(B)"""
    try:
        print("\n  Creando composición RGB...")
        
        # Leer las bandas RGB
        with rasterio.open(bandas_paths['B04']) as red:
            red_data = red.read(1)
            profile = red.profile.copy()
            
        with rasterio.open(bandas_paths['B03']) as green:
            green_data = green.read(1)
            
        with rasterio.open(bandas_paths['B02']) as blue:
            blue_data = blue.read(1)
        
        # Verificar que todas tienen el mismo tamaño
        if not (red_data.shape == green_data.shape == blue_data.shape):
            print(f"    ⚠ Las bandas tienen diferentes tamaños:")
            print(f"       Red: {red_data.shape}, Green: {green_data.shape}, Blue: {blue_data.shape}")
            return None
        
        # Actualizar perfil para 3 bandas
        profile.update({
            'count': 3,
            'dtype': 'uint16',
            'compress': 'lzw'
        })
        
        # Guardar RGB
        output_path = os.path.join(output_folder, f"{product_name}_RGB.tif")
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(red_data, 1)
            dst.write(green_data, 2)
            dst.write(blue_data, 3)
        
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"    ✓ RGB creado ({file_size:.2f} MB)")
        return output_path
        
    except Exception as e:
        print(f"    ✗ Error creando RGB: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
    
def calcular_ndvi(product_output, product_name, bandas_procesadas):
    """Calcular NDVI a partir de las bandas B04 (rojo) y B08 (NIR) con filtrado de valores"""
    try:
        print("\n  Calculando NDVI...")
        print(f"    Umbral mínimo configurado: {NDVI_UMBRAL_MINIMO}")
        
        # Leer banda roja (B04) y NIR (B08)
        with rasterio.open(bandas_procesadas['B04']) as red_src:
            red = red_src.read(1).astype('float32')
            profile = red_src.profile.copy()
            
        with rasterio.open(bandas_procesadas['B08']) as nir_src:
            nir = nir_src.read(1).astype('float32')
        
        # Calcular NDVI: (NIR - RED) / (NIR + RED)
        # Evitar división por cero
        np.seterr(divide='ignore', invalid='ignore')
        ndvi = np.where(
            (nir + red) == 0,
            np.nan,  # Usar NaN en lugar de 0 para divisiones por cero
            (nir - red) / (nir + red)
        )
        
        # FILTRAR: Solo mantener valores superiores al umbral
        # Los valores inferiores se convierten en NoData (transparentes)
        ndvi_filtrado = np.where(ndvi >= NDVI_UMBRAL_MINIMO, ndvi, np.nan)
        
        # Estadísticas antes del filtrado
        valores_validos_original = np.sum(~np.isnan(ndvi))
        valores_validos_filtrado = np.sum(~np.isnan(ndvi_filtrado))
        porcentaje_retenido = (valores_validos_filtrado / valores_validos_original * 100) if valores_validos_original > 0 else 0
        
        print(f"    Valores NDVI originales: {valores_validos_original:,} píxeles")
        print(f"    Valores NDVI filtrados (>= {NDVI_UMBRAL_MINIMO}): {valores_validos_filtrado:,} píxeles ({porcentaje_retenido:.1f}%)")
        print(f"    Rango de valores filtrados: {np.nanmin(ndvi_filtrado):.3f} a {np.nanmax(ndvi_filtrado):.3f}")
        
        # Actualizar perfil
        profile.update({
            'dtype': 'float32',
            'count': 1,
            'compress': 'lzw',
            'nodata': np.nan  # Usar NaN como valor NoData
        })
        
        # Guardar NDVI filtrado
        output_path = os.path.join(product_output, f"{product_name}_NDVI_filtered.tif")
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(ndvi_filtrado, 1)
        
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"    ✓ NDVI filtrado guardado ({file_size:.2f} MB)")
        
        # También guardar NDVI completo (sin filtrar) para referencia
        output_path_full = os.path.join(product_output, f"{product_name}_NDVI_full.tif")
        with rasterio.open(output_path_full, 'w', **profile) as dst:
            dst.write(ndvi, 1)
        print(f"    ✓ NDVI completo guardado para referencia")
        
        return output_path
        
    except Exception as e:
        print(f"    ✗ Error calculando NDVI: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def procesar_producto(zip_path):
    """Procesar un producto completo: descomprimir, recortar, reproyectar"""
    product_name = os.path.basename(zip_path).replace('.zip', '').replace('.SAFE', '')
    print("\n" + "="*70)
    print(f"PROCESANDO: {product_name}")
    print("="*70)
    
    # Verificar que sea L2A
    if 'MSIL2A' not in product_name:
        print("⚠ Este producto NO es L2A, saltando...")
        return False
    
    # 1. Descomprimir
    extract_folder = descomprimir_producto(zip_path)
    
    # 2. Encontrar bandas
    print("\nBuscando bandas...")
    bandas_paths = encontrar_bandas(extract_folder, BANDAS_CONFIG)
    
    if not bandas_paths:
        print("⚠ No se encontraron bandas para procesar")
        return False
    
    # 3. Crear carpeta de salida para este producto
    product_output = os.path.join(OUTPUT_FOLDER, product_name)
    os.makedirs(product_output, exist_ok=True)
    
    # 4. Procesar cada banda
    print("\nRecortando y reproyectando bandas...")
    bandas_procesadas = {}
    for banda_name, banda_path in bandas_paths.items():
        output_path = recortar_y_reproyectar(banda_path, banda_name, product_output, product_name)
        if output_path:
            bandas_procesadas[banda_name] = output_path
    
    # 5. Crear composición RGB si tenemos las bandas necesarias
    if all(b in bandas_procesadas for b in ['B04', 'B03', 'B02']):
        crear_composicion_rgb(bandas_procesadas, product_output, product_name)
    else:
        faltantes = [b for b in ['B04', 'B03', 'B02'] if b not in bandas_procesadas]
        print(f"\n⚠ No se puede crear RGB - faltan bandas: {', '.join(faltantes)}")

    # 6. Calcular NDVI si tenemos las bandas necesarias
    if 'B04' in bandas_procesadas and 'B08' in bandas_procesadas:
        calcular_ndvi(product_output, product_name, bandas_procesadas)
    else:
        faltantes = [b for b in ['B04', 'B08'] if b not in bandas_procesadas]
        print(f"\n⚠ No se puede calcular NDVI - faltan bandas: {', '.join(faltantes)}")
    
    # 7. Limpiar carpeta temporal
    print("\nLimpiando archivos temporales...")
    try:
        shutil.rmtree(extract_folder)
        print(f"✓ Carpeta temporal eliminada")
    except Exception as e:
        print(f"⚠ No se pudo eliminar carpeta temporal: {str(e)}")
    
    print(f"\n{'='*70}")
    print(f"✓ COMPLETADO: {len(bandas_procesadas)}/{len(BANDAS_CONFIG)} bandas procesadas")
    print(f"  Archivos guardados en: {product_output}")
    print(f"{'='*70}")
    return len(bandas_procesadas) > 0

def procesar_todos_los_productos():
    """Procesar todos los productos ZIP en la carpeta"""
    productos_zip = [f for f in os.listdir(PROCESSED_FOLDER) 
                     if f.endswith('.zip') and 'MSIL2A' in f]
    
    if not productos_zip:
        print("⚠ No hay productos L2A para procesar en:", PROCESSED_FOLDER)
        return
    
    print(f"\n{'='*70}")
    print(f"PRODUCTOS L2A ENCONTRADOS: {len(productos_zip)}")
    print(f"{'='*70}")
    
    exitosos = 0
    fallidos = 0
    
    for i, zip_file in enumerate(productos_zip, 1):
        print(f"\n[{i}/{len(productos_zip)}]")
        zip_path = os.path.join(PROCESSED_FOLDER, zip_file)
        
        if procesar_producto(zip_path):
            exitosos += 1
        else:
            fallidos += 1
    
    print(f"\n{'='*70}")
    print(f"RESUMEN FINAL")
    print(f"{'='*70}")
    print(f"✓ Exitosos: {exitosos}")
    print(f"✗ Fallidos: {fallidos}")
    print(f"Total procesados: {exitosos + fallidos}")
    print(f"{'='*70}")

def main():
    print("="*70)
    print("PROCESAMIENTO DE IMÁGENES SENTINEL-2 L2A - ESPAÑA")
    print("="*70)
    print(f"Área de interés: Burgos")
    print(f"Coordenadas: {AOI_BBOX}")
    print(f"Sistema de referencia salida: {OUTPUT_EPSG} (ETRS89 UTM 30N)")
    print(f"Bandas a procesar: {', '.join(BANDAS_CONFIG.keys())}")
    print(f"Resoluciones: {', '.join(set(BANDAS_CONFIG.values()))}")
    print(f"NDVI umbral mínimo: {NDVI_UMBRAL_MINIMO} (solo vegetación >= este valor)")
    print("="*70)
    
    procesar_todos_los_productos()
    
    print("\n" + "="*70)
    print("PROCESAMIENTO FINALIZADO")
    print(f"Resultados guardados en: {OUTPUT_FOLDER}")
    print("="*70)

if __name__ == "__main__":
    main()