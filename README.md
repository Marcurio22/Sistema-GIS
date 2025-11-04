# Sistema-GIS
Este repositorio tendrá como objetivo principal el montaje y uso de un Sistema de Información Geográfica para aplicación de la información proporcionada por JRU Drones.
Cabe aclarar que todas las carpetas de este repositorio contienen un ```nombreCarpeta_info.md``` con una breve explicación de la funcionalidad y uso de cada una de ellas.

## Pasos para la instalación del entorno
- Instalar **anaconda navigator**.
  Esto se puede llevar a cabo a través de la web, accediendo mediante el siguiente enelace: https://www.anaconda.com/download
- Descargar el archivo ```environment.yml``` desde este repositorio.
- Abrir una terminal de **anaconda_prompt**.
- Hacer uso de los siguientes comandos:
  1) Instalar mamba (si no lo tienes ya instalado):
  ```bash
  conda install -n base -c conda-forge mamba
  ```
  2) Crear el entorno: 
  ```bash
  mamba env create -f environment.yml
  mamba activate gis
  ```
  3) Registrar el kernel para Jupyter:
  ```bash
  python -m ipykernel install --user --name gis --display-name "Python (gis)"
  ```
  4) Probar JupyterLab
  ```bash
  jupyter lab
  ```
## Verificación
  Con el entorno activado:
  ```bash
  python -c "import numpy, pandas, geopandas, rasterio; print('OK: entorno GIS activo')"
  ```

## Notas
  - En **VS Code**, selecciona el intérprete:  
    `Command Palette → Python: Select Interpreter → Python (gis)`.
  - Para actualizar dependencias desde `environment.yml`:
    ```bash
    mamba env update -f environment.yml --prune
    ```
  - Si usas PowerShell en Windows, los comandos son los mismos.

