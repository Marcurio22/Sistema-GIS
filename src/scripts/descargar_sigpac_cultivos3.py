import os
import sys  
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1])) 

from webapp import create_app, db  

# ============================================================
# Config
# ============================================================
SIGPAC_COLLECTION = "cultivo_declarado"
PG_TABLE          = "cultivo_declarado2"
PG_VIEW           = "v_cultivo_declarado_popup2"

SIGPAC_BASE      = "https://sigpac-hubcloud.es/ogcapi"
DEFAULT_ROI      = "data/processed/ROI.gpkg"
PAGE_LIMIT       = 250
TILE_DEGREES     = 0.05
PAUSE_BETWEEN    = 2

MAX_RETRIES      = 5
RETRY_WAIT_BASE  = 20

DEDUP_KEYS = ["provincia", "municipio", "poligono", "parcela", "recinto"]

# ============================================================
# Helpers
# ============================================================
def find_project_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(15):
        if (cur / "data").exists() and (cur / "src").exists():
            return cur
        cur = cur.parent
    return Path.cwd().resolve()


def get_one_page(base_url: str, params: dict) -> dict:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(base_url, params={**params, "f": "json"}, timeout=120)

            if 400 <= resp.status_code < 500:
                resp.raise_for_status()

            if resp.status_code in (500, 502, 503, 504):
                wait = RETRY_WAIT_BASE * attempt
                print(f"      ⚠️  HTTP {resp.status_code} intento {attempt}/{MAX_RETRIES} — espero {wait}s…")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.Timeout:
            wait = RETRY_WAIT_BASE * attempt
            print(f"      ⚠️  Timeout intento {attempt}/{MAX_RETRIES} — espero {wait}s…")
            time.sleep(wait)

        except requests.exceptions.ConnectionError:
            wait = RETRY_WAIT_BASE * attempt
            print(f"      ⚠️  ConnectionError intento {attempt}/{MAX_RETRIES} — espero {wait}s…")
            time.sleep(wait)

    raise RuntimeError(f"Petición falló {MAX_RETRIES} veces. Parámetros: {params}")


def download_tile(base_url: str, bbox: tuple) -> gpd.GeoDataFrame:
    minx, miny, maxx, maxy = bbox
    bbox_str = f"{minx},{miny},{maxx},{maxy}"
    offset = 0
    tile_pages = []

    while True:
        params = {"bbox": bbox_str, "limit": PAGE_LIMIT, "offset": offset}
        data = get_one_page(base_url, params)

        feats = data.get("features", []) or []
        if not feats:
            break

        gdf_page = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
        if not gdf_page.empty:
            tile_pages.append(gdf_page)

        offset += len(feats)

        if len(feats) < PAGE_LIMIT:
            break

        time.sleep(PAUSE_BETWEEN)

    if not tile_pages:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    return gpd.GeoDataFrame(
        pd.concat([p for p in tile_pages if not p.empty], ignore_index=True),
        crs="EPSG:4326"
    )


def download_sigpac_tiled(collection: str, bbox4326: tuple) -> gpd.GeoDataFrame:
    base_url = f"{SIGPAC_BASE}/collections/{collection}/items"
    minx, miny, maxx, maxy = bbox4326

    xs = np.arange(minx, maxx, TILE_DEGREES)
    ys = np.arange(miny, maxy, TILE_DEGREES)
    total_tiles = len(xs) * len(ys)

    print(f"   Bbox dividido en {len(xs)} x {len(ys)} = {total_tiles} tiles de ~{TILE_DEGREES}° de lado")

    all_gdfs = []
    tile_n = 0

    for x0 in xs:
        for y0 in ys:
            tile_n += 1
            x1 = min(x0 + TILE_DEGREES, maxx)
            y1 = min(y0 + TILE_DEGREES, maxy)

            print(f"   Tile {tile_n}/{total_tiles}: {x0:.4f},{y0:.4f} → {x1:.4f},{y1:.4f}", end=" ")

            gdf_tile = download_tile(base_url, (x0, y0, x1, y1))

            if gdf_tile.empty:
                print("(vacío)")
            else:
                print(f"→ {len(gdf_tile)} features")
                all_gdfs.append(gdf_tile)

            time.sleep(PAUSE_BETWEEN)

    if not all_gdfs:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    gdf_all = gpd.GeoDataFrame(
        pd.concat([g for g in all_gdfs if not g.empty], ignore_index=True),
        crs="EPSG:4326"
    )
    print(f"\n   Total antes de deduplicar: {len(gdf_all)} features")

    keys_existentes = [k for k in DEDUP_KEYS if k in gdf_all.columns]
    if keys_existentes:
        gdf_all = gdf_all.drop_duplicates(subset=keys_existentes, keep="first").reset_index(drop=True)
        print(f"   Total tras deduplicar:    {len(gdf_all)} features")
    else:
        print("   ⚠️  No se encontraron columnas clave para deduplicar.")

    return gdf_all


# ============================================================
# Main
# ============================================================
def main():
    load_dotenv()

    app = create_app()   # ← igual que en el 2º script

    with app.app_context():
        this_dir     = Path(__file__).resolve().parent
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

        print(f"\nDescargando SIGPAC por tiles → PostGIS tabla={PG_TABLE}…\n")
        gdf = download_sigpac_tiled(SIGPAC_COLLECTION, bbox)

        if gdf.empty:
            print("⚠️ Descarga vacía. No se inserta nada.")
            return

        gdf["geometry"] = gdf["geometry"].buffer(0)

        # Backup GPKG
        out_dir = project_root / "data" / "raw" / "sigpac"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp    = date.today().isoformat()
        out_path = out_dir / f"{stamp}_{PG_TABLE}.gpkg"
        gdf.to_file(out_path, driver="GPKG")
        print(f"\nBackup guardado en: {out_path}")

        # PostGIS
        print("\nEscribiendo en PostGIS…")

        db.session.execute(text("CREATE SCHEMA IF NOT EXISTS sigpac"))
        db.session.commit()

        gdf.to_postgis(
            name=PG_TABLE,
            con=db.engine,            # ← db.engine en lugar del engine propio
            schema="sigpac",
            if_exists="replace",
            index=False,
            chunksize=5000,
        )

        db.session.execute(text(f"""
        DO $$
        DECLARE
            cat_reg regclass;
            cat_sql text;
        BEGIN
            cat_reg := to_regclass('public.productos_fega');
            IF cat_reg IS NULL THEN
                cat_reg := to_regclass('sigpac.productos_fega');
            END IF;

            IF cat_reg IS NULL THEN
                EXECUTE '
                CREATE OR REPLACE VIEW sigpac.{PG_VIEW} AS
                SELECT
                    provincia, municipio, poligono, parcela, recinto, agregado, zona,
                    parc_producto,
                    parc_sistexp, parc_supcult, parc_ayudasol, tipo_aprovecha, pdr_rec,
                    cultsecun_producto, cultsecun_ayudasol, parc_indcultapro,
                    NULL::text AS cultivo_actual_nombre,
                    geometry,
                    NULL::text AS parc_producto_nombre
                FROM sigpac.{PG_TABLE}
                ';
            ELSE
                cat_sql := format('
                CREATE OR REPLACE VIEW sigpac.{PG_VIEW} AS
                SELECT
                    c.provincia, c.municipio, c.poligono, c.parcela, c.recinto, c.agregado, c.zona,
                    c.parc_producto,
                    c.parc_sistexp, c.parc_supcult, c.parc_ayudasol, c.tipo_aprovecha, c.pdr_rec,
                    c.cultsecun_producto, c.cultsecun_ayudasol, c.parc_indcultapro,
                    NULL::text AS cultivo_actual_nombre,
                    c.geometry,
                    pf.descripcion AS parc_producto_nombre
                FROM sigpac.{PG_TABLE} c
                LEFT JOIN %s pf
                    ON pf.codigo::double precision = c.parc_producto
                ', cat_reg);

                EXECUTE cat_sql;
            END IF;
        END $$;
        """))
        db.session.commit()

        print(f"\n✅ PostGIS listo: sigpac.{PG_TABLE} + view sigpac.{PG_VIEW}")


if __name__ == "__main__":
    main()