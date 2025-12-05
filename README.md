# Plataforma GIS para ingestión, análisis y visualización de datos aéreos
Este repositorio tendrá como objetivo principal el montaje y uso de un Sistema de Información Geográfica para aplicación de la información proporcionada por JRU Drones.
Cabe aclarar que todas las carpetas de este repositorio contienen un ```nombreCarpeta_info.md``` con una breve explicación de la funcionalidad y uso de cada una de ellas.
Para la instalación del entorno, se debe consultar el archivo: ```instalacion_info.md```, donde se encuentran todos los pasos redactados para poder llevar a cabo esto sin mayor complicación.

<p align="center">
  <img width="1024" height="1024" alt="JRUDRONES logo" src="https://github.com/user-attachments/assets/e53ee180-2f2d-434e-9b7e-8fe59f00f496" />
</p>

---
## Diagrama de flujo del sistema
<img width="3182" height="1042" alt="image" src="https://github.com/user-attachments/assets/b88a08fd-bb40-4288-b746-b936000ff39e" />

El diagrama siguiente representa la **arquitectura funcional y de datos** del sistema WebGIS de recomendaciones de riego.  
La solución integra diversas fuentes de información, como, por ejemplo: sensores IoT, imágenes satelitales y dron, y capas externas, dentro de un flujo de ingesta, procesamiento, almacenamiento y visualización basado en tecnologías **Python**, **PostgreSQL/PostGIS** y **GeoServer**.

El diseño busca garantizar:
- **Interoperabilidad** con estándares OGC (WMS/WFS/WCS).
- **Escalabilidad** para incorporar nuevas fuentes de datos o algoritmos analíticos.
- **Trazabilidad completa** desde la adquisición del dato hasta la generación de recomendaciones.
- **Flexibilidad** para ser consumido tanto por clientes web como por herramientas SIG de escritorio.

### Componentes principales del flujo

#### 1. Fuentes de datos

Este bloque agrupa los **orígenes primarios de información** que alimentan el sistema:

- **Sensores IoT de humedad y clima:**  
  Dispositivos desplegados en campo que registran variables como humedad del suelo, temperatura, precipitación o caudal.  
  Los datos se envían periódicamente a la capa de ingesta mediante API o ficheros CSV/JSON.

- **Imágenes satelitales y de dron:**  
  Provenientes de programas como **Copernicus (Sentinel-2)** o vuelos con dron.  
  Se procesan para generar índices de vegetación: NDVI, ETP, LAI y productos ráster georreferenciados.

- **Capas externas:**  
  Conjuntos de datos complementarios, como modelos digitales del terreno, estaciones meteorológicas o límites administrativos, obtenidos de servicios públicos WMS/WFS.

Estas fuentes proporcionan los **datos brutos** que serán normalizados y cargados en la base de datos espacial.

#### 2. Ingesta y Procesamiento

Corresponde a la **capa de integración y transformación de datos**, donde se concentran los procesos de pretratamiento y análisis inicial:

- **Scripts Python y Notebooks:**  
  Implementan la lógica de ingesta, limpieza y formateo de datos mediante bibliotecas como `rasterio`, `geopandas`, `pandas` y `shapely`.  
  Se encargan de:
  - Reproyectar y recortar rásteres a las Áreas de Interés (AOI).  
  - Extraer valores medios por recinto.  
  - Calcular índices derivados (NDVI, ETP).  
  - Insertar los resultados en PostgreSQL/PostGIS.

Esta etapa constituye la **puerta de entrada** de toda la información espacial y temporal del sistema.

#### 3. Base de datos espacial

El corazón del sistema es la **base de datos PostgreSQL con extensión PostGIS**, que actúa como repositorio central y estructurado.

- **PostgreSQL + PostGIS** permite almacenar tanto datos **vectoriales** (recintos, sensores, cultivos) como **ráster** (índices NDVI, ortomosaicos).  
- Se gestionan los metadatos, la trazabilidad de las imágenes, las series temporales de sensores y las **recomendaciones de riego** generadas.  
- La estructura responde al modelo E-R presente en la carpeta `db`, explicado en el archivo `db_info.md`, garantizando consistencia e integridad referencial.

Esta base de datos sirve de fuente tanto para el backend de la aplicación como para el servidor GIS.

#### 4. API Backend

Implementada principalmente con **Flask**, la API actúa como **interfaz de negocio y capa lógica** entre la base de datos y los clientes WebGIS.

- Expone **endpoints REST/JSON** para consultar indicadores, recomendaciones o estadísticas.  
- Centraliza la **lógica de negocio**, como el cálculo de láminas de riego o validación de datos.  
- Puede integrarse con módulos de autenticación, gestión de usuarios y registro de logs.

El backend consume la información de PostGIS y la distribuye en formato interoperable para su visualización o integración con otros sistemas.

#### 5. Servidor GIS

El **servidor de mapas** implementado en GeoServer se encarga de **publicar los datos espaciales** mediante estándares OGC:

- **WMS (Web Map Service):** entrega imágenes renderizadas de mapas.  
- **WFS (Web Feature Service):** permite acceso vectorial directo a las geometrías y atributos.  
- **WCS (Web Coverage Service):** sirve rásteres y coberturas, como, por ejemplo NDVI o ETP.  

GeoServer se conecta directamente a las tablas PostGIS para exponer los datasets como **capas accesibles** por clientes web o de escritorio.

#### 6. Frontend / Clientes

Los usuarios finales interactúan con el sistema a través de distintas herramientas que consumen los servicios publicados:

- **Web GIS (Leaflet / Folium):**  
  Aplicación web interactiva que muestra los recintos, sensores y productos ráster.  
  Consume tanto el API REST, correspondiente a datos alfanuméricos, como servicios WMS/WFS, asociados a capas cartográficas.  
  Permite visualizar recomendaciones de riego o valores NDVI históricos.

- **QGIS Desktop:**  
  Herramienta de escritorio que se conecta directamente al GeoServer o a PostGIS mediante WMS/WFS o conexión SQL.  
  Utilizada por técnicos y analistas GIS para edición avanzada o validación de datos.

- **Jupyter Notebooks:**  
  Permite análisis exploratorio, desarrollo de modelos de riego o validación de índices mediante consultas SQL espaciales directas.

El sistema integra de forma armoniosa las tecnologías de **procesamiento científico (Python)**, **gestión espacial (PostGIS)** y **difusión geográfica (GeoServer)**.
Su arquitectura modular y basada en estándares permite adaptarse a nuevas fuentes de datos, como podría ser el caso de sensores adicionales o nuevos índices de vegetación, sin alterar la estructura principal.

Esta arquitectura constituye la **columna vertebral del sistema de riego inteligente**, donde la información espacial y temporal converge para proporcionar recomendaciones precisas, actualizadas y científicamente fundamentadas.

---

