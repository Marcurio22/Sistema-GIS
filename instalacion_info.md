# Pasos para la instalación del entorno
- Instalar **anaconda navigator**.
  Esto se puede llevar a cabo a través de la web, accediendo mediante el siguiente enelace: https://www.anaconda.com/download
- Descargar el archivo ```environment.yml``` desde este mismo repositorio.
- Abrir una terminal de **anaconda_prompt**.
- Hacer uso de los siguientes comandos:
  1) Instalar mamba (recomendable para llevar a cabo la instalación del entorno):
  ```bash
  conda install -n base -c conda-forge mamba
  ```
  2) Crear el entorno: 
  ```bash
  mamba env create -f environment.yml
  conda activate gis
  ```
  3) Registrar el kernel para Jupyter (este paso es opcional y no necesario):
  ```bash
  python -m ipykernel install --user --name gis --display-name "Python (gis)"
  ```
  4) Probar JupyterLab
  ```bash
  jupyter lab
  ```
# Verificación
  Con el entorno activado:
  ```bash
  python -c "import numpy, pandas, geopandas, rasterio; print('OK: entorno GIS activo')"
  ```

# Notas
  Este apartado está mejor explicado y es obligatoria su revisión en el archivo: ```vscode_info.md``` de la carpeta **vscode** de este mismo repositorio.
  - En **VS Code**, habrá que seleccionar el intérprete:  
    `Command Palette → Python: Select Interpreter → Python (gis)`.
  - Para actualizar dependencias desde `environment.yml`:
    ```bash
    mamba env update -f environment.yml --prune
    ```
  - Tanto en PowerShell como en cmd de Windows, los comandos son los mismos.
