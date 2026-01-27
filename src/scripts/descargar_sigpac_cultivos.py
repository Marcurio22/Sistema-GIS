import os
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ============================================================
# Config
# ============================================================
SIGPAC_COLLECTION = "cultivo_declarado"
SIGPAC_BASE = "https://sigpac-hubcloud.es/ogcapi"
DEFAULT_ROI = "data/processed/ROI.gpkg"
DEFAULT_LIMIT = 1000  # el servidor puede capar (p.ej. 250), pero nuestra paginación funciona igual

# ============================================================
# Helpers
# ============================================================
def find_project_root(start: Path) -> Path:
    """Sube desde start hasta encontrar carpeta con /data y /src."""
    cur = start.resolve()
    for _ in range(15):
        if (cur / "data").exists() and (cur / "src").exists():
            return cur
        cur = cur.parent
    return Path.cwd().resolve()


def download_sigpac_bbox(collection: str, bbox4326, requested_limit: int) -> gpd.GeoDataFrame:
    """
    Descarga una colección OGC API Features por bbox usando offset.
    Robusto ante servidores que ignoran tu limit y devuelven un máximo fijo (p.ej. 250).
    """
    base_url = f"{SIGPAC_BASE}/collections/{collection}/items"
    offset = 0
    pages = []
    page = 0
    total_matched = None

    # Algunos endpoints fallan con application/geo+json; json suele funcionar
    formats = ["application/geo+json", "json"]

    while True:
        page += 1
        ok = False
        last_err = None
        data = None
        resp = None

        for fval in formats:
            params = {
                "f": fval,
                "bbox": f"{bbox4326[0]},{bbox4326[1]},{bbox4326[2]},{bbox4326[3]}",
                "limit": requested_limit,
                "offset": offset,
            }
            try:
                resp = requests.get(base_url, params=params, timeout=180)
                print(f"→ Página {page} offset={offset} URL: {resp.url}")
                resp.raise_for_status()
                data = resp.json()
                ok = True
                break
            except Exception as e:
                last_err = e

        if not ok:
            raise last_err

        feats = data.get("features", []) or []
        total_matched = data.get("numberMatched", total_matched)
        number_returned = data.get("numberReturned")

        print(f"   numberMatched={total_matched} numberReturned={number_returned} feats={len(feats)}")

        if len(feats) == 0:
            break

        gdf_page = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
        if not gdf_page.empty:
            pages.append(gdf_page)

        # ✅ avanzar según lo devuelto realmente
        offset += len(feats)

    if not pages:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    # Evita warnings futuros: concat solo de páginas no vacías
    gdf_all = gpd.GeoDataFrame(pd.concat(pages, ignore_index=True), crs="EPSG:4326")
    print(f"✅ Descarga completa colección={collection}. Total features: {len(gdf_all)} (matched={total_matched})")
    return gdf_all


def build_engine_from_env():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    pwd = os.getenv("POSTGRES_PASSWORD")

    if not all([db, user, pwd]):
        raise RuntimeError("Faltan POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD en .env")

    db_url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    return create_engine(db_url)


# ============================================================
# Main
# ============================================================
def main():
    load_dotenv()

    this_dir = Path(__file__).resolve().parent
    project_root = find_project_root(this_dir)

    roi_path = Path(os.getenv("ROI_PATH", DEFAULT_ROI))
    if not roi_path.is_absolute():
        roi_path = (project_root / roi_path).resolve()

    if not roi_path.exists():
        raise FileNotFoundError(f"ROI no encontrado: {roi_path}")

    print("ROI path:", roi_path)

    roi = gpd.read_file(roi_path).to_crs(4326)
    minx, miny, maxx, maxy = roi.total_bounds
    bbox = (float(minx), float(miny), float(maxx), float(maxy))
    print("ROI bbox:", bbox)

    requested_limit = int(os.getenv("SIGPAC_LIMIT", str(DEFAULT_LIMIT)))

    print(f"\nDescargando capa SIGPAC ({SIGPAC_COLLECTION})…")
    gdf = download_sigpac_bbox(SIGPAC_COLLECTION, bbox, requested_limit=requested_limit)

    if gdf.empty:
        print("⚠️ SIGPAC devolvió 0 features para ese bbox. No se inserta nada.")
        return

    # Arreglo mínimo de geometrías (si alguna es inválida)
    # buffer(0) puede convertir Polygon->Polygon; no forzamos MultiPolygon porque el servicio ya suele venir bien
    gdf["geometry"] = gdf["geometry"].buffer(0)

    # Backup GPKG
    out_dir = project_root / "data" / "raw" / "sigpac"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    out_path = out_dir / f"{stamp}_{SIGPAC_COLLECTION}.gpkg"
    gdf.to_file(out_path, driver="GPKG")
    print(f"\nBackup guardado en: {out_path}")

    # PostGIS: tabla espejo + índices + vista popup
    print("\nEscribiendo en PostGIS…")
    engine = build_engine_from_env()

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS sigpac"))

    # ✅ Tabla espejo (todas las columnas, mismos nombres, tipos compatibles)
    # Esto evita el problema de parc_producto=99.0 vs INTEGER
    gdf.to_postgis(
        name=SIGPAC_COLLECTION,
        con=engine,
        schema="sigpac",
        if_exists="replace",
        index=False,
        chunksize=5000,
    )

    # Índices útiles para WMS/QGIS y consultas
    with engine.begin() as conn:
        # Índices (igual que antes)
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {SIGPAC_COLLECTION}_gix "
            f"ON sigpac.{SIGPAC_COLLECTION} USING GIST (geometry)"
        ))

        conn.execute(text(f"""
        DO $$
        BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='sigpac' AND table_name='{SIGPAC_COLLECTION}' AND column_name='provincia')
            AND EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='sigpac' AND table_name='{SIGPAC_COLLECTION}' AND column_name='municipio')
            AND EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='sigpac' AND table_name='{SIGPAC_COLLECTION}' AND column_name='poligono')
            AND EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='sigpac' AND table_name='{SIGPAC_COLLECTION}' AND column_name='parcela')
            AND EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='sigpac' AND table_name='{SIGPAC_COLLECTION}' AND column_name='recinto')
        THEN
            EXECUTE 'CREATE INDEX IF NOT EXISTS {SIGPAC_COLLECTION}_keys_ix
                    ON sigpac.{SIGPAC_COLLECTION} (provincia, municipio, poligono, parcela, recinto)';
        END IF;
        END $$;
        """))

        # ✅ VIEW robusta: crea con join a catálogo SOLO si existe una tabla catálogo real
        conn.execute(text(f"""
        DO $$
        DECLARE
        cat_reg regclass;
        cat_sql text;
        BEGIN
        -- Busca una tabla catálogo existente (ajusta/añade aquí si tu catálogo tiene otro nombre)
        cat_reg := to_regclass('sigpac.productos_fea');
        IF cat_reg IS NULL THEN
            cat_reg := to_regclass('public.productos_fea');
        END IF;

        IF cat_reg IS NULL THEN
            -- No hay catálogo: vista sin nombre del cultivo
            EXECUTE '
            CREATE OR REPLACE VIEW sigpac.v_cultivo_declarado_popup AS
            SELECT
                provincia, municipio, poligono, parcela, recinto, agregado, zona,
                parc_producto,
                parc_sistexp, parc_supcult, parc_ayudasol, tipo_aprovecha, pdr_rec,
                cultsecun_producto, cultsecun_ayudasol, parc_indcultapro,
                NULL::text AS cultivo_actual_nombre,
                geometry
            FROM sigpac.{SIGPAC_COLLECTION}
            ';
        ELSE
            -- Hay catálogo: vista con join a catálogo
            cat_sql := format('
            CREATE OR REPLACE VIEW sigpac.v_cultivo_declarado_popup AS
            SELECT
                c.provincia, c.municipio, c.poligono, c.parcela, c.recinto, c.agregado, c.zona,
                c.parc_producto,
                c.parc_sistexp, c.parc_supcult, c.parc_ayudasol, c.tipo_aprovecha, c.pdr_rec,
                c.cultsecun_producto, c.cultsecun_ayudasol, c.parc_indcultapro,
                p.descripcion AS cultivo_actual_nombre,
                c.geometry
            FROM sigpac.{SIGPAC_COLLECTION} c
            LEFT JOIN %s p
                ON p.codigo::text = c.parc_producto::text
            ', cat_reg);

            EXECUTE cat_sql;
        END IF;
        END $$;
        """))

    print(f"✅ PostGIS listo: sigpac.{SIGPAC_COLLECTION} + índices + view sigpac.v_cultivo_declarado_popup")
    print("Siguiente paso: publicar en GeoServer como WMS desde PostGIS (recomendado).")


if __name__ == "__main__":
    main()