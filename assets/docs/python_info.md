# Documentación referente a instalación y entorno de Python
Para este proyecto trabajamos principalmente con el lenguaje de programación Python a través de la aplicación VS Code, donde generamos nuestro código y funcionamiento general del sistema. 
Por otro lado, tenemos jupyter notebook donde se encuentra todo nuestro entorno de pruebas: código y visualización de imágenes, procesados y rasterizados.
Cabe añadir que github trata jupyter notebook como un lenguaje de programación a parte, pero realmente sigue siendo python, al menos en nuestro caso.
Procederemos ahora a explicar cada entorno por separado:
## Visual Studio Code
Puedes descargar Visual Studio Code desde el siguiente enlace: https://code.visualstudio.com/
Para la activación y configuración de este entorno, se debe consultar la carpeta **vscode**, donde se encuentra el archivo: ```vscode_info.md```.
En dicho archivo, se narran los pasos guiados con imágenes a seguir para probar este entorno, activar nuestro intérprete de python que hemos creado anteriormente y solventar posibles errores que surjan durante este proceso de activación y prueba.
Dentro de esta aplicación, hemos creado un enlace remoto a este repositorio de github para poder llevar a cabo diversas operaciones de git, como pulls, commits y pushes sin tener que hacerlo por terminal, para ello:

<img width="278" height="258" alt="hhdhd" src="https://github.com/user-attachments/assets/2f9aa731-ba70-4fec-af34-0a61ee427c33" />

Enlazamos la cuenta de github (1) y luego el repositorio (2), que es la pestaña del source control. De esta forma, podremos ver el árbol de directorios del repositorio tal y como lo tenemos en la imagen.
A partir de ahí, podremos trabajar libremente, crear los archivos que necesitemos y gestionar las operaciones de git a través de la pestaña de source control.

A través de esta pestaña:  <img width="70" height="78" alt="image" src="https://github.com/user-attachments/assets/7b7059c4-7bdc-4ae0-b1db-8e342eedb064" />  podremos ejecutar y depurar los archivos con los que estemos trabajando.
Al igual que lo que se indica en: ```vscode_info.md```, hemos creado tres archivos diferentes para diferentes necesidades.

- **settings.json**: Con este archivo, VS Code sabrá qué intérprete usar, en nuestro caso se trata del llamado gis. Se aplicará constantemente un formato automático con Black, los errores de estilo se manejarán con Ruff o isort y todas las variables del .env estarán disponibles, como es el caso de `DATABASE_URL`.
- **launch.json**: Su utilidad es evitar hacer uso de la terminal para ejecutar o depurar un script. Gracias a este, podremos hacerlo directamente con F5 o pulsando en el botón que he mencionado anteriormente. También podremos ejecutar la app Dash del proyecto y lanzar la suite de tests para su comprobación y validación.
- **devcontainer.json**: Este archivo permite abrir el proyecto en un contenedor Docker con todo preinstalado. Es ideal para trabajar en equipo o si el entorno GIS es pesado, como es el caso, debido a las bilbiotecas **GDAL** o **rasterio**.
  Para lanzarlo, seguimos los pasos:
  1) Tener Docker Desktop instalado y abierto.
  2) Dentro de VS Studio pulsar en este botón abajo a la izquierda:
  <img width="184" height="105" alt="image" src="https://github.com/user-attachments/assets/6434463f-ff78-46c2-a208-33131042a22e" />

  3) Elegir la opción: *Reopen in container*
  <img width="448" height="211" alt="image" src="https://github.com/user-attachments/assets/9c35d975-f205-4ac0-910c-e40bb12ea1e7" />

De esta manera, VS Code sustituirá el entorno automáticamente.

## Jupyter Lab

Jupyter Lab viene por defecto con el Anaconda Navigator, cuya instalación es necesaria para llevar a cabo la construcción de este entorno.
Como bien se ha dicho, este será nuestro entorno de pruebas. Tenemos la carpeta notebooks de este repositorio, en la que llevaremos a cabo todo lo referente a este entorno.
Para inicializarlo, como se indica en `instalación_info.md`, tras activar el entorno gis, mediante la consola de anaconda, basta con escribir: `jupyter lab` y se abrirá el entorno en el directorio en el que nos encontremos en ese momento en la terminal de anaconda:

<img width="838" height="35" alt="image" src="https://github.com/user-attachments/assets/25d90dcd-0f4a-41b2-9680-559c047596d0" />
(En este caso, entraré en la carpeta Sistema-GIS-main del escritorio)





