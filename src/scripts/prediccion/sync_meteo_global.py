"""
Sincroniza meteorologia UNA vez en gisdb y replica datos_diarios a todas las comunidades.

Flujo diario recomendado (Planificador de tareas, una sola tarea):
  1. Este script  -> API Inforiego -> gisdb -> todas las BBDD de comunidades
  2. run_all.py   -> por cada comunidad (sin llamar a la API)

Variables utiles:
  METEO_ENV_FILE      .env de la instancia maestra (donde esta gisdb)
  COMUNIDADES_ROOT    carpeta con subcarpetas de comunidades (ej. C:\\GIS\\comunidades)
  REFERENCE_SOURCE_DB nombre BD maestra (por defecto gisdb)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

# Cargar .env maestro antes de importar sync_inforiego (necesita INFORIEGO_API_KEY)
_meteo_env = os.getenv("METEO_ENV_FILE", "").strip()
if _meteo_env and Path(_meteo_env).is_file():
    load_dotenv(_meteo_env, override=True)
elif (ROOT / ".env").is_file():
    load_dotenv(ROOT / ".env", override=True)

from scripts.prediccion.meteo_db import (  # noqa: E402
    build_master_url_from_env,
    build_pg_url_from_env,
    discover_community_envs,
)
from scripts.prediccion.replicate_datos_diarios import replicate_datos_diarios  # noqa: E402
from scripts.prediccion import sync_inforiego  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def load_master_env() -> Path | None:
    env_file = os.getenv("METEO_ENV_FILE", "").strip()
    if env_file:
        path = Path(env_file)
        if path.is_file():
            load_dotenv(path, override=True)
            return path
        log.warning("METEO_ENV_FILE no encontrado: %s", env_file)

    local_env = ROOT / ".env"
    if local_env.is_file():
        load_dotenv(local_env, override=True)
        return local_env
    return None


def sync_master(fecha_inicio: date, fecha_fin: date) -> None:
    master_url = build_master_url_from_env()
    engine = create_engine(master_url)
    Session = sessionmaker(bind=engine)

    original_engine = sync_inforiego.engine
    original_session = sync_inforiego.Session
    try:
        sync_inforiego.engine = engine
        sync_inforiego.Session = Session
        sync_inforiego.sync(fecha_inicio, fecha_fin)
    finally:
        sync_inforiego.engine = original_engine
        sync_inforiego.Session = original_session


def replicate_all_communities(fecha_inicio: date, fecha_fin: date) -> int:
    master_url = build_master_url_from_env()
    root = os.getenv("COMUNIDADES_ROOT", r"C:\GIS\comunidades")
    communities = discover_community_envs(root)

    if not communities:
        log.warning("No se encontraron comunidades en %s", root)
        return 0

    ok = 0
    for name, env_path in communities:
        load_dotenv(env_path, override=True)
        target_url = build_pg_url_from_env()
        if not target_url:
            log.warning("[%s] Sin POSTGRES_DB en .env, omitiendo", name)
            continue
        if target_url == master_url:
            log.info("[%s] Es la BD maestra, omitiendo replicacion", name)
            continue

        log.info("[%s] Replicando datos_diarios...", name)
        try:
            replicate_datos_diarios(master_url, target_url, fecha_inicio, fecha_fin)
            ok += 1
        except Exception as exc:
            log.error("[%s] Error replicando: %s", name, exc)

    return ok


def main() -> int:
    load_master_env()

    parser = argparse.ArgumentParser(
        description="Sync Inforiego -> gisdb -> todas las comunidades"
    )
    parser.add_argument("--dias", type=int, default=15)
    parser.add_argument("--inicio", type=str)
    parser.add_argument("--fin", type=str)
    parser.add_argument(
        "--solo-replicar",
        action="store_true",
        help="No llama a la API; solo copia desde gisdb a las comunidades",
    )
    args = parser.parse_args()

    if args.inicio:
        try:
            fecha_inicio = datetime.strptime(args.inicio, "%d/%m/%Y").date()
            fecha_fin = (
                datetime.strptime(args.fin, "%d/%m/%Y").date()
                if args.fin
                else date.today()
            )
        except ValueError:
            log.error("Formato de fecha invalido. Usa DD/MM/YYYY")
            return 1
    else:
        fecha_fin = date.today()
        fecha_inicio = fecha_fin - timedelta(days=args.dias)

    log.info("Rango meteorologico: %s -> %s", fecha_inicio, fecha_fin)

    if not args.solo_replicar:
        log.info("=== [1/2] Sincronizando API Inforiego -> gisdb ===")
        sync_master(fecha_inicio, fecha_fin)
    else:
        log.info("=== [1/2] Omitido (--solo-replicar) ===")

    log.info("=== [2/2] Replicando gisdb -> comunidades ===")
    n = replicate_all_communities(fecha_inicio, fecha_fin)
    log.info("Comunidades replicadas OK: %s", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
