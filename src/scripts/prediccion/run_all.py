import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
load_dotenv(ROOT / ".env")


def _subprocess_env() -> dict:
    env = os.environ.copy()
    src = str(SRC)
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + prev if prev else "")
    return env

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
        env=_subprocess_env(),
    )

print("\nTodos los scripts terminaron correctamente.")
