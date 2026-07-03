#!/usr/bin/env python3
"""
Pack diario NDVI: ndvi_diax.py → generate_thumbnails.py

Ejecutar desde la carpeta de la comunidad (donde está server.py):

  python -u src/scripts/pack_ndvi_diario.py

Tras ndvi_diax, detecta la fecha del mosaico generado y pasa esa fecha
a generate_thumbnails (--fechas YYYYMMDD).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def find_project_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(15):
        if (cur / "server.py").is_file() and (cur / "src").is_dir():
            return cur
        if (cur / "data").is_dir() and (cur / "src").is_dir():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root(Path(__file__).resolve())
NDVI_DIR = PROJECT_ROOT / "data" / "processed" / "ndvi_composite"
LOG_DIR = PROJECT_ROOT / "logs"


def log(msg: str, fp) -> None:
    line = msg.rstrip()
    print(line, flush=True)
    if fp:
        fp.write(line + "\n")
        fp.flush()


def run_script(rel_path: str, extra_args: list[str], fp) -> int:
    script = PROJECT_ROOT / rel_path.replace("/", os.sep)
    if not script.is_file():
        log(f"[ERROR] No existe: {script}", fp)
        return 1

    cmd = [sys.executable, "-u", str(script), *extra_args]
    log(f"\n>> {' '.join(cmd)}", fp)
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    code = int(proc.returncode or 0)
    log(f">> código salida: {code}", fp)
    return code


def fecha_mosaico_reciente() -> str | None:
    if not NDVI_DIR.is_dir():
        return None
    patron = re.compile(r"^ndvi_pc_(\d{8})_mosaic\.json$")
    candidatos: list[tuple[float, str]] = []
    for p in NDVI_DIR.glob("ndvi_pc_*_mosaic.json"):
        m = patron.match(p.name)
        if m:
            candidatos.append((p.stat().st_mtime, m.group(1)))
    if not candidatos:
        return None
    candidatos.sort(reverse=True)
    return candidatos[0][1]


def main() -> int:
    os.chdir(PROJECT_ROOT)
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"pack-ndvi-diario-{stamp}.log"

    with log_path.open("w", encoding="utf-8") as fp:
        log(f"Pack NDVI diario — {PROJECT_ROOT}", fp)
        log(f"Log: {log_path}", fp)

        log("\n[1/2] ndvi_diax.py", fp)
        code = run_script("src/ndvi_diax.py", [], fp)
        if code != 0:
            log("\n[ABORTADO] ndvi_diax falló; no se ejecuta generate_thumbnails", fp)
            return code

        fecha = fecha_mosaico_reciente()
        if not fecha:
            fecha = datetime.now().strftime("%Y%m%d")
            log(f"\n[AVISO] No se detectó mosaico JSON; usando fecha {fecha}", fp)
        else:
            log(f"\nFecha mosaico para thumbnails: {fecha}", fp)

        log("\n[2/2] generate_thumbnails.py", fp)
        code = run_script("src/generate_thumbnails.py", ["--fechas", fecha], fp)
        if code != 0:
            log("\n[ERROR] generate_thumbnails falló", fp)
            return code

        log("\n[OK] Pack NDVI diario completado", fp)

    print(f"\nLog guardado en: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
