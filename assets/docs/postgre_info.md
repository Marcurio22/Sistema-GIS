# Guía PostgreSQL + PostGIS

## Introduccion
**PostgreSQL** es una base de datos relacional de código abierto.  
**PostGIS** es una extensión de PostGres que añade soporte espacial (geometrías y rásteres), permitiendo almacenar, consultar y analizar datos geográficos. 
Con PostGIS, es posible realizar operaciones como medir distancias, calcular intersecciones, encontrar áreas dentro de un radio determinado, o analizar relaciones espaciales entre objetos — tareas fundamentales en campos como la cartografía, planificación urbana, medio ambiente, logística y sistemas de información geográfica (SIG o GIS).

## Instalación
1. Descargar el instalador desde:  
   👉 [https://www.postgresql.org/download/windows/](https://www.postgresql.org/download/windows/)
2. Ejecutar el instalador y seguir los pasos por defecto.
3. Al finalizar, abrir **Stack Builder** y marcar la opción para instalar **PostGIS**.
4. Verificar que se instalaron correctamente:
   - PostgreSQL
   - pgAdmin 4
   - Extensión PostGIS
  
## Configuración básica

1) Abrir pgAdmin 4 y conectarse al servidor local.
2)  Crear una nueva base de datos, por ejemplo:
   -Nombre: proyecto_gis
3) Activar la extensión PostGIS ejecutando:  
   CREATE EXTENSION postgis;  
   CREATE EXTENSION postgis_raster;  
También se puede hacer desde el apartado de extensiones, haciendo clic en crear extension y buscando postgis y postgis_raster
<img width="915" height="227" alt="image" src="https://github.com/user-attachments/assets/71541cb7-7dee-4cb4-ab75-3446d4ca3e9f" />

4) Verificar que las extensiones están activas:
 Deberían aparecer postgis y postgis_raster.
  
# Herramientas de administración

**pgAdmin:** Interfaz gráfica incluida con PostgreSQL para gestionar bases de datos  
**psql:** Cliente de línea de comandos



