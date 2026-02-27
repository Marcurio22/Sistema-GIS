"""
Sincroniza datos diarios desde la API de Inforiego usando SQLAlchemy en Flask.
Ejecutar con cron o manualmente. Por defecto sincroniza los últimos 25 días.
"""

import argparse
import logging
from datetime import date, datetime, timedelta
import requests
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webapp import create_app, db
from webapp.config import Config
from webapp.models import DatosDiarios, Estacion
from sqlalchemy.dialects.postgresql import insert as pg_insert

# ─── Configuración ──────────────────────────────────────────────────────────
API_KEY = Config.INFORIEGO_API_KEY
BASE_URL = "https://gateway.api.itacyl.es/inforiego"
HEADERS = {"apikey": API_KEY}

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ─── Funciones ──────────────────────────────────────────────────────────────
def get_estaciones(session):
    """
    Devuelve lista de estaciones con: (idprovincia, idestacion, id interno PK)
    """
    estaciones = session.query(Estacion).all()
    if not estaciones:
        log.error("No hay estaciones en la base de datos")
        sys.exit(1)
    log.info(f"Cargadas {len(estaciones)} estaciones desde la BD")
    return [(str(e.idprovincia), e.idestacion, e.id) for e in estaciones]


def parse_fecha(fecha_val):
    if fecha_val is None:
        return None
    if isinstance(fecha_val, (int, float)):
        try:
            return datetime.utcfromtimestamp(fecha_val / 1000).date()
        except Exception:
            return None
    try:
        return datetime.fromisoformat(str(fecha_val).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(str(fecha_val)[:10], "%Y-%m-%d").date()
        except Exception:
            return None


def fetch_diarios(provincia, estacion, fecha_inicio, fecha_fin):
    params = {
        "provincia": provincia,
        "estacion": estacion,
        "fecha_inicio": fecha_inicio.strftime("%d/%m/%Y"),
        "fecha_fin": fecha_fin.strftime("%d/%m/%Y"),
    }
    try:
        r = requests.get(
            f"{BASE_URL}/cnt/rest/diarios/",
            headers=HEADERS,
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        return data if data else []
    except requests.RequestException as e:
        log.error(f"Error API estación {estacion} provincia {provincia}: {e}")
        return []


def get_fechas_existentes(session, est_id, fecha_inicio, fecha_fin):
    """
    Devuelve un set con las fechas ya almacenadas para una estación
    en el rango dado. 1 query por estación en lugar de 1 por registro.
    """
    rows = (
        session.query(DatosDiarios.fecha)
        .filter(
            DatosDiarios.estacion_id == est_id,
            DatosDiarios.fecha >= fecha_inicio,
            DatosDiarios.fecha <= fecha_fin,
        )
        .all()
    )
    return {row.fecha for row in rows}


def build_dato(r, est_id, fecha_dato):
    """Construye un objeto DatosDiarios a partir de un registro de la API."""
    return DatosDiarios(
        estacion_id=est_id,
        fecha=fecha_dato,
        año=r.get("año"),
        dia=r.get("dia"),
        provincia=r.get("provincia"),
        tempmax=r.get("tempmax"),
        tempmin=r.get("tempmin"),
        tempmedia=r.get("tempmedia"),
        tempd=r.get("tempd"),
        hormintempmax=r.get("hormintempmax"),
        hormintempmin=r.get("hormintempmin"),
        humedadmax=r.get("humedadmax"),
        humedadmin=r.get("humedadmin"),
        humedadmedia=r.get("humedadmedia"),
        humedadd=r.get("humedadd"),
        horminhummax=r.get("horminhummax"),
        horminhummin=r.get("horminhummin"),
        velviento=r.get("velviento"),
        velvientomax=r.get("velvientomax"),
        dirviento=r.get("dirviento"),
        dirvientovelmax=r.get("dirvientovelmax"),
        recorrido=r.get("recorrido"),
        horminvelmax=r.get("horminvelmax"),
        precipitacion=r.get("precipitacion"),
        radiacion=r.get("radiacion"),
        rmax=r.get("rmax"),
        rn=r.get("rn"),
        n=r.get("n"),
        vd=r.get("vd"),
        vn=r.get("vn"),
        etbc=r.get("etbc"),
        etharg=r.get("etharg"),
        etpmon=r.get("etpmon"),
        etrad=r.get("etrad"),
        pebc=r.get("pebc"),
        peharg=r.get("peharg"),
        pepmon=r.get("pepmon"),
        perad=r.get("perad"),
        id_inforiego=r.get("id"),
        id_aux=r.get("idAux"),
    )


def sync(fecha_inicio, fecha_fin):
    session = Session()
    total_insert = 0
    total_skip = 0
    try:
        estaciones = get_estaciones(session)
        for prov, est_codigo, est_id in estaciones:
            log.info(f"Sincronizando estación {est_codigo} (provincia {prov}) — {fecha_inicio} → {fecha_fin}")

            registros = fetch_diarios(prov, est_codigo, fecha_inicio, fecha_fin)
            if not registros:
                log.warning(f"  → Sin datos para estación {est_codigo}")
                continue

            for r in registros:
                fecha_dato = parse_fecha(r.get("fecha"))
                if not fecha_dato:
                    log.warning(f"  → Fecha no parseable: {r.get('fecha')}")
                    continue

                stmt = pg_insert(DatosDiarios).values(
                    estacion_id=est_id,
                    fecha=fecha_dato,
                    año=r.get("año"),
                    dia=r.get("dia"),
                    provincia=r.get("provincia"),
                    tempmax=r.get("tempmax"),
                    tempmin=r.get("tempmin"),
                    tempmedia=r.get("tempmedia"),
                    tempd=r.get("tempd"),
                    hormintempmax=r.get("hormintempmax"),
                    hormintempmin=r.get("hormintempmin"),
                    humedadmax=r.get("humedadmax"),
                    humedadmin=r.get("humedadmin"),
                    humedadmedia=r.get("humedadmedia"),
                    humedadd=r.get("humedadd"),
                    horminhummax=r.get("horminhummax"),
                    horminhummin=r.get("horminhummin"),
                    velviento=r.get("velviento"),
                    velvientomax=r.get("velvientomax"),
                    dirviento=r.get("dirviento"),
                    dirvientovelmax=r.get("dirvientovelmax"),
                    recorrido=r.get("recorrido"),
                    horminvelmax=r.get("horminvelmax"),
                    precipitacion=r.get("precipitacion"),
                    radiacion=r.get("radiacion"),
                    rmax=r.get("rmax"),
                    rn=r.get("rn"),
                    n=r.get("n"),
                    vd=r.get("vd"),
                    vn=r.get("vn"),
                    etbc=r.get("etbc"),
                    etharg=r.get("etharg"),
                    etpmon=r.get("etpmon"),
                    etrad=r.get("etrad"),
                    pebc=r.get("pebc"),
                    peharg=r.get("peharg"),
                    pepmon=r.get("pepmon"),
                    perad=r.get("perad"),
                    id_inforiego=r.get("id"),
                    id_aux=r.get("idAux"),
                ).on_conflict_do_nothing(
                    constraint="uq_estacion_fecha"
                )

                result = session.execute(stmt)
                if result.rowcount == 1:
                    total_insert += 1
                else:
                    total_skip += 1

        session.commit()
        log.info(f"Sincronización completa: {total_insert} insertados, {total_skip} omitidos")

    except Exception as e:
        session.rollback()
        log.error(f"Error durante la sincronización, rollback aplicado: {e}")
        sys.exit(1)
    finally:
        session.close()


# ─── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # Crear tablas si no existen
    app = create_app()
    with app.app_context():
        db.create_all()
        log.info("Tablas verificadas/creadas correctamente")

    parser = argparse.ArgumentParser(description="Sincroniza datos diarios Inforiego")
    parser.add_argument(
        "--dias",
        type=int,
        default=25,
        help="Número de días hacia atrás a sincronizar (por defecto: 25)",
    )
    parser.add_argument(
        "--inicio",
        type=str,
        help="Fecha inicio manual DD/MM/YYYY (sobreescribe --dias)",
    )
    parser.add_argument(
        "--fin",
        type=str,
        help="Fecha fin manual DD/MM/YYYY (sobreescribe --dias, por defecto hoy)",
    )
    args = parser.parse_args()

    if args.inicio:
        try:
            fecha_inicio = datetime.strptime(args.inicio, "%d/%m/%Y").date()
            fecha_fin = datetime.strptime(args.fin, "%d/%m/%Y").date() if args.fin else date.today()
        except ValueError:
            log.error("Formato de fecha inválido. Usa DD/MM/YYYY")
            sys.exit(1)
    else:
        fecha_fin = date.today()
        fecha_inicio = fecha_fin - timedelta(days=args.dias)

    log.info(f"Iniciando sincronización: {fecha_inicio} → {fecha_fin}")
    sync(fecha_inicio, fecha_fin)