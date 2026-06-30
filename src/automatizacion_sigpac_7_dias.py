"""
descargar_sigpac_recintos.py

Descarga todos los recintos SIGPAC que intersectan tu ROI,
los vuelca a PostGIS usando una actualización atómica
(tabla temporal + renombrado).

Ejecutar manualmente o via cron cuando se necesite.
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import geopandas as gpd
from sqlalchemy import create_engine, text

# ── Localizar raíz del proyecto y añadir al path ──────────────────────────────
def find_project_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(15):
        if (cur / "data").exists() and (cur / "src").exists():
            return cur
        cur = cur.parent
    return Path.cwd().resolve()

THIS_DIR     = Path(__file__).resolve().parent
PROJECT_ROOT = find_project_root(THIS_DIR)
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from webapp.config import Config  # usa el mismo Config que el resto de la app

try:
    from geoalchemy2 import Geometry
    _HAS_GEOALCHEMY = True
except ImportError:
    _HAS_GEOALCHEMY = False

# ── Constantes ────────────────────────────────────────────────────────────────
SIGPAC_BASE    = "https://sigpac-hubcloud.es/ogcapi"
COLLECTION     = "recintos"           # ← cambia si el endpoint se llama distinto
DEFAULT_ROI    = "data/processed/roi.gpkg"
PAGE_LIMIT     = 250                  # tamaño de página seguro para la API
TILE_DEGREES   = 0.05                 # misma estrategia de tiles que cultivo_declarado
PAUSE_BETWEEN  = 2                    # segundos entre peticiones

MAX_RETRIES    = 5
RETRY_WAIT_BASE = 20

DEDUP_KEYS = ["provincia", "municipio", "poligono", "parcela", "recinto"]


# ══════════════════════════════════════════════════════════════════════════════
# Helpers de descarga (misma estrategia de tiles que funciona en cultivo_declarado)
# ══════════════════════════════════════════════════════════════════════════════

def check_collection_exists(collection: str) -> bool:
    """Comprueba que la colección existe en la API antes de intentar descargar."""
    url = f"{SIGPAC_BASE}/collections?f=json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        ids = [c["id"] for c in resp.json().get("collections", [])]
        if collection not in ids:
            print(f"⚠️  Colección '{collection}' no encontrada.")
            print(f"   Colecciones disponibles: {ids}")
            return False
        return True
    except Exception as e:
        print(f"⚠️  No se pudo verificar colecciones: {e}")
        print("   Continuando de todas formas…")
        return True  # intentar igualmente


def get_one_page(base_url: str, params: dict) -> dict:
    import time
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
            import time as t
            wait = RETRY_WAIT_BASE * attempt
            print(f"      ⚠️  Timeout intento {attempt}/{MAX_RETRIES} — espero {wait}s…")
            t.sleep(wait)

        except requests.exceptions.ConnectionError:
            import time as t
            wait = RETRY_WAIT_BASE * attempt
            print(f"      ⚠️  ConnectionError intento {attempt}/{MAX_RETRIES} — espero {wait}s…")
            t.sleep(wait)

    raise RuntimeError(f"Petición falló {MAX_RETRIES} veces. Parámetros: {params}")


def download_tile(base_url: str, bbox: tuple) -> gpd.GeoDataFrame:
    import time
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
        pd.concat(tile_pages, ignore_index=True),
        crs="EPSG:4326"
    )


def download_sigpac_tiled(collection: str, bbox4326: tuple) -> gpd.GeoDataFrame:
    import time
    base_url = f"{SIGPAC_BASE}/collections/{collection}/items"
    minx, miny, maxx, maxy = bbox4326

    xs = np.arange(minx, maxx, TILE_DEGREES)
    ys = np.arange(miny, maxy, TILE_DEGREES)
    total_tiles = len(xs) * len(ys)

    print(f"   Bbox dividido en {len(xs)} × {len(ys)} = {total_tiles} tiles de {TILE_DEGREES}°")

    all_gdfs = []
    for tile_n, (x0, y0) in enumerate(
        ((x, y) for x in xs for y in ys), start=1
    ):
        x1 = min(x0 + TILE_DEGREES, maxx)
        y1 = min(y0 + TILE_DEGREES, maxy)

        print(f"   Tile {tile_n}/{total_tiles}: {x0:.4f},{y0:.4f} → {x1:.4f},{y1:.4f}", end=" ", flush=True)
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
        pd.concat(all_gdfs, ignore_index=True),
        crs="EPSG:4326"
    )
    print(f"\n   Total antes de deduplicar: {len(gdf_all)} features")

    keys = [k for k in DEDUP_KEYS if k in gdf_all.columns]
    if keys:
        gdf_all = gdf_all.drop_duplicates(subset=keys, keep="first").reset_index(drop=True)
        print(f"   Total tras deduplicar:    {len(gdf_all)} features")
    else:
        print("   ⚠️  No se encontraron columnas clave para deduplicar.")

    return gdf_all


# ══════════════════════════════════════════════════════════════════════════════
# Backup local
# ══════════════════════════════════════════════════════════════════════════════

def guardar_backup_rotatorio(gdf: gpd.GeoDataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    out_path = out_dir / f"{stamp}_recintos.gpkg"
    gdf.to_file(out_path, driver="GPKG")
    print(f"\nBackup guardado en: {out_path}")

    # Mantener solo los 2 últimos
    files = sorted(out_dir.glob("*_recintos.gpkg"))
    for f in files[:-2]:
        f.unlink(missing_ok=True)
        print(f"Backup antiguo eliminado: {f}")


# ══════════════════════════════════════════════════════════════════════════════
# PostGIS — actualización atómica
# ══════════════════════════════════════════════════════════════════════════════

def actualizar_postgis_atomic(gdf: gpd.GeoDataFrame) -> None:
    """
    1) Escribe en sigpac.recintos_new (tabla temporal).
    2) UPSERT en public.parcelas.
    3) Asigna id_parcela a recintos_new.
    4) Intercambio atómico recintos_new → recintos.
    5) FK + índices.
    """
    engine = create_engine(
        Config.SQLALCHEMY_DATABASE_URI,
        **Config.SQLALCHEMY_ENGINE_OPTIONS,
    )

    dtype = {"geometry": Geometry("POLYGON", srid=4326)} if _HAS_GEOALCHEMY else None

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS sigpac"))

    print("→ Escribiendo en sigpac.recintos_new…")
    gdf.to_postgis(
        name="recintos_new",
        con=engine,
        schema="sigpac",
        if_exists="replace",
        index=False,
        chunksize=5000,
        dtype=dtype,
    )

    with engine.begin() as conn:
        print("→ UPSERT en public.parcelas…")
        conn.execute(text("""
            INSERT INTO public.parcelas (
                nombre, superficie_ha, geom,
                provincia, municipio, agregado, zona, poligono, recinto
            )
            SELECT
                format('recinto %s-%s-%s-%s-%s-%s',
                    r.provincia, r.municipio,
                    COALESCE(r.agregado, 0), COALESCE(r.zona, 0),
                    r.poligono, r.recinto
                ) AS nombre,
                ST_Area(ST_Transform(ST_Union(r.geometry), 3857)) / 10000.0 AS superficie_ha,
                ST_Multi(ST_Union(r.geometry)) AS geom,
                r.provincia, r.municipio, r.agregado, r.zona, r.poligono, r.recinto
            FROM sigpac.recintos_new r
            GROUP BY r.provincia, r.municipio, r.agregado, r.zona, r.poligono, r.recinto
            ON CONFLICT (provincia, municipio, agregado, zona, poligono, recinto)
            DO UPDATE SET
                geom          = EXCLUDED.geom,
                superficie_ha = EXCLUDED.superficie_ha
        """))

        print("→ Asignando id_parcela a recintos_new…")
        conn.execute(text("ALTER TABLE sigpac.recintos_new ADD COLUMN id_parcela integer"))
        conn.execute(text("""
            UPDATE sigpac.recintos_new r
            SET id_parcela = p.id_parcela
            FROM public.parcelas p
            WHERE
                r.provincia = p.provincia
                AND r.municipio = p.municipio
                AND r.poligono  = p.poligono
                AND r.recinto   = p.recinto
                AND r.agregado  IS NOT DISTINCT FROM p.agregado
                AND r.zona      IS NOT DISTINCT FROM p.zona
        """))

        missing = conn.execute(
            text("SELECT COUNT(*) FROM sigpac.recintos_new WHERE id_parcela IS NULL")
        ).scalar()
        if missing and missing > 0:
            raise RuntimeError(
                f"{missing} recintos sin id_parcela. Revisa public.parcelas."
            )

        print("→ Intercambio atómico de tablas…")
        conn.execute(text("DROP TABLE IF EXISTS sigpac.recintos_old"))
        conn.execute(text("ALTER TABLE IF EXISTS sigpac.recintos RENAME TO recintos_old"))
        conn.execute(text("ALTER TABLE sigpac.recintos_new RENAME TO recintos"))
        conn.execute(text("DROP TABLE IF EXISTS sigpac.recintos_old"))

        print("→ FK e índices…")
        conn.execute(text("""
            ALTER TABLE sigpac.recintos
            ALTER COLUMN id_parcela SET NOT NULL
        """))
        conn.execute(text("""
            ALTER TABLE sigpac.recintos
            ADD CONSTRAINT recintos_parcelas_fk
            FOREIGN KEY (id_parcela)
            REFERENCES public.parcelas(id_parcela)
            ON DELETE RESTRICT
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_recintos_id_parcela
            ON sigpac.recintos(id_parcela)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_recintos_geom
            ON sigpac.recintos USING GIST(geometry)
        """))

    print("✅ sigpac.recintos y public.parcelas actualizadas correctamente.")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n========================")
    print("  ACTUALIZACIÓN SIGPAC  ")
    print("========================\n")

    # ── ROI ──────────────────────────────────────────────────────────────────
    roi_path = PROJECT_ROOT / DEFAULT_ROI
    if not roi_path.exists():
        raise FileNotFoundError(f"ROI no encontrado: {roi_path}")

    roi = gpd.read_file(roi_path).to_crs(4326)
    minx, miny, maxx, maxy = roi.total_bounds
    bbox = (float(minx), float(miny), float(maxx), float(maxy))
    print("ROI bbox:", bbox)

    # ── Verificar colección ───────────────────────────────────────────────────
    if not check_collection_exists(COLLECTION):
        print("\n❌ Abortando: colección no disponible.")
        print("   Comprueba https://sigpac-hubcloud.es/ogcapi/collections?f=json")
        print("   y actualiza la constante COLLECTION al nombre correcto.")
        return

    # ── Descarga por tiles ────────────────────────────────────────────────────
    print(f"\nDescargando colección '{COLLECTION}' por tiles…\n")
    gdf = download_sigpac_tiled(COLLECTION, bbox)

    if gdf.empty:
        print("⚠️  Descarga vacía. No se actualiza PostGIS.")
        return

    gdf["geometry"] = gdf["geometry"].buffer(0)

    # ── Backup ────────────────────────────────────────────────────────────────
    guardar_backup_rotatorio(gdf, PROJECT_ROOT / "data" / "raw" / "sigpac")

    # ── PostGIS ───────────────────────────────────────────────────────────────
    print("\nActualizando PostGIS…")
    actualizar_postgis_atomic(gdf)

    print("\n✅ Proceso completado.\n")


if __name__ == "__main__":
    main()