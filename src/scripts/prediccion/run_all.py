import subprocess
import sys

scripts = [
    "scripts.prediccion.sync_inforiego",
    "scripts.prediccion.evotranspiracion_archivo2",
    "scripts.prediccion.generarmodelos",
    "scripts.prediccion.predecir",
    "scripts.prediccion.mapasprediccion",
]

for script in scripts:
    print(f"\nEjecutando {script}...")

    subprocess.run(
        [sys.executable, "-m", script],
        check=True
    )

print("\nTodos los scripts terminaron correctamente.")