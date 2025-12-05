# Información general de la carpeta db
En esta carpeta se encuentra todo lo referente a la base de datos, que se implementará en **PostgreSQL con la extensión PostGIS**, lo que permite el almacenamiento y gestión de geometrías y rásteres geoespaciales.  
El modelo se ha diseñado bajo criterios de **normalización**, **integridad referencial** y **eficiencia espacial**, garantizando su interoperabilidad con servicios OGC (WMS, WFS, WCS) y plataformas como **GeoServer** y **QGIS**.
## Diagrama E-R
<img width="5639" height="3897" alt="image" src="https://github.com/user-attachments/assets/9d527050-7676-4df0-a28f-af622f449949" />


El modelo entidad–relación define la estructura lógica de la base de datos que sustenta nuestro sistema **GIS** de Recomendaciones de Riego.  
Este sistema integra información geoespacial (recintos, sensores, rásteres satelitales y productos derivados), datos agronómicos (cultivos, coeficientes Kc, estados fenológicos) y series temporales (lecturas de sensores y condiciones ambientales), con el propósito de generar recomendaciones de riego personalizadas para cada unidad agrícola.

### Descripción de las entidades principales
- **USUARIOS**

  Gestiona la autenticación y control de acceso del sistema.
  Contiene información de credenciales, roles y estado de actividad.
  Permite diferenciar perfiles administrativos, técnicos y de usuario final.

- **recintos**

  Representa las unidades agrícolas base del sistema.
  Cada registro incluye su geometría espacial, superficie y propietario.
  Constituye la entidad central sobre la cual se vinculan los cultivos, sensores, imágenes y recomendaciones.

- **CULTIVOS**

  Describe los cultivos asociados a cada recinto, incluyendo su tipo, variedad, fechas de siembra y cosecha, y coeficiente Kc medio.
  Permite la gestión de rotaciones y el seguimiento fenológico.

- **IMÁGENES**
  Actúa como entidad padre común para cualquier tipo de imagen de observación, ya sea satelital o de dron.
  Registra metadatos generales como la fecha de adquisición, sensor, resolución espacial, EPSG y ruta al archivo físico.
  Facilita la extensibilidad y la trazabilidad de las distintas fuentes de datos espaciales.

- **IMÁGENES_SATELITALES**

  Contiene los detalles específicos de las imágenes provenientes de satélite.
  Incluye el nombre del satélite, nivel de procesamiento, cobertura nubosa, identificador del producto y bandas disponibles.
  Se relaciona uno a uno con la tabla `IMAGENES`, de la cual hereda la información general de adquisición y localización.

- **IMÁGENES_DRON**

  Gestiona los vuelos de dron realizados sobre los recintos.
  Incluye información técnica del vuelo y el vínculo con el recinto cubierta.
  Permite la integración de observaciones de alta resolución complementarias a las imágenes satelitales, a través de la relación uno a uno con `IMAGENES`.

- **INDICES_RASTER**

  Registra los productos ráster derivados de las imágenes, tales como NDVI, ETP, LAI o NDWI.
  Cada índice se asocia a una imagen fuente de la tabla `IMAGENES` y, opcionalmente, a una recinto específica.
  Se almacena la ruta del archivo GeoTIFF o COG, junto con sus metadatos, en lugar del ráster dentro de PostGIS, optimizando el rendimiento e integración con GeoServer.

- **SENSORES**

  Representa los dispositivos IoT desplegados en campo.
  Se vinculan a recintos y cultivos concretos, e incluyen datos sobre ubicación, tipo, fabricante y frecuencia de medición.
  Constituyen la fuente primaria de datos de humedad de suelo, temperatura, caudal y otras variables.

- **VARIABLES**

  Define el catálogo de variables físicas o ambientales medidas por los sensores, como, por ejemplo es el caso de: `humedad_suelo`, `temp_aire` y `precipitación`.
  Facilita la extensibilidad del sistema y la normalización de unidades.

- **MEDICIONES_SENSORES**

  Almacena las series temporales de valores registrados por los sensores.
  Cada medición está asociada a un sensor y a una variable específica, con su marca temporal y valor cuantitativo.
  La columna `otros_datos` permite registrar información adicional en formato JSON, como la calidad de la señal o los metadatos del dispositivo.

- **RECOMENDACIONES_RIEGO**

  Contiene los resultados generados por los modelos de recomendación.
  Relaciona la información proveniente de recintos, cultivos, índices de vegetación y sensores para estimar la lámina de riego sugerida.
  Incluye indicadores como NDVI promedio, humedad del suelo y ETP calculada, además de la descripción del método o modelo empleado.

- **LOGS_SISTEMA**

  Registra las operaciones internas del sistema, incluyendo procesos automáticos, errores y acciones de usuario.
  Su campo `datos_adicionales` permite almacenar información estructurada en formato JSONB.
  Es fundamental para la trazabilidad, auditoría y depuración de procesos de ingesta y análisis.

### Descripción de las relaciones entre las entidades del sistema
Se explican en la siguiente tabla:

| Relación                             | Tipo                      | Explicación breve                                                                 |
| ------------------------------------ | ------------------------- | --------------------------------------------------------------------------------- |
| **recintos → CULTIVOS**              | **One to Mandatory Many** | Cada recinto debe tener uno o varios cultivos asociados.                          |
| **recintos → SENSORES**              | **One to Optional Many**  | Una recinto puede tener varios sensores instalados o ninguno.                     |
| **recintos → IMAGENES_DRON**         | **One to Optional Many**  | Una recinto puede ser cubierta por vuelos de dron o no tener ninguno.             |
| **recintos → INDICES_RASTER**        | **One to Optional Many**  | Una recinto puede tener índices ráster asociados o no.                            |
| **recintos → RECOMENDACIONES_RIEGO** | **One to Mandatory Many** | Cada recinto genera una o más recomendaciones de riego durante su ciclo.          |
| **CULTIVOS → SENSORES**              | **One to Optional Many**  | Un cultivo puede usar sensores específicos o no tener ninguno.                    |
| **CULTIVOS → RECOMENDACIONES_RIEGO** | **One to Optional Many**  | Un cultivo puede estar asociado a una o varias recomendaciones de riego.          |
| **IMAGENES → INDICES_RASTER**        | **One to Mandatory Many** | Cada imagen (sea satelital o de dron) produce uno o más índices ráster derivados. |
| **IMAGENES → IMAGENES_SATELITALES**  | **One to One (Optional)** | Una imagen puede ser de tipo satelital y tener metadatos específicos asociados.   |
| **IMAGENES → IMAGENES_DRON**         | **One to One (Optional)** | Una imagen puede proceder de un dron y tener detalles técnicos propios del vuelo. |
| **SENSORES → MEDICIONES_SENSORES**   | **One to Mandatory Many** | Cada sensor debe registrar una o más mediciones en el tiempo.                     |
| **VARIABLES → MEDICIONES_SENSORES**  | **One to Mandatory Many** | Cada variable medida posee múltiples registros asociados.                         |
| **USUARIOS → LOGS_SISTEMA**          | **One to Optional Many**  | Un usuario puede generar varios registros de actividad o ninguno.                 |


### Interpretación general del modelo
El modelo mantiene una estructura jerárquica centrada en la **recinto** como núcleo de toda la información agrícola.
Las entidades dependientes, como cultivos, sensores, imágenes e índices ráster, se vinculan a ella para garantizar coherencia espacial y temporal.
Las **entidades observacionales**, como, por ejemplo, `mediciones_sensores` o `indices_raster` son las que más crecen con el tiempo, reflejando la naturaleza dinámica de la monitorización agrícola.
Por último, las **relaciones opcionales** aseguran flexibilidad: no todas los recintos tienen sensores o imágenes, pero el modelo lo soporta sin comprometer la integridad de los datos.

## Script con las tablas
En este mismo directorio podrás encontrar el script `schema.sql`. Con este fichero se definen todas las tablas ya vistas en el esquema de E-R, junto con sus respectivas relaciones y datos, definiendo en el proceso las claves primarias, fóraneas, el tipo de cada relación y restricciones de integridad, como: UNIQUE, NOT NULL, ON DELETE CASCADE, etc...

Además de esto, también se fijan tipos de datos adecuados a un contexto GIS, siendo estos: geometrías `geometry(Point/Polygon, 4326)` y campos `JSONB` para datos flexibles.

Adicionalmente, el script crea distintos índices para optimizar el rendimiento de las consultas. Se añaden índices espaciales GiST sobre las columnas geométricas para acelerar operaciones como búsquedas por intersección o proximidad, muy frecuentes en un **sistema GIS**. Sobre claves foráneas, campos de fechas y columnas muy usadas en filtros se crean índices B-tree que permiten recuperar rápidamente cultivos de una recinto, mediciones en un rango temporal o logs de un módulo concreto. 

Por último, algunos índices son únicos, lo que no solo mejora el rendimiento sino que también evita duplicidades lógicas, como dos mediciones con el mismo sensor-variable-timestamp o dos recomendaciones de riego para la misma recinto y día.


