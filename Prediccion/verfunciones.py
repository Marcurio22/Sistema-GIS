import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from project_paths import PREDICCION_DLL_DIR  # noqa: E402

import pefile

pe = pefile.PE(str(PREDICCION_DLL_DIR / "DllRiegos64.dll"))
for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    print(exp.name)
