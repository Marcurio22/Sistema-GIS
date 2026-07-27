"""
Fija PROJ_LIB y GDAL_DATA del entorno conda antes de importar geopandas/rasterio.

En Windows, si PostGIS y conda están instalados, sin esto pyproj/rasterio fallan
con "unable to set PROJ database path" al ejecutar scripts fuera del servicio NSSM.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def conda_env_root(python_exe: str | Path | None = None) -> Path:
    exe = Path(python_exe or sys.executable).resolve()
    root = exe.parent
    if root.name.lower() == "scripts":
        root = root.parent
    return root


def _prepend_conda_bin_to_path(env: dict[str, str], root: Path) -> None:
    """Asegura DLLs de GDAL/PROJ en PATH (necesario fuera de 'conda activate')."""
    bins = [
        root,
        root / "Library" / "mingw-w64" / "bin",
        root / "Library" / "usr" / "bin",
        root / "Library" / "bin",
        root / "Scripts",
        root / "bin",
    ]
    prefix = os.pathsep.join(str(p) for p in bins if p.is_dir())
    if not prefix:
        return
    current = env.get("PATH", "")
    # Evitar duplicar si ya está al inicio
    if current.startswith(prefix):
        return
    env["PATH"] = prefix + os.pathsep + current if current else prefix


def setup_gis_runtime_env(python_exe: str | Path | None = None) -> dict[str, str]:
    """Define PROJ_LIB, GDAL_DATA y PATH conda en os.environ. Devuelve rutas aplicadas."""
    root = conda_env_root(python_exe)
    applied: dict[str, str] = {}

    for candidate in (root / "Library" / "share" / "proj", root / "share" / "proj"):
        if candidate.is_dir():
            os.environ["PROJ_LIB"] = str(candidate)
            applied["PROJ_LIB"] = str(candidate)
            break

    for candidate in (root / "Library" / "share" / "gdal", root / "share" / "gdal"):
        if candidate.is_dir():
            os.environ["GDAL_DATA"] = str(candidate)
            applied["GDAL_DATA"] = str(candidate)
            break

    _prepend_conda_bin_to_path(os.environ, root)
    applied["PATH_PREFIX"] = str(root / "Library" / "bin")
    return applied


def gis_subprocess_env(python_exe: str | Path | None = None) -> dict[str, str]:
    """os.environ copiado con PROJ/GDAL/PATH del conda (para subprocess)."""
    env = os.environ.copy()
    root = conda_env_root(python_exe)

    for candidate in (root / "Library" / "share" / "proj", root / "share" / "proj"):
        if candidate.is_dir():
            env["PROJ_LIB"] = str(candidate)
            break

    for candidate in (root / "Library" / "share" / "gdal", root / "share" / "gdal"):
        if candidate.is_dir():
            env["GDAL_DATA"] = str(candidate)
            break

    _prepend_conda_bin_to_path(env, root)
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env
