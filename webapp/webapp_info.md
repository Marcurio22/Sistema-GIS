# Carpeta destinada a todo lo relacionado con la interfaz web de la aplicación
## Integración entre Flask, PostGIS y GeoServer
Este sistema GIS combina tres componentes principales que interactúan entre sí para ofrecer capacidades completas de almacenamiento, análisis y visualización geoespacial:
- Flask → backend web + API REST + servidor de plantillas HTML
- PostGIS → base de datos espacial centralizada
- GeoServer → servidor GIS para publicación de servicios OGC (WMS/WFS)

### Conexión entre Flask y PostGIS
**Flask** actúa como backend de la aplicación, encargándose de atender peticiones HTTP desde el frontend, consultar la base de datos espacial y exponer endpoints API y renderizar vistas HTML.

La comunicación con **PostGIS** se realiza mediante **SQLAlchemy**, cargando una URL desde `Config` e inyectándola en **Flask** a través de la extensión `flask_sqlalchemy`.
**Flask** obtiene ciertas funcionalidades mediante el uso de un acceso directo a **PostGIS**:
- Consultas SQL optimizadas sobre geometrías y atributos.
- Cálculo de indicadores geoespaciales (NDVI, ETP, agregaciones, etc ...).
- Generación de respuestas en formato:
  - **JSON** - API REST para el frontend,
  - **GeoJSON** - capas vectoriales ligeras,
  - **HTML** - renderización de plantillas Jinja2.
- Lógica de negocio personalizada - validaciones, filtros, reglas.

**Flask** no procesa capas raster pesadas, ya que estas serán delegadas a **GeoServer**.

### Conexión entre GeoServer y PostGIS
Este punto en concreto está mejor explicado en: 

**GeoServer** actúa como servidor GIS especializado y se conecta a la misma base de datos **PostGIS**, aunque usando su propio usuario y permisos independientes.

**GeoServer** utiliza las tablas espaciales para publicar `WMS (Web Map Service)`, publicar `WFS (Web Feature Service)`, servir estilos `SLD`, generar tiles, reproyecciones y procesamiento geoespacial `server-side`.

**GeoServer** es responsable de servir `capas vectoriales grandes`, como: parcelas, redes, usos de suelo, `capas ráster`, como: NDVI, ortofotos, DEM, `capas multiespectrales` y productos derivados y consultas espaciales pesadas optimizadas mediante **PostGIS**.

### Conexión Frontend(Leaflet/Folium) con Flask y GeoServer
La parte web, que se encuentra en la carpeta: `webapp/templates` utiliza Leaflet/Folium como motor del visor GIS.
Desde el navegador, el cliente mezcla información procedente de dos fuentes complementarias:
- Por un lado, **servicios WMS/WFS desde GeoServer**.
Se utilizan para las capas de mayor volumen o cuando se requiere un renderizado dinámico en servidor, una reproyección automática, una simbología avanzada (SLD) o un acceso estandarizado vía OGC.
- Por otro lado, la **API REST personalizada servida por Flask**.
El frontend consulta Flask mediante `fetch()` para obtener: indicadores derivados, estadísticas de parcela, datos IoT procesados, resultados de algoritmos de análisis desarrollados en Python o capas vectoriales ligeras en GeoJSON.

### Integración combinada
El visor carga:
- Los mapas pesados desde **GeoServer** (WMS/WFS).
- Los datos analíticos desde **Flask**.

Esto permite una clara separación de responsabilidades:

  | Componente    | Rol                                                                    |
  | ------------- | ---------------------------------------------------------------------- |
  | **GeoServer** | Publicación GIS estándar, renderizado eficiente, ráster/vector pesados |
  | **Flask**     | API analítica, lógica de negocio, consultas personalizadas             |
  | **PostGIS**   | Fuente común de datos espaciales para ambos                            |


Más información sobre la estructura general del proyecto se puede encontrar en el archivo: `README.md`, en el directorio raíz de este repositorio.



