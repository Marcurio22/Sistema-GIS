import subprocess
import sys

scripts = [
    "scripts.prediccion.sync_inforiego",
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
        check=True
    )

print("\nTodos los scripts terminaron correctamente.")