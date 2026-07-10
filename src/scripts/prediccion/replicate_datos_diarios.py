"""
Replica datos_diarios desde la BD maestra (gisdb) a la BD de la comunidad actual.

Las estaciones y sus mediciones son compartidas entre comunidades; solo hace falta
descargar de Inforiego una vez (en gisdb) y luego copiar el rango de fechas aqui.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from scripts.prediccion.meteo_db import (  # noqa: E402
    build_master_url_from_env,
    build_pg_url_from_env,
)
from webapp.models import DatosDiarios  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DATOS_COLUMNS = [
    c.name
    for c in DatosDiarios.__table__.columns
    if c.name != "id"
]


def replicate_datos_diarios(
    source_url: str,
    target_url: str,
    fecha_inicio: date,
    fecha_fin: date,
) -> tuple[int, int]:
    """Copia datos_diarios del rango [fecha_inicio, fecha_fin] con upsert."""
    if source_url == target_url:
        log.info("Origen y destino son la misma BD, omitiendo replicacion")
        return 0, 0

    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)

    with src_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {", ".join(DATOS_COLUMNS)}
                FROM datos_diarios
                WHERE fecha >= :ini AND fecha <= :fin
                ORDER BY estacion_id, fecha
                """
            ),
            {"ini": fecha_inicio, "fin": fecha_fin},
        ).mappings().all()

    if not rows:
        log.warning(
            f"Sin datos_diarios en maestra para {fecha_inicio} -> {fecha_fin}"
        )
        return 0, 0

    update_cols = {
        col: getattr(pg_insert(DatosDiarios).excluded, col)
        for col in DATOS_COLUMNS
        if col not in ("estacion_id", "fecha")
    }

    payloads = [dict(r) for r in rows]
    batch_size = 500
    written = 0

    try:
        with tgt_engine.begin() as conn:
            for i in range(0, len(payloads), batch_size):
                chunk = payloads[i : i + batch_size]
                stmt = pg_insert(DatosDiarios).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["estacion_id", "fecha"],
                    set_=update_cols,
                )
                result = conn.execute(stmt)
                written += result.rowcount if result.rowcount and result.rowcount > 0 else len(chunk)
    except Exception as exc:
        log.error("Error escribiendo en destino: %s", exc)
        raise

    with tgt_engine.connect() as conn:
        n_dest = conn.execute(
            text(
                "SELECT COUNT(*) FROM datos_diarios "
                "WHERE fecha >= :ini AND fecha <= :fin"
            ),
            {"ini": fecha_inicio, "fin": fecha_fin},
        ).scalar()

    log.info(
        f"Replicados {written} registros (upsert estacion_id+fecha); "
        f"destino tiene {n_dest} filas en el rango"
    )
    return written, 0


def main() -> int:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Replica datos_diarios desde gisdb a la BD de la comunidad"
    )
    parser.add_argument("--dias", type=int, default=15)
    parser.add_argument("--inicio", type=str)
    parser.add_argument("--fin", type=str)
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

    try:
        source_url = build_master_url_from_env()
        target_url = build_pg_url_from_env()
    except RuntimeError as exc:
        log.error(str(exc))
        return 1

    if not target_url:
        log.error("POSTGRES_DB / DATABASE_URL no definidos en .env de la comunidad")
        return 1

    log.info(
        f"Replicando datos_diarios {fecha_inicio} -> {fecha_fin}\n"
        f"  Origen:  {source_url.split('@')[-1]}\n"
        f"  Destino: {target_url.split('@')[-1]}"
    )
    replicate_datos_diarios(source_url, target_url, fecha_inicio, fecha_fin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
