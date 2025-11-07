# Librería GDAL (Geospatial Data Abstraction Library)
---

## Descripción General

**GDAL** es una librería open source fundamental dentro del ecosistema **GIS**.  Se puede encontrar toda su documentación en la página: https://gdal.org/en/stable/ .
Proporciona una interfaz unificada para leer, escribir, transformar y analizar datos geoespaciales en más de 200 formatos de ráster y vector.

GDAL se utiliza tanto en herramientas de escritorio, como es el caso de **QGIS** con la que también trabajaremos, o como en entornos de desarrollo **Python**, donde se integra con librerías como `rasterio`, `geopandas`, `fiona` o `shapely`.

## Características Principales

| Tipo de dato | Capacidades |
|---------------|-------------|
| **Ráster** | Lectura y escritura de GeoTIFF, JPEG2000, IMG, NetCDF, HDF, GRIB, etc... |
| **Vectorial** | Soporte para Shapefile, GeoPackage, GeoJSON, KML, PostGIS, GML, etc... |
| **Transformaciones** | Reproyección y cambio de sistema de referencia. |
| **Conversión** | Comando `gdal_translate` para convertir entre formatos y comprimir archivos. |
| **Procesamiento** | Subconjuntos espaciales, mosaicos, reproyecciones, cálculos por píxel. |
| **Integración** | Compatible con PostgreSQL + PostGIS, Python, C/C++, R y otros lenguajes. |

## Arquitectura Interna

GDAL está compuesta por dos componentes principales:

- **GDAL** (para datos ráster): maneja imágenes satelitales, ortofotos, DEM, etc...  
- **OGR** (para datos vectoriales): maneja capas vectoriales, geometrías, atributos y topología.

Ambos comparten una **API unificada**, lo que permite procesar datos heterogéneos sin importar su formato o fuente.

## Instalación y Verificación
Esta librería se instala mediante nuestro fichero de `environment.yml`, junto con el resto de librerías clave para nuestro proyecto.

Para llevar a cabo la verificación de la misma, se pueden ejecutar los siguientes comandos desde la terminal de anaconda:
```bash
gdalinfo --version
```
Tras ejecutarlo, deberá de salir algo como: `GDAL 3.9.0, released 2024/05/07` donde se muestre claramente la versión de la librería.

Si queremos verificarlo mediante comandos de Python, tendremos que ejecutar lo siguiente:
```bash
from osgeo import gdal
print(gdal.__version__)
```
Nos deberá mostrar algo como lo de antes.

## Comandos clave de GDAL
| Comando          | Función                                                      | Ejemplo                                                                         |
| ---------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| `gdalinfo`       | Muestra información de metadatos de un archivo ráster        | `gdalinfo data/raw/s2_B04.tif`                                                  |
| `gdal_translate` | Convierte y comprime formatos ráster                         | `gdal_translate -of GTiff -co COMPRESS=LZW input.jp2 output.tif`                |
| `gdalwarp`       | Reproyecta o recorta imágenes                                | `gdalwarp -t_srs EPSG:4326 input.tif output_4326.tif`                           |
| `gdal_merge.py`  | Combina varios ráster en uno                                 | `gdal_merge.py -o mosaic.tif *.tif`                                             |
| `ogrinfo`        | Inspecciona archivos vectoriales                             | `ogrinfo data/processed/aoi.gpkg`                                               |
| `ogr2ogr`        | Convierte entre formatos vectoriales o carga datos a PostGIS | `ogr2ogr -f "PostgreSQL" PG:"dbname=gisdb user=gis_user password=..." aoi.gpkg` |


## Relación con otras librerías del proyecto
| Librería                 | Interacción con GDAL                                                     | Propósito                                         |
| ------------------------ | ------------------------------------------------------------------------ | ------------------------------------------------- |
| **Rasterio**             | Usa GDAL internamente para leer/escribir datos de ráster                 | Procesamiento de imágenes satelitales             |
| **GeoPandas**            | Usa OGR/GDAL a través de Fiona                                           | Manejo de datos vectoriales (shapes, geopackages) |
| **Shapely**              | Compatible con geometrías de OGR                                         | Análisis geométrico y espacial                    |
| **SQLAlchemy + PostGIS** | GDAL interactúa con PostGIS mediante `ogr2ogr` o drivers directos        | Carga y consulta de datos espaciales              |
| **Folium / Dash**        | Visualización de resultados procesados con GDAL                          | Mapas interactivos y dashboards                   |

