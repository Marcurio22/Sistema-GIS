"""
descargar_sigpac_cultivos.py
 
Descarga todas las parcelas/cultivos SIGPAC que intersectan tu ROI,
guarda backup rotatorio y actualiza sigpac.cultivo_declarado.
 
Autor: Adaptado para cultivos declarados
Versión: 1.0.0
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
# 2) Listar colecciones disponibles
# -------------------------------------------
def listar_colecciones():
    """Lista todas las colecciones disponibles en el servicio SIGPAC."""
    url = "https://sigpac-hubcloud.es/ogcapi/collections?f=json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        colecciones = data.get("collections", [])
        print("\n📋 Colecciones disponibles:")
        for col in colecciones:
            nombre = col.get("id", "sin nombre")
            titulo = col.get("title", "")
            print(f"  • {nombre} - {titulo}")
        return [col.get("id") for col in colecciones]
    except Exception as e:
        print(f"⚠️ Error al listar colecciones: {e}")
        return []

print("\nConsultando colecciones disponibles...")
colecciones = listar_colecciones()

# -------------------------------------------
# 3) Descargar TODOS los cultivos por páginas
# -------------------------------------------
def descargar_todo_sigpac_cultivos(bbox, collection_name, limit=10000):
    """
    Descarga todas las parcelas/cultivos SIGPAC que intersectan el bbox paginando con offset.
    limit = tamaño de página (no total).
    """
    base_url = f"https://sigpac-hubcloud.es/ogcapi/collections/{collection_name}/items"
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
        try:
            resp = requests.get(url, timeout=180)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"⚠️ Error en página offset={offset}: {e}")
            break
 
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
    print(f"✅ Total parcelas/cultivos descargados en bbox: {len(gdf_all)}")
    return gdf_all
 
 
print("\nDescargando cultivos/parcelas del SIGPAC…")
print("Usando colección: cultivo_declarado")

gdf_cultivos = descargar_todo_sigpac_cultivos(bbox, "cultivo_declarado", limit=10000)

if gdf_cultivos is None or len(gdf_cultivos) == 0:
    print("\n❌ No se encontraron datos en la colección 'cultivo_declarado'")
    print(f"Bbox usado: {bbox}")
    print("\nPosibles causas:")
    print("  1. No hay cultivos declarados en ese bbox")
    print("  2. El servicio requiere filtros adicionales")
    print("  3. Problema temporal del servicio")
    
    # Intentar una consulta de prueba sin bbox
    print("\nProbando consulta sin bbox para verificar que la colección funciona...")
    test_url = "https://sigpac-hubcloud.es/ogcapi/collections/cultivo_declarado/items?f=json&limit=10"
    try:
        resp = requests.get(test_url, timeout=30)
        resp.raise_for_status()
        test_data = resp.json()
        test_feats = test_data.get("features", [])
        print(f"  → Consulta sin bbox devuelve {len(test_feats)} features")
        if len(test_feats) > 0:
            print("  → La colección funciona pero tu bbox no intersecta con datos")
            print(f"  → Verifica que el ROI ({roi_path}) sea correcto")
    except Exception as e:
        print(f"  → Error en consulta de prueba: {e}")
    
    exit(0)
 
# Normalizar geometrías a MultiPolygon, por si acaso
if len(gdf_cultivos) > 0:
    gdf_cultivos["geometry"] = gdf_cultivos["geometry"].apply(
        lambda geom: geom if geom.geom_type == "MultiPolygon" else geom.buffer(0)
    )
 
 
# ---------------------------------------------------
# 3) Guardar backup local ROTATORIO (solo 2 últimos)
# ---------------------------------------------------
out_dir = Path("data/raw/sigpac")
out_dir.mkdir(parents=True, exist_ok=True)
 
stamp = date.today().isoformat()
cultivo_path = out_dir / f"{stamp}_cultivos.gpkg"
 
if len(gdf_cultivos) > 0:
    gdf_cultivos.to_file(cultivo_path, driver="GPKG")
    print(f"\nBackup guardado en: {cultivo_path}")
 
    # Mantener solo los 2 últimos backups
    files = sorted(out_dir.glob("*_cultivos.gpkg"))
    for f in files[:-2]:
        f.unlink(missing_ok=True)
        print(f"Backup antiguo eliminado: {f}")
else:
    print("\n⚠️ No hay datos para guardar backup")
 
 
# ---------------------------------------------------
# 4) Volcar a PostGIS en CHUNKS (sigpac.cultivo_declarado)
# ---------------------------------------------------
if len(gdf_cultivos) == 0:
    print("\n⚠️ No hay datos para cargar en la base de datos")
    exit(0)

print("\nEscribiendo en PostGIS (sigpac.cultivo_declarado)…")
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
 
    # Si la tabla sigpac.cultivo_declarado existe, la vaciamos; si no existe, no pasa nada
    conn.execute(text(
        """
        DO $$
        BEGIN
            IF to_regclass('sigpac.cultivo_declarado') IS NOT NULL THEN
                TRUNCATE TABLE sigpac.cultivo_declarado;
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
gdf_cultivos.to_postgis(
    name="cultivo_declarado",
    con=engine,
    schema="sigpac",
    if_exists="append",   # antes era "replace"
    index=False,
    chunksize=5000,
    dtype=dtype
)
 
print("✅ Tabla sigpac.cultivo_declarado actualizada correctamente (TRUNCATE + INSERT).")
print(f"   Total de registros cargados: {len(gdf_cultivos)}")
 
# Opcional: Mostrar estructura de datos
print("\nColumnas disponibles en cultivo_declarado:")
print(gdf_cultivos.columns.tolist())

print("\nProceso completado.")