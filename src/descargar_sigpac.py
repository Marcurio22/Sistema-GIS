"""
descargar_sigpac.py
 
Descarga todos los recintos SIGPAC que intersectan tu ROI,
guarda backup rotatorio, actualiza sigpac.recintos y sincroniza
los campos SIGPAC en public.recintos (geom + superficie_ha).
 
Autor: Marcos Zamorano Lasso
Versión: 2.0.0
"""
 
import os
from datetime import date
from pathlib import Path
 
import pandas as pd
import requests
import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
 
# (Opcional para geometrías MultiPolygon)
try:
    from geoalchemy2 import Geometry
    _HAS_GEOALCHEMY = True
except ImportError:
    _HAS_GEOALCHEMY = False
 
 
# -----------------------------
# 1) Cargar ROI y calcular bbox
# -----------------------------
roi_path = "../data/processed/roi.gpkg"  # usa gpkg/shp, NO .qgz
roi = gpd.read_file(roi_path).to_crs(4326)  # WGS84 / CRS84
 
minx, miny, maxx, maxy = roi.total_bounds
bbox = (float(minx), float(miny), float(maxx), float(maxy))
print("ROI bbox:", bbox)
 
 
# -------------------------------------------
# 2) Descargar TODOS los recintos por páginas
# -------------------------------------------
def descargar_todo_sigpac_recintos(bbox, limit=10000):
    """
    Descarga todos los recintos SIGPAC que intersectan el bbox paginando con offset.
    limit = tamaño de página (no total).
    """
    base_url = "https://sigpac-hubcloud.es/ogcapi/collections/recintos/items"
    offset = 0
    pages = []
 
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
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
 
    gdf_all = gpd.GeoDataFrame(pd.concat(pages, ignore_index=True), crs="EPSG:4326")
    print(f"✅ Total recintos descargados en bbox: {len(gdf_all)}")
    return gdf_all
 
 
print("\nDescargando recintos del SIGPAC…")
gdf_recintos = descargar_todo_sigpac_recintos(bbox, limit=10000)
 
# Normalizar geometrías a MultiPolygon, por si acaso
gdf_recintos["geometry"] = gdf_recintos["geometry"].apply(
    lambda geom: geom if geom.geom_type == "MultiPolygon" else geom.buffer(0)
)
 
 
# ---------------------------------------------------
# 3) Guardar backup local ROTATORIO (solo 2 últimos)
# ---------------------------------------------------
out_dir = Path("data/raw/sigpac")
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
# 4) Volcar a PostGIS en CHUNKS (sigpac.recintos)
# ---------------------------------------------------
print("\nEscribiendo en PostGIS (sigpac.recintos)…")
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
 
    # Si la tabla sigpac.recintos existe, la vaciamos; si no existe, no pasa nada
    conn.execute(text(
        """
        DO $$
        BEGIN
            IF to_regclass('sigpac.recintos') IS NOT NULL THEN
                TRUNCATE TABLE sigpac.recintos;
            END IF;
        END
        $$;
        """
    ))
 
# dtype robusto para MultiPolygon si tienes geoalchemy2
dtype = None
if _HAS_GEOALCHEMY:
    dtype = {"geometry": Geometry("MULTIPOLYGON", srid=4326)}
 
# IMPORTANTE: ahora usamos if_exists="append" para no intentar hacer DROP TABLE
gdf_recintos.to_postgis(
    name="recintos",
    con=engine,
    schema="sigpac",
    if_exists="append",   # antes era "replace"
    index=False,
    chunksize=5000,
    dtype=dtype
)
 
print("✅ Tabla sigpac.recintos actualizada correctamente (TRUNCATE + INSERT).")
 
 
# ---------------------------------------------------
# 5) Sincronizar campos SIGPAC en public.recintos
#    (modelo B: actualizar geom + superficie_ha, insertar nuevos)
# ---------------------------------------------------
print("\nSincronizando public.recintos con sigpac.recintos (geom + superficie_ha)…")
 
with engine.begin() as conn:
    # 5.1) Actualizar recintos ya existentes (mismas claves SIGPAC)
    conn.execute(text(
        """
        UPDATE public.recintos AS r
        SET
          geom = s.geometry,
          superficie_ha = ST_Area(ST_Transform(s.geometry, 3857)) / 10000.0
        FROM sigpac.recintos AS s
        WHERE
              r.provincia = s.provincia
          AND r.municipio = s.municipio
          AND COALESCE(r.agregado, -1) = COALESCE(s.agregado, -1)
          AND COALESCE(r.zona, -1)     = COALESCE(s.zona, -1)
          AND r.poligono = s.poligono
          AND r.parcela  = s.parcela
          AND r.recinto  = s.recinto
        ;
        """
    ))
 
    # 5.2) Insertar recintos nuevos que no existían en public.recintos
    conn.execute(text(
        """
        INSERT INTO public.recintos (
            nombre,
            superficie_ha,
            geom,
            fecha_creacion,
            activa,
            provincia,
            municipio,
            agregado,
            zona,
            poligono,
            parcela,
            recinto
        )
        SELECT
            -- nombre por defecto: prov-muni-pol-parc-rec
            (s.provincia::text || '-' ||
             s.municipio::text || '-' ||
             s.poligono::text  || '-' ||
             s.parcela::text   || '-' ||
             s.recinto::text)      AS nombre,
            ST_Area(ST_Transform(s.geometry, 3857)) / 10000.0 AS superficie_ha,
            s.geometry                   AS geom,
            NOW() AT TIME ZONE 'UTC'     AS fecha_creacion,
            TRUE                         AS activa,
            s.provincia,
            s.municipio,
            s.agregado,
            s.zona,
            s.poligono,
            s.parcela,
            s.recinto
        FROM sigpac.recintos AS s
        LEFT JOIN public.recintos AS r
          ON  r.provincia = s.provincia
          AND r.municipio = s.municipio
          AND COALESCE(r.agregado, -1) = COALESCE(s.agregado, -1)
          AND COALESCE(r.zona, -1)     = COALESCE(s.zona, -1)
          AND r.poligono = s.poligono
          AND r.parcela  = s.parcela
          AND r.recinto  = s.recinto
        WHERE r.id_recinto IS NULL
        ;
        """
    ))
 
print("public.recintos sincronizado (se respetan propietario, nombre personalizado y activa).")
print("Proceso completado.")