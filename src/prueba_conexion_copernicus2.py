import requests
import os
from dotenv import load_dotenv
import datetime
from datetime import datetime, timedelta

# Cargar variables de entorno
load_dotenv()

# ========== CONFIGURACIÓN ==========
USERNAME = os.getenv('COPERNICUS_USER')
PASSWORD = os.getenv('COPERNICUS_PASSWORD')
FECHA_HASTA = "2025-11-16"  # Fecha límite - busca desde esta fecha hacia atrás
DIAS_BUSQUEDA_ATRAS = 60  # Número de días hacia atrás para buscar
COBERTURA_NUBES_MAX = 30  # Máximo % de nubes

roi_bbox = [-4.6718708208, 41.7248613835, -3.8314839480, 42.1274665349]

PRODUCTOS_A_DESCARGAR = 1  # Solo descargar 1 imagen
# ===================================

download_folder = "../data/raw"
os.makedirs(download_folder, exist_ok=True)

# 1. Obtener token de acceso
print("Conectando con Copernicus Dataspace...")
auth_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

credentials = {
    'grant_type': 'password',
    'username': USERNAME,
    'password': PASSWORD,
    'client_id': 'cdse-public'
}

response = requests.post(auth_url, data=credentials)

if response.status_code == 200:
    access_token = response.json()['access_token']
    print("Conexión establecida")
else:
    print(f"Error de autenticación: {response.status_code}")
    print(f"Mensaje: {response.text}")
    exit()

# 2. Búsqueda de imágenes - FILTRADO PARA L2A
search_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
headers = {'Authorization': f'Bearer {access_token}'}

# Calcular el rango de fechas - desde FECHA_HASTA hacia atrás
fecha_hasta_dt = datetime.strptime(FECHA_HASTA, '%Y-%m-%d')
fecha_desde_dt = fecha_hasta_dt - timedelta(days=DIAS_BUSQUEDA_ATRAS)

fecha_inicio = fecha_desde_dt.strftime('%Y-%m-%dT00:00:00.000Z')
fecha_fin = (fecha_hasta_dt + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00.000Z')

# Crear polígono a partir del bounding box
lon_min, lat_min, lon_max, lat_max = roi_bbox

# Construir el polígono (sentido antihorario)
polygon_wkt = f"POLYGON(({lon_min} {lat_min},{lon_max} {lat_min},{lon_max} {lat_max},{lon_min} {lat_max},{lon_min} {lat_min}))"

print(f"Buscando imágenes Sentinel-2 MSI L2A")
print(f"Rango de fechas: desde {fecha_desde_dt.strftime('%Y-%m-%d')} hasta {FECHA_HASTA}")
print(f"Área de búsqueda (bbox): {roi_bbox}")
print(f"Polígono: {polygon_wkt}")
print(f"Cobertura máxima de nubes: {COBERTURA_NUBES_MAX}%")

# Filtrar por 'SENTINEL-2' con productType L2A usando POLYGON
params = {
    '$filter': f"Collection/Name eq 'SENTINEL-2' and "
               f"Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq 'S2MSI2A') and "
               f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon_wkt}') and "
               f"ContentDate/Start ge {fecha_inicio} and "
               f"ContentDate/Start lt {fecha_fin} and "
               f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {COBERTURA_NUBES_MAX})",
    '$top': PRODUCTOS_A_DESCARGAR
}

results = requests.get(search_url, headers=headers, params=params)

if results.status_code != 200:
    print(f"Error en búsqueda: {results.status_code}")
    print(f"Mensaje: {results.text}")
    exit()

products = results.json()
products_list = products.get('value', [])

if not products_list:
    print(f"No se encontraron productos L2A desde {fecha_desde_dt.strftime('%Y-%m-%d')} hasta {FECHA_HASTA} con {COBERTURA_NUBES_MAX}% o menos de nubes")
    exit()

print(f"\n✓ Se encontró 1 producto L2A con {COBERTURA_NUBES_MAX}% o menos de nubes")

# 3. Descargar el producto
product = products_list[0]
product_id = product['Id']
product_name = product['Name']
fecha = product.get('ContentDate', {}).get('Start', 'N/A')

# Extraer información del satélite del nombre del producto
satelite = "Desconocido"
if 'S2A' in product_name:
    satelite = "Sentinel-2A"
elif 'S2B' in product_name:
    satelite = "Sentinel-2B"

# Verificar que sea L2A
nivel = "L2A" if "MSIL2A" in product_name else "Otro nivel"

# Obtener cobertura de nubes si está disponible
cloud_cover = "N/A"
for attr in product.get('Attributes', []):
    if attr.get('Name') == 'cloudCover':
        cloud_cover = f"{attr.get('Value', 'N/A')}%"
        break

print(f"\n{'='*60}")
print(f"IMAGEN A DESCARGAR")
print(f"Satélite: {satelite}")
print(f"Nivel de procesamiento: {nivel}")
print(f"Fecha de captura: {fecha}")
print(f"Cobertura de nubes: {cloud_cover}")
print(f"Producto: {product_name}")
print(f"{'='*60}")

download_url = f"https://zipper.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"

download_response = requests.get(download_url, headers=headers, stream=True)

if download_response.status_code == 200:
    file_path = os.path.join(download_folder, f"{product_name}.zip")
    
    total_size = int(download_response.headers.get('content-length', 0))
    downloaded = 0
    
    with open(file_path, 'wb') as f:
        for chunk in download_response.iter_content(chunk_size=1024*1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                progress = (downloaded / total_size) * 100
                print(f"\rProgreso: {progress:.1f}% ({downloaded/(1024*1024):.1f}/{total_size/(1024*1024):.1f} MB)", end='')
    
    print()
    file_size = os.path.getsize(file_path) / (1024 * 1024)
    print(f"✓ Completado: {file_path} ({file_size:.1f} MB)")
else:
    print(f"Error en descarga: {download_response.status_code}")
    print(f"Mensaje: {download_response.text}")

print(f"\n{'='*60}")
print(f"Descarga completa. Archivo en: {download_folder}")
print(f"{'='*60}")