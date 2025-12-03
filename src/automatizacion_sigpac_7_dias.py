"""
descargar_sigpac_automatico.py

Descarga todos los recintos SIGPAC que intersectan tu ROI,
los vuelca a PostGIS usando una actualización "atómica" (estrategia B:
tabla temporal + renombrado), y repite el proceso cada 7 días.

Autor: Marcos Zamorano Lasso
Versión: 2.0.0
"""

import os
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# (Opcional pero recomendable para geometrías MultiPolygon)
try:
    from geoalchemy2 import Geometry
    _HAS_GEOALCHEMY = True
except ImportError:
    _HAS_GEOALCHEMY = False


# -----------------------------
# 1) Cargar ROI y calcular bbox
# -----------------------------
def obtener_bbox_roi(roi_path: str | Path) -> tuple[float, float, float, float]:
    """
    Lee un ROI (gpkg/shp) y devuelve su bbox en WGS84 (EPSG:4326)
    como (minx, miny, maxx, maxy).
    """
    roi = gpd.read_file(roi_path).to_crs(4326)  # WGS84 / CRS84
    minx, miny, maxx, maxy = roi.total_bounds
    bbox = (float(minx), float(miny), float(maxx), float(maxy))
    print("ROI bbox:", bbox)
    return bbox


# -------------------------------------------
# 2) Descargar TODOS los recintos por páginas
# -------------------------------------------
def descargar_todo_sigpac_recintos(bbox, limit=10000) -> gpd.GeoDataFrame:
    """
    Descarga todos los recintos SIGPAC que intersectan el bbox paginando con offset.
    limit = tamaño de página (no total).
    """
    base_url = "https://sigpac-hubcloud.es/ogcapi/collections/recintos/items"
    offset = 0
    pages: list[gpd.GeoDataFrame] = []

    while True:
        url = (
            f"{base_url}?f=json"
            f"&bbox-crs=http://www.opengis.net/def/crs/OGC/1.3/CRS84"
            f"&bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            f"&limit={limit}&offset={offset}"
        )

        print(f"→ Descargando página offset={offset}")
        resp = requests.get(url, timeout=180)
        resp.raise_for_status()
        data = resp.json()

        feats = data.get("features", [])
        if not feats:
            break

        gdf_page = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
        pages.append(gdf_page)

        if len(feats) < limit:
            break

        offset += limit

    if not pages:
        print("⚠ No se han descargado recintos para este bbox")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    gdf_all = gpd.GeoDataFrame(pd.concat(pages, ignore_index=True), crs="EPSG:4326")
    print(f"✅ Total recintos descargados en bbox: {len(gdf_all)}")
    return gdf_all


# ---------------------------------------------------
# 3) Guardar backup local ROTATORIO (solo 2 últimos)
# ---------------------------------------------------
def guardar_backup_rotatorio(gdf_recintos: gpd.GeoDataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    rec_path = out_dir / f"{stamp}_recintos.gpkg"

    gdf_recintos.to_file(rec_path, driver="GPKG")
    print(f"\nBackup guardado en: {rec_path}")

    # Mantener solo los 2 últimos backups
    files = sorted(out_dir.glob("*_recintos.gpkg"))
    for f in files[:-2]:
        f.unlink(missing_ok=True)
        print(f"Backup antiguo eliminado: {f}")


# ---------------------------------------------------
# 4) Volcar a PostGIS con actualización atómica
# ---------------------------------------------------
def actualizar_postgis_atomic(gdf_recintos: gpd.GeoDataFrame) -> None:
    """
    Actualiza la tabla sigpac.recintos en PostGIS de forma atómica:

    1) Escribe gdf_recintos en sigpac.recintos_new (replace).
    2) Dentro de una transacción:
        - DROP TABLE IF EXISTS sigpac.recintos_old;
        - ALTER TABLE IF EXISTS sigpac.recintos RENAME TO recintos_old;
        - ALTER TABLE sigpac.recintos_new RENAME TO recintos;
    """

    if gdf_recintos.empty:
        raise RuntimeError("No hay recintos para volcar a PostGIS (GeoDataFrame vacío).")

    print("\nConectando a PostGIS…")
    load_dotenv()

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    pwd  = os.getenv("POSTGRES_PASSWORD")

    if not all([db, user, pwd]):
        raise RuntimeError("Faltan POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD en .env")

    db_url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    engine = create_engine(db_url)

    # Crear schema si no existe
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS sigpac"))

    # dtype robusto para MultiPolygon
    dtype = None
    if _HAS_GEOALCHEMY:
        dtype = {"geometry": Geometry("MULTIPOLYGON", srid=4326)}

    print("→ Escribiendo datos en tabla temporal sigpac.recintos_new…")
    gdf_recintos.to_postgis(
        name="recintos_new",
        con=engine,
        schema="sigpac",
        if_exists="replace",   # crea o reemplaza la tabla temporal
        index=False,
        chunksize=5000,
        dtype=dtype,
    )

    print("→ Haciendo swap atómico recintos_old / recintos_new…")
    swap_sql = """
    DROP TABLE IF EXISTS sigpac.recintos_old;
    ALTER TABLE IF EXISTS sigpac.recintos RENAME TO recintos_old;
    ALTER TABLE sigpac.recintos_new RENAME TO recintos;
    """

    with engine.begin() as conn:
        conn.execute(text(swap_sql))

    print("Tabla sigpac.recintos actualizada correctamente.")


# ---------------------------------------------------
# 5) Proceso completo de actualización
# ---------------------------------------------------
def main():
    print("\n========================")
    print("  ACTUALIZACIÓN SIGPAC  ")
    print("========================")

    # Ruta del ROI (ajusta si hace falta)
    roi_path = "../data/processed/roi.gpkg"

    # 1) BBOX del ROI
    bbox = obtener_bbox_roi(roi_path)

    # 2) Descargar recintos del SIGPAC dentro del bbox
    print("\nDescargando recintos del SIGPAC…")
    gdf_recintos = descargar_todo_sigpac_recintos(bbox, limit=10000)

    if gdf_recintos.empty:
        print("⚠ No se descargaron recintos. No se actualiza PostGIS.")
        return

    # 3) Backup rotatorio
    guardar_backup_rotatorio(gdf_recintos, Path("data/raw/sigpac"))

    # 4) Actualizar PostGIS con swap atómico
    actualizar_postgis_atomic(gdf_recintos)

    print("\n✅ Proceso de actualización completado.\n")


# ---------------------------------------------------
# 6) Bucle de ejecución cada 7 días
# ---------------------------------------------------
if __name__ == "__main__":
    # Con cron, se puede comentar todo el while y llamar solo a main().
    while True:
        try:
            main()
        except Exception as exc:
            print(f"\n ERROR en la actualización: {exc}\n")

        # Esperar 7 días (7 * 24 * 60 * 60 segundos)
        print("Esperando 7 días para la próxima actualización…")
        time.sleep(7 * 24 * 60 * 60)