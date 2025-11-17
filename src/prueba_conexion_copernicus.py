import requests
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# ========== CONFIGURACIÓN ==========
USERNAME = os.getenv('COPERNICUS_USER')
PASSWORD = os.getenv('COPERNICUS_PASSWORD')
FECHA_ESPECIFICA = datetime.datetime.now().strftime('%Y-%m-%d') -1
COBERTURA_NUBES_MAX = 100
COORDENADAS = (-3.7038, 42.3439)  # (longitud, latitud) - Burgos
PRODUCTOS_A_DESCARGAR = 1 # Cambiar para descargar más imágenes

# ===================================

download_folder = "./data/raw"
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

# 2. Búsqueda de imágenes
search_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
headers = {'Authorization': f'Bearer {access_token}'}

# Calcular el rango del día específico
from datetime import datetime, timedelta
fecha_dt = datetime.strptime(FECHA_ESPECIFICA, '%Y-%m-%d')
fecha_inicio = fecha_dt.strftime('%Y-%m-%dT00:00:00.000Z')
fecha_fin = (fecha_dt + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00.000Z')

print(f"Buscando imágenes del día: {FECHA_ESPECIFICA}")

params = {
    '$filter': f"Collection/Name eq 'SENTINEL-2' and OData.CSC.Intersects(area=geography'SRID=4326;POINT({COORDENADAS[0]} {COORDENADAS[1]})') and ContentDate/Start ge {fecha_inicio} and ContentDate/Start lt {fecha_fin} and Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value lt {COBERTURA_NUBES_MAX})",
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
    print(f"No se encontraron productos para el día {FECHA_ESPECIFICA} con los criterios especificados")
    exit()

print(f"Se encontraron {len(products_list)} producto(s) para el día {FECHA_ESPECIFICA}")

# 3. Descargar productos completos
for i, product in enumerate(products_list, 1):
    product_id = product['Id']
    product_name = product['Name']
    fecha = product.get('ContentDate', {}).get('Start', 'N/A')
    
    # Extraer información del satélite del nombre del producto
    # Formato típico: S2A_... o S2B_...
    satelite = "Desconocido"
    if 'S2A' in product_name:
        satelite = "Sentinel-2A"
    elif 'S2B' in product_name:
        satelite = "Sentinel-2B"
    
    print(f"\n{'='*60}")
    print(f"Satélite: {satelite}")
    print(f"Fecha de captura: {fecha}")
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
print(f"Descarga completa. Archivos en: {download_folder}")
print(f"{'='*60}")