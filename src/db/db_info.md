# Información general de la carpeta db
En esta carpeta se encuentra todo lo referente a la base de datos, que se implementará en **PostgreSQL con la extensión PostGIS**, lo que permite el almacenamiento y gestión de geometrías y rásteres geoespaciales.  
El modelo se ha diseñado bajo criterios de **normalización**, **integridad referencial** y **eficiencia espacial**, garantizando su interoperabilidad con servicios OGC (WMS, WFS, WCS) y plataformas como **GeoServer** y **QGIS**.
## Diagrama E-R
<img width="4547" height="3977" alt="image" src="https://github.com/user-attachments/assets/93184e44-95e3-454f-8742-c5507aa80ad2" />

El modelo entidad–relación define la estructura lógica de la base de datos que sustenta nuestro sistema **GIS** de Recomendaciones de Riego.  
Este sistema integra información geoespacial (parcelas, sensores, rásteres satelitales y productos derivados), datos agronómicos (cultivos, coeficientes Kc, estados fenológicos) y series temporales (lecturas de sensores y condiciones ambientales), con el propósito de generar recomendaciones de riego personalizadas para cada unidad agrícola.

### Descripción de las entidades principales
- **USUARIOS**

  Gestiona la autenticación y control de acceso del sistema.
  Contiene información de credenciales, roles y estado de actividad.
  Permite diferenciar perfiles administrativos, técnicos y de usuario final.

- **PARCELAS**

  Representa las unidades agrícolas base del sistema.
  Cada registro incluye su geometría espacial, superficie y propietario.
  Constituye la entidad central sobre la cual se vinculan los cultivos, sensores, imágenes y recomendaciones.

- **CULTIVOS**

  Describe los cultivos asociados a cada parcela, incluyendo su tipo, variedad, fechas de siembra y cosecha, y coeficiente Kc medio.
  Permite la gestión de rotaciones y el seguimiento fenológico.

- **IMÁGENES_SATELITALES**

  Almacena los metadatos de productos de observación terrestre.
  Incluye fechas de adquisición, nivel de procesamiento, cobertura nubosa, geometría de huella y rutas a los archivos físicos.

- **INDICES_RASTER**

  Registra los productos ráster derivados de las imágenes satelitales, tales como NDVI, ETP, LAI o NDWI.
  Cada índice se asocia a una imagen fuente y, opcionalmente, a una parcela específica.
  Puede almacenarse tanto la ruta del archivo GeoTIFF/COG como el propio ráster dentro de PostGIS.

- **IMÁGENES_DRON**

  Gestiona los vuelos de dron realizados sobre las parcelas.
  Incluye información técnica del vuelo, tipo de cámara y geometría del ortomosaico resultante.
  Permite la integración de observaciones de alta resolución complementarias a las imágenes satelitales.

- **SENSORES**

  Representa los dispositivos IoT desplegados en campo.
  Se vinculan a parcelas y cultivos concretos, e incluyen datos sobre ubicación, tipo, fabricante y frecuencia de medición.
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
  Relaciona la información proveniente de parcelas, cultivos, índices de vegetación y sensores para estimar la lámina de riego sugerida.
  Incluye indicadores como NDVI promedio, humedad del suelo y ETP calculada, además de la descripción del método o modelo empleado.

- **LOGS_SISTEMA**

  Registra las operaciones internas del sistema, incluyendo procesos automáticos, errores y acciones de usuario.
  Su campo `datos_adicionales` permite almacenar información estructurada en formato JSONB.
  Es fundamental para la trazabilidad, auditoría y depuración de procesos de ingesta y análisis.

### Descripción de las relaciones entre las entidades del sistema
En el diagrama, no se puede apreciar correctamente, pero no todas las relaciones son del tipo 1 a N (opcional) como pudiera parecer en un inicio. Esto se debe a una limitación de la herramienta con la que ha sido creada el diagrama E-R.
Por eso, serán explicadas debidamente a continuación en la siguiente tabla:

| Relación                                | Tipo                   | Explicación breve |
| --------------------------------------- | ---------------------- | ----------------- |
| **PARCELAS → CULTIVOS**                 | **One to Mandatory Many**     | Cada parcela debe tener uno o varios cultivos asociados. |
| **PARCELAS → SENSORES**                 | **One to Optional Many**      | Una parcela puede tener varios sensores instalados o ninguno. |
| **PARCELAS → IMAGENES_DRON**            | **One to Optional Many**      | Una parcela puede ser cubierta por vuelos de dron o no tener ninguno. |
| **PARCELAS → INDICES_RASTER**           | **One to Optional Many**      | Una parcela puede tener índices ráster asociados o no. |
| **PARCELAS → RECOMENDACIONES_RIEGO**    | **One to Mandatory Many**     | Cada parcela genera una o más recomendaciones de riego durante su ciclo. |
| **CULTIVOS → SENSORES**                 | **One to Optional Many**      | Un cultivo puede usar sensores específicos o no tener ninguno. |
| **CULTIVOS → RECOMENDACIONES_RIEGO**    | **One to Optional Many**      | Un cultivo puede estar asociado a una o varias recomendaciones de riego. |
| **IMAGENES_SATELITALES → INDICES_RASTER** | **One to Mandatory Many**   | Cada imagen satelital produce uno o más índices ráster derivados. |
| **SENSORES → MEDICIONES_SENSORES**      | **One to Mandatory Many**     | Cada sensor debe registrar una o más mediciones en el tiempo. |
| **VARIABLES → MEDICIONES_SENSORES**     | **One to Mandatory Many**     | Cada variable medida posee múltiples registros asociados. |
| **USUARIOS → LOGS_SISTEMA**             | **One to Optional Many**      | Un usuario puede generar varios registros de actividad o ninguno. |

El modelo presenta únicamente relaciones de tipo uno a muchos (1:N), reflejando así la naturaleza jerárquica y temporal de los datos agrícolas.
Se comprende que, una parcela agrupa muchos **elementos dependientes**, como es el caso de los `cultivos`, `sensores`, `imágenes` y `recomendaciones`,
las **entidades de medición y observación**, como los `índices ráster` o las `lecturas de sensores`, son las que crecen dinámicamente en el tiempo y
las **relaciones opcionales** se emplean para mantener `flexibilidad`, no todas las parcelas tienen sensores o imágenes, pero el modelo lo soporta sin comprometer la integridad de los datos.

