"""Wrapper: ejecuta generarmodelos portable en src/scripts/prediccion/."""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
target = ROOT / "src" / "scripts" / "prediccion" / "generarmodelos.py"
sys.path.insert(0, str(ROOT / "src"))
runpy.run_path(str(target), run_name="__main__")
