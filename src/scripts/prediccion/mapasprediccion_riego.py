"""
Genera mapas de predicción de riego (ETc = ET₀ × Kc) para 4 días.

- ET₀: CSV de predicciones (mismo que mapasprediccion.py)
- Kc: fórmula según cultivo (cultivos_kc.csv) × NDVI (mosaico ndvi_diax.py)
- Publica capas WMS en GeoServer: riego_prediccion_0..3
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from dotenv import load_dotenv
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds as window_from_bounds
from shapely import wkt
from shapely.geometry import mapping, shape
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kc_calculo import calc_kc, load_kc_catalog, lookup_cultivo

load_dotenv()

ROOT = Path(__file__).resolve().parents[3]

GEOSERVER_BASE_URL = os.getenv("GEOSERVER_WMS_URL", "").replace("/wms", "").rstrip("/")
GEOSERVER_USER     = os.getenv("GEOSERVER_USER")
GEOSERVER_PASSWORD = os.getenv("GEOSERVER_PASSWORD")
WORKSPACE          = "gis_project"

DB_USER     = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST     = os.getenv("POSTGRES_HOST")
DB_PORT     = os.getenv("POSTGRES_PORT")
DB_NAME     = os.getenv("POSTGRES_DB")

CARPETA_CSV = ROOT / "Prediccion" / "salidaPred"
STATIC_DIR  = ROOT / "src" / "webapp" / "static" / "riego_prediccion"
NDVI_DIR    = ROOT / "data" / "processed" / "ndvi_composite"
os.makedirs(STATIC_DIR, exist_ok=True)

AUTH         = (GEOSERVER_USER, GEOSERVER_PASSWORD)
HEADERS_JSON = {"Content-Type": "application/json"}

engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# ── Utilidades ────────────────────────────────────────────────────────────────

def deficit_mm_desde_etc(riego_mm: float, ev_ref: float) -> float:
    """
    Demanda hídrica diaria del cultivo (ETc = ET₀ × Kc).
    Se usa directamente como déficit porque Kc < 1 siempre hace ETc < ET₀,
    por lo que comparar ETc vs ET₀ siempre daría 0.
    ev_ref se conserva como parámetro para posible ajuste futuro por lluvia.
    """
    return max(0.0, float(riego_mm))


def calcular_color_riego(etp_valor: float, ev_ref: float) -> str:
    """
    Mismo criterio que el mapa de ET de referencia (mapasprediccion.calcular_color):
    rojo si ET₀ predicha > ET₀ de referencia (Ev_t); azul en caso contrario.
    El Kc solo afecta a riego_mm (ETc), no al color del mapa.
    """
    return "red" if float(etp_valor) > float(ev_ref) else "blue"


def formato_volumen_mapa(deficit_mm: float) -> str:
    """Etiqueta compacta en m³/ha (1 mm de déficit ≈ 10 m³/ha)."""
    d = float(deficit_mm)
    if d <= 0:
        return ""
    m3_ha = d * 10
    if m3_ha >= 100:
        return f"{m3_ha:.0f} m³/ha"
    return f"{m3_ha:.1f} m³/ha"


def area_superficie_desde_geom(geom) -> tuple[float, float]:
    """Devuelve (area_m2, superficie_ha) en UTM 25830."""
    g = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs("EPSG:25830")
    area_m2 = float(g.area.iloc[0])
    return area_m2, round(area_m2 / 10000.0, 4)


def litros_desde_deficit_y_area(deficit_mm: float, area_m2: float) -> int:
    """Déficit (mm) × m² = litros a aportar ese día."""
    return int(round(float(deficit_mm) * float(area_m2)))


def buscar_csv_reciente() -> Path:
    archivos = glob.glob(str(CARPETA_CSV / "predicciones_*.csv"))
    if not archivos:
        raise FileNotFoundError(f"No se encontró ningún CSV en {CARPETA_CSV}")
    return Path(max(archivos, key=os.path.getmtime))


def detectar_columnas_et(df: pd.DataFrame) -> list[str]:
    cols = [c for c in df.columns if c.startswith("ET_")]
    def parse_fecha(col):
        d, m = col.replace("ET_", "").split("/")
        return datetime(datetime.now().year, int(m), int(d))
    return sorted(cols, key=parse_fecha)


def buscar_ndvi_tif_reciente() -> Path | None:
    archivos = list(NDVI_DIR.glob("ndvi_pc_*_mosaic_utm.tif"))
    if not archivos:
        return None
    return max(archivos, key=lambda p: p.stat().st_mtime)


def fast_bbox_from_predictions(df: pd.DataFrame, pad: float = 0.02) -> tuple[float, float, float, float]:
    """Bounding box aproximado del CSV sin parsear cada geometría con shapely."""
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for wkt_str in df["geometry_wkt"]:
        for lng_s, lat_s in re.findall(r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)", str(wkt_str)):
            lng, lat = float(lng_s), float(lat_s)
            minx = min(minx, lng)
            miny = min(miny, lat)
            maxx = max(maxx, lng)
            maxy = max(maxy, lat)
    if not all(map(np.isfinite, (minx, miny, maxx, maxy))):
        raise ValueError("No se pudo calcular el bbox del CSV de predicciones")
    return minx - pad, miny - pad, maxx + pad, maxy + pad


def cargar_recintos_en_bbox(bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    """Solo recintos que intersectan el área de predicción (mucho más rápido)."""
    minx, miny, maxx, maxy = bbox
    sql_count = text(f"""
        SELECT COUNT(*) FROM recintos
        WHERE geom && ST_MakeEnvelope({minx}, {miny}, {maxx}, {maxy}, 4326)
    """)
    sql_load = f"""
        SELECT id_recinto, id_propietario, geom
        FROM recintos
        WHERE geom && ST_MakeEnvelope({minx}, {miny}, {maxx}, {maxy}, 4326)
    """
    with engine.connect() as conn:
        total = conn.execute(sql_count).scalar()
    print(f"  Recintos en área de predicción: {total:,}")

    t0 = time.perf_counter()
    gdf = gpd.read_postgis(sql_load, engine, geom_col="geom", crs="EPSG:4326")
    print(f"  Recintos cargados en {time.perf_counter() - t0:.1f}s")
    return gdf


def ndvi_at_centroid(dataset, geom_wgs84) -> float | None:
    """NDVI en el centroide (mucho más rápido que media zonal para miles de polígonos)."""
    try:
        centroid = geom_wgs84.centroid
        pt = transform_geom("EPSG:4326", dataset.crs, mapping(centroid))
        x, y = pt["coordinates"][:2]
        samples = list(dataset.sample([(x, y)]))
        if samples:
            val = float(samples[0][0])
            if np.isfinite(val):
                return val
    except Exception:
        pass
    return None


def zonal_ndvi_mean(dataset, geom_wgs84) -> float | None:
    """Media NDVI dentro de una geometría WGS84."""
    try:
        geom_proj = shape(
            transform_geom("EPSG:4326", dataset.crs, mapping(geom_wgs84))
        )
    except Exception:
        return None

    minx, miny, maxx, maxy = geom_proj.bounds
    win = window_from_bounds(minx, miny, maxx, maxy, transform=dataset.transform)
    win = win.round_offsets().round_lengths()
    if win.width <= 0 or win.height <= 0:
        return None

    arr = dataset.read(1, window=win).astype(np.float32)
    if not np.any(np.isfinite(arr)):
        return None

    win_transform = dataset.window_transform(win)
    mask = geometry_mask(
        [mapping(geom_proj)],
        transform=win_transform,
        out_shape=arr.shape,
        invert=True,
    )
    vals = arr[mask]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return None
    return float(vals.mean())


def cargar_ndvi_por_recinto() -> dict[int, float]:
    """Respaldo: último NDVI medio por recinto desde indices_raster."""
    sql = text("""
        SELECT DISTINCT ON (ir.id_recinto)
            ir.id_recinto,
            ir.valor_medio AS ndvi
        FROM public.indices_raster ir
        WHERE ir.tipo_indice = 'NDVI'
          AND ir.valor_medio IS NOT NULL
        ORDER BY ir.id_recinto, ir.fecha_ndvi DESC NULLS LAST
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    return {int(r["id_recinto"]): float(r["ndvi"]) for r in rows}


def ndvi_desde_recintos(geom, recintos_gdf, ndvi_recinto: dict[int, float]) -> float | None:
    """NDVI medio de recintos que intersectan el polígono (fallback sin raster)."""
    try:
        g = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
        rec = recintos_gdf[["id_recinto", "geom"]].rename(columns={"geom": "geometry"})
        joined = gpd.sjoin(g, rec, how="inner", predicate="intersects")
        if joined.empty:
            return None
        vals = [
            ndvi_recinto[int(rid)]
            for rid in joined["id_recinto"].unique()
            if int(rid) in ndvi_recinto
        ]
        return float(np.mean(vals)) if vals else None
    except Exception:
        return None


# ── Generar tablas PostGIS ────────────────────────────────────────────────────

def generar_tablas_postgis():
    csv_path = buscar_csv_reciente()
    print(f"CSV encontrado: {csv_path}")

    df = pd.read_csv(csv_path)
    columnas_et = detectar_columnas_et(df)
    print(f"Columnas ET detectadas: {columnas_et}")

    kc_catalog = load_kc_catalog()
    print(f"Catálogo Kc: {len(kc_catalog)} cultivos")

    ndvi_tif = buscar_ndvi_tif_reciente()
    print("Cargando NDVI por recinto (indices_raster)...")
    t0 = time.perf_counter()
    ndvi_recinto = cargar_ndvi_por_recinto()
    print(f"  {len(ndvi_recinto):,} recintos con NDVI ({time.perf_counter() - t0:.1f}s)")
    if ndvi_tif:
        print(f"NDVI raster: {ndvi_tif.name}")
    else:
        print("[WARN] Sin mosaico NDVI; se usará indices_raster por recinto intersectado")

    print(f"Polígonos en CSV: {len(df):,}")
    bbox_pred = fast_bbox_from_predictions(df)
    print(
        "Cargando recintos para join espacial "
        f"(bbox {bbox_pred[0]:.3f},{bbox_pred[1]:.3f} → {bbox_pred[2]:.3f},{bbox_pred[3]:.3f})..."
    )
    recintos_gdf = cargar_recintos_en_bbox(bbox_pred)
    recintos_para_join = recintos_gdf[["id_propietario", "geom"]].copy().set_geometry("geom")

    indice = {}
    cache_ndvi: dict[int, float | None] = {}
    cache_area: dict[int, tuple[float, float]] = {}

    with rasterio.open(str(ndvi_tif)) if ndvi_tif else nullcontext() as ndvi_ds:
        for offset, col in enumerate(columnas_et):
            fecha_str = col.replace("ET_", "")
            tabla     = f"riego_prediccion_{offset}"
            filas     = []
            total_rows = len(df)
            t_dia = time.perf_counter()

            for n, (idx, row) in enumerate(df.iterrows(), start=1):
                if n == 1 or n % 5000 == 0 or n == total_rows:
                    print(f"  {tabla}: procesando {n:,}/{total_rows:,} polígonos...")

                try:
                    geom = wkt.loads(row["geometry_wkt"])
                    geom = geom.simplify(0.00005, preserve_topology=True)
                except Exception as e:
                    print(f"  Error geometría fila {idx}: {e}")
                    continue

                cultivo_nombre = str(row["Cl"]).strip()
                cultivo_info   = lookup_cultivo(kc_catalog, cultivo_nombre)

                # NDVI (cache por fila del CSV)
                if idx not in cache_ndvi:
                    ndvi_val = None
                    if ndvi_ds is not None:
                        try:
                            ndvi_val = ndvi_at_centroid(ndvi_ds, geom)
                            if ndvi_val is None:
                                ndvi_val = zonal_ndvi_mean(ndvi_ds, geom)
                        except Exception:
                            pass
                    if ndvi_val is None:
                        ndvi_val = ndvi_desde_recintos(geom, recintos_gdf, ndvi_recinto)
                    cache_ndvi[idx] = ndvi_val

                ndvi_used = cache_ndvi[idx]
                kc, ndvi_eff = calc_kc(
                    ndvi_used,
                    cultivo_info["formula_code"],
                    cultivo_info["kc_min"],
                    cultivo_info["kc_max"],
                )

                etp_valor = float(row[col])
                riego_val = round(etp_valor * kc, 3)   # ETc mm/día
                ev_ref    = float(row["Ev_t"])          # ET₀ actual (reservado)
                deficit   = riego_val                   # demanda = ETc directamente

                if idx not in cache_area:
                    try:
                        cache_area[idx] = area_superficie_desde_geom(geom)
                    except Exception:
                        cache_area[idx] = (0.0, 0.0)
                area_m2, sup_ha = cache_area[idx]
                litros_dia = litros_desde_deficit_y_area(deficit, area_m2)
                m3_ha = round(deficit * 10, 2)

                filas.append({
                    "cultivo":  cultivo_nombre,
                    "riego":    str(row["Rg"]),
                    "etp":      round(etp_valor, 3),
                    "kc":       round(kc, 3),
                    "ndvi":     round(ndvi_eff, 3) if ndvi_eff is not None else None,
                    "riego_mm": riego_val,
                    "deficit_mm": deficit,
                    "m3_ha":    m3_ha,
                    "superficie_ha": sup_ha,
                    "litros_dia": litros_dia,
                    "litros_txt": formato_volumen_mapa(deficit),
                    "color":    calcular_color_riego(etp_valor, ev_ref),
                    "fecha":    fecha_str,
                    "geometry": geom,
                })

            gdf = gpd.GeoDataFrame(filas, crs="EPSG:4326")

            gdf_centroids = gdf.copy().set_geometry("geometry")
            gdf_centroids["geometry"] = (
                gdf_centroids["geometry"]
                .to_crs("EPSG:25830")
                .centroid
                .to_crs("EPSG:4326")
            )

            joined = gpd.sjoin(
                gdf_centroids,
                recintos_para_join,
                how="left",
                predicate="within",
            )
            joined = joined[~joined.index.duplicated(keep="first")]
            gdf["id_propietario"] = joined["id_propietario"].values

            asignados = gdf["id_propietario"].notna().sum()
            print(
                f"  {tabla}: propietarios {asignados}/{len(gdf)}  ({fecha_str}) "
                f"en {time.perf_counter() - t_dia:.1f}s"
            )

            gdf.to_postgis(tabla, engine, if_exists="replace", index=False, chunksize=1000)

            with engine.connect() as conn:
                conn.execute(text(
                    f'CREATE INDEX IF NOT EXISTS {tabla}_geom_idx '
                    f'ON "{tabla}" USING GIST (geometry)'
                ))
                conn.commit()

            indice[str(offset)] = fecha_str

    with open(STATIC_DIR / "indice.json", "w", encoding="utf-8") as f:
        json.dump(indice, f)
    print(f"  → indice.json guardado en {STATIC_DIR}")

    return list(range(len(columnas_et)))


# ── GeoServer (reutiliza datastore postgis_etp) ─────────────────────────────

def datastore_postgis_existe() -> bool:
    url = f"{GEOSERVER_BASE_URL}/rest/workspaces/{WORKSPACE}/datastores/postgis_etp.json"
    return requests.get(url, auth=AUTH).status_code == 200


def capa_existe(nombre: str) -> bool:
    url = (
        f"{GEOSERVER_BASE_URL}/rest/workspaces/{WORKSPACE}/"
        f"datastores/postgis_etp/featuretypes/{nombre}.json"
    )
    return requests.get(url, auth=AUTH).status_code == 200


def crear_capa(nombre: str, offset: int):
    ft_body = json.dumps({
        "featureType": {
            "name":       nombre,
            "nativeName": nombre,
            "title":      f"Predicción riego día +{offset}",
            "enabled":    True,
            "srs":        "EPSG:4326",
            "defaultStyle": {"name": "riego_prediccion_estilo"},
        }
    })
    r = requests.post(
        f"{GEOSERVER_BASE_URL}/rest/workspaces/{WORKSPACE}/datastores/postgis_etp/featuretypes",
        auth=AUTH, headers=HEADERS_JSON, data=ft_body,
    )
    print(f"  [FT] {nombre}: {r.status_code}")


def recargar_capa(nombre: str):
    url  = (
        f"{GEOSERVER_BASE_URL}/rest/workspaces/{WORKSPACE}/"
        f"datastores/postgis_etp/featuretypes/{nombre}.json"
    )
    body = json.dumps({"featureType": {"enabled": True}})
    r    = requests.put(url, auth=AUTH, headers=HEADERS_JSON, data=body)
    print(f"  Recarga {nombre}: {r.status_code}")


def asignar_estilo(nombre: str):
    url  = f"{GEOSERVER_BASE_URL}/rest/layers/{WORKSPACE}:{nombre}.json"
    body = json.dumps({"layer": {"defaultStyle": {"name": "riego_prediccion_estilo"}}})
    r = requests.put(url, auth=AUTH, headers=HEADERS_JSON, data=body)
    print(f"  Estilo {nombre}: {r.status_code}")


def limpiar_cache(nombre: str):
    url = f"{GEOSERVER_BASE_URL}/gwc/rest/layers/{WORKSPACE}:{nombre}.json"
    r   = requests.delete(url, auth=AUTH)
    print(f"  Cache {nombre}: {r.status_code}")


def asegurar_estilo():
    nombre = "riego_prediccion_estilo"
    sld = """<?xml version="1.0" encoding="UTF-8"?><sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>riego_prediccion_estilo</sld:Name>
    <sld:UserStyle>
      <sld:Name>riego_prediccion_estilo</sld:Name>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:Name>Urgente hoy-manana</sld:Name>
          <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>color</ogc:PropertyName><ogc:Literal>red</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
          <sld:PolygonSymbolizer>
            <sld:Fill><sld:CssParameter name="fill">#d32f2f</sld:CssParameter><sld:CssParameter name="fill-opacity">0.42</sld:CssParameter></sld:Fill>
            <sld:Stroke><sld:CssParameter name="stroke">#b71c1c</sld:CssParameter><sld:CssParameter name="stroke-width">1.2</sld:CssParameter></sld:Stroke>
          </sld:PolygonSymbolizer>
        </sld:Rule>
        <sld:Rule>
          <sld:Name>Recomendado 2-3 dias</sld:Name>
          <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>color</ogc:PropertyName><ogc:Literal>orange</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
          <sld:PolygonSymbolizer>
            <sld:Fill><sld:CssParameter name="fill">#f57c00</sld:CssParameter><sld:CssParameter name="fill-opacity">0.38</sld:CssParameter></sld:Fill>
            <sld:Stroke><sld:CssParameter name="stroke">#e65100</sld:CssParameter><sld:CssParameter name="stroke-width">1</sld:CssParameter></sld:Stroke>
          </sld:PolygonSymbolizer>
        </sld:Rule>
        <sld:Rule>
          <sld:Name>Sin recomendacion</sld:Name>
          <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>color</ogc:PropertyName><ogc:Literal>blue</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
          <sld:PolygonSymbolizer>
            <sld:Fill><sld:CssParameter name="fill">#1976d2</sld:CssParameter><sld:CssParameter name="fill-opacity">0.35</sld:CssParameter></sld:Fill>
            <sld:Stroke><sld:CssParameter name="stroke">#1565c0</sld:CssParameter><sld:CssParameter name="stroke-width">0.8</sld:CssParameter></sld:Stroke>
          </sld:PolygonSymbolizer>
        </sld:Rule>
        <sld:Rule>
          <sld:Name>Volumen Label</sld:Name>
          <MinScaleDenominator>1</MinScaleDenominator>
          <MaxScaleDenominator>25000</MaxScaleDenominator>
          <ogc:Filter>
            <ogc:Or>
              <ogc:PropertyIsEqualTo><ogc:PropertyName>color</ogc:PropertyName><ogc:Literal>red</ogc:Literal></ogc:PropertyIsEqualTo>
              <ogc:PropertyIsEqualTo><ogc:PropertyName>color</ogc:PropertyName><ogc:Literal>orange</ogc:Literal></ogc:PropertyIsEqualTo>
            </ogc:Or>
          </ogc:Filter>
          <sld:TextSymbolizer>
            <sld:Label><ogc:PropertyName>litros_txt</ogc:PropertyName></sld:Label>
            <sld:Font>
              <sld:CssParameter name="font-family">Arial</sld:CssParameter>
              <sld:CssParameter name="font-size">10</sld:CssParameter>
              <sld:CssParameter name="font-weight">bold</sld:CssParameter>
            </sld:Font>
            <sld:LabelPlacement><sld:PointPlacement><sld:AnchorPoint><sld:AnchorPointX>0.5</sld:AnchorPointX><sld:AnchorPointY>0.5</sld:AnchorPointY></sld:AnchorPoint></sld:PointPlacement></sld:LabelPlacement>
            <sld:Halo><sld:Radius>2</sld:Radius><sld:Fill><sld:CssParameter name="fill">#000000</sld:CssParameter><sld:CssParameter name="fill-opacity">0.55</sld:CssParameter></sld:Fill></sld:Halo>
            <sld:Fill><sld:CssParameter name="fill">#ffffff</sld:CssParameter></sld:Fill>
          </sld:TextSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>"""

    existe = requests.get(
        f"{GEOSERVER_BASE_URL}/rest/styles/{nombre}.json", auth=AUTH
    ).status_code == 200
    if not existe:
        requests.post(
            f"{GEOSERVER_BASE_URL}/rest/styles",
            auth=AUTH,
            headers=HEADERS_JSON,
            data=json.dumps({"style": {"name": nombre, "filename": f"{nombre}.sld"}}),
        )
    r = requests.put(
        f"{GEOSERVER_BASE_URL}/rest/styles/{nombre}",
        auth=AUTH,
        headers={"Content-Type": "application/vnd.ogc.sld+xml"},
        data=sld.encode("utf-8"),
    )
    print(f"  SLD riego: {r.status_code}")


def main():
    print("=" * 50)
    print(f"Predicción RIEGO (ET₀×Kc) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    offsets = generar_tablas_postgis()

    print("\nComprobando estilo GeoServer...")
    asegurar_estilo()

    if not datastore_postgis_existe():
        print("[ERROR] Datastore postgis_etp no existe. Ejecuta mapasprediccion.py primero.")
        return

    print("\nPublicando capas riego en GeoServer...")
    for offset in offsets:
        nombre = f"riego_prediccion_{offset}"
        if capa_existe(nombre):
            recargar_capa(nombre)
        else:
            crear_capa(nombre, offset)
        asignar_estilo(nombre)
        limpiar_cache(nombre)

    print("\nFinalizado.")


if __name__ == "__main__":
    main()
