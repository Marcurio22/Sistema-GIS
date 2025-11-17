import os
import zipfile
import rasterio
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import box
import geopandas as gpd
import shutil

# ========== CONFIGURACIÓN ==========
# Área de interés (Burgos y alrededores - ajusta según necesites)
AOI_BBOX = {
    'minx': -3.85,
    'miny': 42.25,
    'maxx': -3.55,
    'maxy': 42.45
}

# Bandas a procesar (puedes añadir más)
BANDAS_A_PROCESAR = ['B04', 'B03', 'B02', 'B08']  # RGB + NIR

# CRS de salida (por defecto: EPSG:4326 - WGS84)
OUTPUT_CRS = 'EPSG:4326'

# Carpetas
PROCESSED_FOLDER = "./raw"
OUTPUT_FOLDER = "./sentinel_gis_ready"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

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

def encontrar_bandas(product_folder, bandas):
    """Encontrar las rutas de las bandas específicas, buscando solo en carpetas IMG_DATA"""
    bandas_paths = {}
    
    # Buscar en la estructura de carpetas de Sentinel-2
    for root, dirs, files in os.walk(product_folder):
        
        # Filtrar para buscar solo dentro de la carpeta 'IMG_DATA' (o 'R10m', 'R20m', etc.)
        if 'IMG_DATA' in root or ('GRANULE' in root and any(r in root for r in ['R10m', 'R20m', 'R60m'])):
            
            for file in files:
                if file.endswith('.jp2'):
                    for banda in bandas:
                        # Las bandas suelen tener formato: T30TVN_20250110T110421_B04_10m.jp2
                        if f"_{banda}_" in file or f"_{banda}." in file:
                            # Evitar archivos de máscara que contienen 'MSK_'
                            if 'MSK_' not in file:
                                bandas_paths[banda] = os.path.join(root, file)
                                break
    
    print(f"Bandas encontradas: {list(bandas_paths.keys())}")
    return bandas_paths


def recortar_y_reproyectar(banda_path, banda_name, output_folder, product_name):
    """Recortar banda al área de interés y reproyectar si es necesario"""
    try:
        with rasterio.open(banda_path) as src:
            # Crear geometría del bounding box
            bbox_geom = box(AOI_BBOX['minx'], AOI_BBOX['miny'], 
                           AOI_BBOX['maxx'], AOI_BBOX['maxy'])
            
            # Convertir bbox a la proyección de la imagen
            from pyproj import Transformer
            transformer = Transformer.from_crs('EPSG:4326', src.crs, always_xy=True)
            
            # Transformar las coordenadas del bbox
            minx_t, miny_t = transformer.transform(AOI_BBOX['minx'], AOI_BBOX['miny'])
            maxx_t, maxy_t = transformer.transform(AOI_BBOX['maxx'], AOI_BBOX['maxy'])
            bbox_geom_transformed = box(minx_t, miny_t, maxx_t, maxy_t)
            
            # Recortar
            out_image, out_transform = mask(src, [bbox_geom_transformed], crop=True)
            out_meta = src.meta.copy()
            
            # Actualizar metadata
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "compress": "lzw"  # Comprimir para ahorrar espacio
            })
            
            # Guardar recorte
            output_path = os.path.join(output_folder, f"{product_name}_{banda_name}.tif")
            with rasterio.open(output_path, "w", **out_meta) as dest:
                dest.write(out_image)
            
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"Banda {banda_name} procesada: {output_path} ({file_size:.1f} MB)")
            return output_path
            
    except Exception as e:
        print(f"Error procesando banda {banda_name}: {str(e)}")
        return None

def crear_composicion_rgb(bandas_paths, output_folder, product_name):
    """Crear una composición RGB (True Color)"""
    try:
        # Leer las bandas RGB
        with rasterio.open(bandas_paths['B04']) as red, \
             rasterio.open(bandas_paths['B03']) as green, \
             rasterio.open(bandas_paths['B02']) as blue:
            
            # Leer los datos
            red_data = red.read(1)
            green_data = green.read(1)
            blue_data = blue.read(1)
            
            # Crear metadata para RGB
            rgb_meta = red.meta.copy()
            rgb_meta.update({
                'count': 3,
                'dtype': 'uint16'
            })
            
            # Guardar RGB
            output_path = os.path.join(output_folder, f"{product_name}_RGB.tif")
            with rasterio.open(output_path, 'w', **rgb_meta) as dst:
                dst.write(red_data, 1)
                dst.write(green_data, 2)
                dst.write(blue_data, 3)
            
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"Composición RGB creada: {output_path} ({file_size:.1f} MB)")
            return output_path
            
    except Exception as e:
        print(f"Error creando composición RGB: {str(e)}")
        return None

def procesar_producto(zip_path):
    """Procesar un producto completo: descomprimir, recortar, reproyectar"""
    product_name = os.path.basename(zip_path).replace('.zip', '')
    print("="*60)
    print(f"PROCESANDO: {product_name}")
    print("="*60)
    
    # 1. Descomprimir
    extract_folder = descomprimir_producto(zip_path)
    
    # 2. Encontrar bandas
    bandas_paths = encontrar_bandas(extract_folder, BANDAS_A_PROCESAR)
    
    if not bandas_paths:
        print("No se encontraron bandas para procesar")
        return False
    
    # 3. Crear carpeta de salida para este producto
    product_output = os.path.join(OUTPUT_FOLDER, product_name)
    os.makedirs(product_output, exist_ok=True)
    
    # 4. Procesar cada banda
    bandas_procesadas = {}
    for banda_name, banda_path in bandas_paths.items():
        output_path = recortar_y_reproyectar(banda_path, banda_name, product_output, product_name)
        if output_path:
            bandas_procesadas[banda_name] = output_path
    
    # 5. Crear composición RGB si tenemos las bandas necesarias
    if all(b in bandas_procesadas for b in ['B04', 'B03', 'B02']):
        crear_composicion_rgb(bandas_procesadas, product_output, product_name)
    
    # 6. Limpiar carpeta temporal
    try:
        shutil.rmtree(extract_folder)
        print(f"Carpeta temporal eliminada: {extract_folder}")
    except Exception as e:
        print(f"No se pudo eliminar carpeta temporal: {str(e)}")
    
    print(f"PROCESAMIENTO COMPLETO: {len(bandas_procesadas)} bandas procesadas")
    return True

def procesar_todos_los_productos():
    """Procesar todos los productos en la carpeta de procesados"""
    productos_zip = [f for f in os.listdir(PROCESSED_FOLDER) if f.endswith('.zip')]
    
    if not productos_zip:
        print("No hay productos para procesar")
        return
    
    print(f"Productos a procesar: {len(productos_zip)}")
    
    for zip_file in productos_zip:
        zip_path = os.path.join(PROCESSED_FOLDER, zip_file)
        procesar_producto(zip_path)

def main():
    print("="*60)
    print("INICIANDO PROCESAMIENTO DE PRODUCTOS SENTINEL")
    print("="*60)
    procesar_todos_los_productos()
    print("="*60)
    print("PROCESAMIENTO FINALIZADO")
    print("="*60)

if __name__ == "__main__":
    main()