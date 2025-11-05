"""
Proyecto : Sistema GIS
Archivo  : src/quick_env_check.py
Autor    : Marcos Zamorano Lasso
Versión  : 1.0.0
Fecha    : 2025-11-04
Descripción:
    Verificación rápida de entorno:
    - Carga variables desde .env
    - Muestra APP_PORT
    - Imprime el intérprete en uso y el directorio de trabajo
Uso:
    1) Desde VS Code (Run and Debug) con la configuración
       "Ejecutar archivo actual (con .env)".
    2) O desde terminal:
          conda activate gis
          python src/quick_env_check.py
Notas:
    - Si APP_PORT sale como None, revisa que el archivo .env exista en la raíz del repo
      y/o que estemos ejecutando desde la raíz. Considera pasar dotenv_path si fuera necesario.
"""
import os
from dotenv import load_dotenv
load_dotenv()
print("APP_PORT =", os.getenv("APP_PORT"))