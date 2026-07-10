import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

scripts = [
    # Meteorologia compartida: copia desde gisdb (la API se llama una vez con sync_meteo_global)
    "scripts.prediccion.replicate_datos_diarios",
    "scripts.prediccion.evotranspiracion_archivo2",
    "scripts.prediccion.generarmodelos",
    "scripts.prediccion.predecir",
    "scripts.prediccion.mapasprediccion",
    # Requiere NDVI reciente (ndvi_diax.py) para Kc preciso; si no hay raster usa fallback BD.
    "scripts.prediccion.mapasprediccion_riego",
]

for script in scripts:
    print(f"\nEjecutando {script}...")

    subprocess.run(
        [sys.executable, "-m", script],
        check=True,
        cwd=str(ROOT),
    )

print("\nTodos los scripts terminaron correctamente.")
