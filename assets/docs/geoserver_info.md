# Geoserver

## 1. Introduccion
**GeoServer** es un servidor GIS de código abierto que permite publicar datos espaciales desde diversas fuentes (PostGIS, Shapefiles, GeoTIFF, etc.) mediante estándares **OGC** como **WMS**, **WFS** y **WCS**.

En este proyecto, GeoServer se usa para:


## 2. Instalación 

1) Descargar GeoServer desde:  
   👉 https://geoserver.org/download/
2) Elegir la versión.
3) Descargar el instalador `.exe` para Windows.
4) Ejecutar el instalador y seguir los pasos:
   - Ruta de instalación (por ejemplo: `C:\Program Files\GeoServer`)
   - Puerto por defecto: **8080**
5) Al finalizar, abrir el navegador y entrar en:  
   👉 http://localhost:8080/geoserver
6) Iniciar sesión, credenciales por defecto:  
**Usuario:** admin  
**Contraseña:** geoserver

## 3. Configuración
   1) Conexión con PostGIS
      **Data** → **Stores** → **Add new Store** → **PostGIS**  
      Rellenar los datos para la conexión:
      - Workspace: nombre que quieras
      - Host: `localhost:5432`
      - Database: nombre de la base de datos
      - User/Password: credenciales de PostgreSQL
   2) Publicar capas 
   **Data** → **Layers** → **Add new layer**
      - Seleccionar store y tabla
      - Configurar SRS (ej: EPSG:25830)
      - Calcular Bounding Boxes

## 4. Referencias
   Documentación: https://docs.geoserver.org/

