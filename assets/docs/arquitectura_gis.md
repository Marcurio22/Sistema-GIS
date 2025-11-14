## Arquitectura del Servidor GIS

El sistema sigue una arquitectura basada en tres componentes principales:

1) **PostGIS**, que actúa como base de datos espacial donde se almacenan todos los datos vectoriales, raster y metadatos del proyecto.  
2) **GeoServer**, que se conecta directamente a PostGIS y publica la información mediante los servicios estándar OGC (WMS para visualización, WFS para datos vectoriales y WCS para datos raster).  
3) **Clientes GIS** como **QGIS** y la **interfaz WebGIS**, para visualizar y consultar la información.

El flujo de trabajo seguirá la ruta: **PostGIS → GeoServer (mediante servicios WMS/WFS/WCS) → QGIS/WebGIS**, asegurando coherencia de datos, accesibilidad remota y un sistema modular que separa almacenamiento, publicación y visualización.


