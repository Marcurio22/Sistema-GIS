## Arquitectura del Servidor GIS

El sistema sigue una arquitectura en capas que separa almacenamiento, publicación y visualización de datos geoespaciales. Esta organización modular facilita el mantenimiento, las pruebas independientes de cada componente y futuras ampliaciones.

### Almacenamiento: PostGIS

PostGIS es el núcleo del sistema y almacena todos los datos geoespaciales: capas vectoriales (parcelas, sensores, límites de cultivos, redes de riego), raster (NDVI, ETP, LAI, imágenes Sentinel-2) y metadatos asociados. También mantiene un registro de actualizaciones automáticas, lo que permite rastrear cambios y versiones de los datos.

### Publicación: GeoServer

GeoServer se conecta a PostGIS y publica los datos mediante servicios web estándar OGC: **WMS** para mapas, **WFS** para datos vectoriales y **WCS** para capas raster. Gestiona estilos visuales mediante SLD y permite que los clientes web y de escritorio accedan a la información sin duplicarla. Así, los datos permanecen centralizados y actualizados.

### Consumo: QGIS y WebGIS

**QGIS** se utiliza para análisis espacial avanzado y edición de datos, conectándose directamente a los servicios de GeoServer.  
**WebGIS** permite a los usuarios acceder desde el navegador para visualizar capas y realizar consultas básicas, usando WMS/WFS o la API REST del backend Flask.

### Flujo general de datos

Los datos siguen una ruta clara: **PostGIS → GeoServer → [WMS/WFS/WCS] → QGIS/WebGIS**. Esta organización asegura que cada componente pueda actualizarse o reemplazarse de forma independiente, manteniendo la coherencia de la información y facilitando la integración con otros sistemas GIS.

### Ventajas

Esta arquitectura ofrece **modularidad**, **escalabilidad**, **accesibilidad remota**, **mantenibilidad** y **coherencia de datos**, garantizando un sistema flexible, eficiente y fácil de ampliar según las necesidades del proyecto.

> **Nota**: Esta arquitectura es provisional 
