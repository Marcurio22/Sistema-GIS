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
FECHA_ESPECIFICA = "2025-11-16"  # datetime.datetime.now().strftime('%Y-%m-%d')
COBERTURA_NUBES_MAX = 100

# Definir el bounding box [lon_min, lat_min, lon_max, lat_max]
roi_bbox = [-4.6718708208, 41.7248613835, -3.8314839480, 42.1274665349]

PRODUCTOS_A_DESCARGAR = 5  # Aumentado para cubrir el área completa
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

# Calcular el rango del día específico
fecha_dt = datetime.strptime(FECHA_ESPECIFICA, '%Y-%m-%d')
fecha_inicio = fecha_dt.strftime('%Y-%m-%dT00:00:00.000Z')
fecha_fin = (fecha_dt + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00.000Z')

# Crear polígono a partir del bounding box
lon_min, lat_min, lon_max, lat_max = roi_bbox

# Construir el polígono (sentido antihorario)
polygon_wkt = f"POLYGON(({lon_min} {lat_min},{lon_max} {lat_min},{lon_max} {lat_max},{lon_min} {lat_max},{lon_min} {lat_min}))"

print(f"Buscando imágenes Sentinel-2 MSI L2A del día: {FECHA_ESPECIFICA}")
print(f"Área de búsqueda (bbox): {roi_bbox}")
print(f"Polígono: {polygon_wkt}")

# Filtrar por 'SENTINEL-2' con productType L2A usando POLYGON
params = {
    '$filter': f"Collection/Name eq 'SENTINEL-2' and "
               f"Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq 'S2MSI2A') and "
               f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon_wkt}') and "
               f"ContentDate/Start ge {fecha_inicio} and "
               f"ContentDate/Start lt {fecha_fin} and "
               f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value lt {COBERTURA_NUBES_MAX})",
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
    print(f"No se encontraron productos L2A para el día {FECHA_ESPECIFICA} con los criterios especificados")
    exit()

print(f"\nSe encontraron {len(products_list)} producto(s) L2A para el día {FECHA_ESPECIFICA}")

# 3. Descargar productos completos
for i, product in enumerate(products_list, 1):
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
    print(f"Producto {i}/{len(products_list)}")
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
print(f"Descarga completa. Archivos en: {download_folder}")
print(f"Total de productos descargados: {len(products_list)}")
print(f"{'='*60}")