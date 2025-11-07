# QGIS

##  Introduccion  
   **QGIS** es un Sistema de Información Geográfica de código abierto que permite visualizar, editar y analizar datos espaciales.

   En este proyecto se usa para:
  1) Visualización de datos geográficos en diferentes formatos

##  Instalación
  1) Descargar desde https://qgis.org/download/  
  2) Escoger una versión
  3) Instalar siguiendo el asistente
  4) Abrir QGIS Desktop

## Configuración básica
### Conexión con PostGIS  
   - En el panel de “Administrador de fuentes de datos”, elegir **PostgreSQL**.  
   - Crear una nueva conexión con los siguientes parámetros:
     - **Nombre:** ej `PostGIS - proyecto_gis`
     - **Host:** `localhost`  
     - **Puerto:** por defecto:`5432`  
     - **Base de datos:** ej: `proyecto_gis`  
     - **Usuario:** *(por ejemplo, `postgres`)*  
     - **Contraseña:** *(la definida durante la instalación)*  
   - Hacer clic en **Probar conexión** y luego en **Aceptar**.  
   - Una vez guardada, podrás agregar capas directamente desde la base de datos.


## Plugins 
Los **Plugins** son extensiones que añaden funcionalidades adicionales a QGIS (como análisis avanzado, descarga de datos o conexión con servicios externos).  
Estos son los Plugins usados para el proyecto:


