# -*- coding: utf-8-sig -*-
# EL BUENO SE SUPONE, AUNQUE SEA EL COPY

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from scipy.spatial import cKDTree
import rasterio
from rasterio.mask import mask as rasterio_mask
import pyproj
from shapely import wkt as shapely_wkt
from shapely.ops import transform as shapely_transform
from shapely.geometry import box as shapely_box
from webapp.config import Config

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from project_paths import DATOS_SALIDA_DIR, ndvi_mosaic_mas_reciente  # noqa: E402

engine  = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)

FECHA          = "2026-03-01"
DIAS_ATRAS_ETO = 12

VARIABLES_DIA  = ["tempmax", "tempmin", "tempmedia", "humedadmedia", "velviento", "precipitacion", "radiacion", "pepmon"]

ALIAS_COLUMNAS = {
    "pepmon":        "precipitacion_efectiva",
    "radiacion":     "radiacion(MJ/M^2)",
    "humedadmedia":      "humedad",
    "precipitacion": "precipitacion(mm)",
}

# IDW adaptativo — parámetros
MIN_VECINOS      = 4
MAX_VECINOS      = 6
RADIO_INICIAL_KM = 80
RADIO_MAX_KM     = 180
PASO_RADIO_KM    = 30

# Potencias específicas por variable
POTENCIAS_IDW = {
    "tempmax":        2.0,
    "tempmin":        2.0,
    "tempmedia":      2.0,
    "radiacion":      2.0,
    "humedadmedia":   2.5,
    "etpmon":         2.5,
    "velviento":      3.5,
    "precipitacion":  3.5,
    "pepmon":         3.5,
}

# Umbrales de alerta por variable
UMBRALES_ALERTA = {
    "tempmax":   2.0,
    "tempmin":   2.0,
    "tempmedia": 1.5,
    "humedadmedia": 10.0,
    "etpmon":    0.4,
}

ESTACIONES_EXCLUIR = set()

_ndvi_path = os.getenv("NDVI_MOSAIC_PATH", "").strip()
if _ndvi_path:
    RASTER_NDVI = _ndvi_path
else:
    _ndvi_auto = ndvi_mosaic_mas_reciente()
    RASTER_NDVI = str(_ndvi_auto) if _ndvi_auto else ""

CARPETA_SALIDA = str(DATOS_SALIDA_DIR)
NOMBRE_SALIDA  = f"datoscultivos222final_{FECHA}.csv"


# ------------------------------------------------------------
# FUNCIONES AUXILIARES
# ------------------------------------------------------------

def get_utm_proj(lon, lat):
    """Devuelve un Transformer de WGS84 a la zona UTM correspondiente."""
    zone = int((lon + 180) // 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)


def idw_adaptativo_metrico(puntos_conocidos_m, valores_conocidos, puntos_destino_m,
                           potencia=3.0, min_vecinos=4, max_vecinos=6,
                           radio_inicial_m=80000, radio_max_m=180000, paso_m=30000):
    """IDW con radio dinámico en sistema métrico (metros)."""
    tree      = cKDTree(puntos_conocidos_m)
    resultado = np.full(len(puntos_destino_m), np.nan)
    k_buscar  = min(max_vecinos, len(puntos_conocidos_m))
    sin_cob   = 0

    for i, punto in enumerate(puntos_destino_m):
        radio_m  = radio_inicial_m
        asignado = False
        while radio_m <= radio_max_m:
            dists, idxs = tree.query([punto], k=k_buscar)
            dists, idxs = dists[0], idxs[0]
            mascara = dists <= radio_m
            if mascara.sum() >= min_vecinos:
                d      = np.maximum(dists[mascara], 1e-12)
                v      = valores_conocidos[idxs[mascara]]
                pesos  = 1.0 / (d ** potencia)
                resultado[i] = np.sum(pesos * v) / np.sum(pesos)
                asignado = True
                break
            radio_m += paso_m
        if not asignado:
            sin_cob += 1

    if sin_cob:
        print(f"  ⚠️  {sin_cob:,} cultivos sin cobertura → NaN "
              f"(radio máx {radio_max_m/1000:.0f} km, mín {min_vecinos} vecinos).")
    return resultado


def conectar_bd():
    try:
        session = Session()
        session.execute(text("SELECT 1"))
        print("✅ Conexión exitosa a la base de datos.")
        return session
    except Exception as e:
        print(f"❌ Error al conectar: {e}")
        return None


def obtener_cultivos(session):
    query = text("""
        SELECT
            ST_AsText(c.geometry)         AS geometry_wkt,
            ST_X(ST_Centroid(c.geometry)) AS lon,
            ST_Y(ST_Centroid(c.geometry)) AS lat,
            p.descripcion                 AS cultivo,
            c.parc_sistexp
        FROM sigpac.cultivo_declarado c
        LEFT JOIN public.productos_fega p ON p.codigo = c.parc_producto
        WHERE c.geometry IS NOT NULL
          AND p.descripcion IS NOT NULL
          AND p.descripcion != '';
    """)
    resultado = session.execute(query)
    df = pd.DataFrame(resultado.fetchall(), columns=resultado.keys())
    print(f"✅ {len(df):,} cultivos cargados.")
    return df


def obtener_estaciones(session, variable, fecha):
    excluir_sql = ""
    params      = {"fecha": fecha}
    if ESTACIONES_EXCLUIR:
        placeholders = ", ".join(f":exc_{i}" for i in range(len(ESTACIONES_EXCLUIR)))
        excluir_sql  = f"AND e.codigo NOT IN ({placeholders})"
        for i, cod in enumerate(ESTACIONES_EXCLUIR):
            params[f"exc_{i}"] = cod

    query = text(f"""
        SELECT e.nombre, e.codigo,
               ST_X(e.geom) AS lon, ST_Y(e.geom) AS lat,
               d.{variable} AS valor
        FROM estaciones e
        JOIN datos_diarios d ON e.id = d.estacion_id
        WHERE d.fecha = :fecha AND d.{variable} IS NOT NULL
        {excluir_sql};
    """)
    resultado = session.execute(query, params)
    filas     = resultado.fetchall()
    if not filas:
        print(f"  ⚠️  Sin datos para '{variable}' en {fecha}.")
        return None

    datos = np.array(
        [(f[0], f[1], f[2], f[3], f[4]) for f in filas],
        dtype=[('nombre', 'U64'), ('codigo', 'U16'),
               ('lon', float), ('lat', float), ('valor', float)]
    )

    sufijo = f" (excluyendo {len(ESTACIONES_EXCLUIR)})" if ESTACIONES_EXCLUIR else ""
    print(f"  ✅ {variable} ({fecha}): {len(datos)} estaciones{sufijo}.")
    datos = np.sort(datos, order='codigo')
    return datos


def validar_interpolacion(df, col_nombre, datos, puntos_cultivos_lonlat):
    tree   = cKDTree(puntos_cultivos_lonlat)
    umbral = UMBRALES_ALERTA.get(col_nombre, 3.0)
    print(f"\n  📍 Validación {col_nombre} (umbral ⚠️ > {umbral}):")
    for i in range(len(datos)):
        lon, lat, valor_real = datos['lon'][i], datos['lat'][i], datos['valor'][i]
        dist, idx  = tree.query([[lon, lat]], k=1)
        valor_csv  = df[col_nombre].iloc[idx[0]]
        diff       = abs(valor_real - valor_csv)
        dist_km    = dist[0] * 111
        alerta     = "  ⚠️ " if diff > umbral else ""
        print(f"     {datos['nombre'][i]:25s} ({datos['codigo'][i]:6s}): "
              f"real={valor_real:.3f} | interpolado={valor_csv:.3f} | "
              f"diff={diff:.3f} | dist={dist_km:.1f}km{alerta}")


def muestrear_ndvi_zonal(df, ruta_raster):
    print(f"🛰️  Leyendo NDVI (estadística zonal): {ruta_raster}")
    with rasterio.open(ruta_raster) as src:
        raster_crs = src.crs
        nodata_val = src.nodata
        bounds     = src.bounds
        raster_box = shapely_box(bounds.left, bounds.bottom, bounds.right, bounds.top)

        print(f"  CRS del raster : {raster_crs}")
        print(f"  NoData value   : {nodata_val}")
        print(f"  Procesando {len(df):,} recintos...")

        transformer = pyproj.Transformer.from_crs(
            "EPSG:4326", raster_crs, always_xy=True
        )

        def reproyectar(geom):
            return shapely_transform(
                lambda x, y: transformer.transform(x, y),
                geom
            )

        ndvi_vals   = np.full(len(df), np.nan)
        n_validos   = 0
        n_pequenos  = 0
        n_vacios    = 0
        n_fuera     = 0
        n_error_wkt = 0

        for i, wkt_str in enumerate(df["geometry_wkt"]):
            try:
                geom_wgs84 = shapely_wkt.loads(wkt_str)
            except Exception:
                n_error_wkt += 1
                continue

            try:
                geom_proj = reproyectar(geom_wgs84)
            except Exception:
                n_fuera += 1
                continue

            if not geom_proj.intersects(raster_box):
                n_fuera += 1
                continue

            def extraer_pixeles(all_touched):
                pixeles, _ = rasterio_mask(
                    src,
                    [geom_proj],
                    crop=True,
                    nodata=nodata_val if nodata_val is not None else np.nan,
                    all_touched=all_touched,
                )
                arr = pixeles[0].astype(float)
                if nodata_val is not None:
                    arr[arr == nodata_val] = np.nan
                return arr[~np.isnan(arr)]

            try:
                validos = extraer_pixeles(all_touched=False)
                if len(validos) == 0:
                    validos = extraer_pixeles(all_touched=True)
                    if len(validos) > 0:
                        n_pequenos += 1
                if len(validos) == 0:
                    n_vacios += 1
                else:
                    ndvi_vals[i] = validos.mean()
                    n_validos   += 1
            except Exception:
                n_fuera += 1

        print(f"  ✅ Con píxeles válidos      : {n_validos:,}")
        print(f"  🔹 Recintos muy pequeños   : {n_pequenos:,}  (resueltos con all_touched)")
        print(f"  ⬜ Sin píxeles válidos      : {n_vacios:,}  (nubes / nodata completo)")
        print(f"  🔲 Fuera del raster        : {n_fuera:,}")
        if n_error_wkt:
            print(f"  ❌ Error WKT               : {n_error_wkt:,}")

    return ndvi_vals


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():
    print(f"\n🌱 Interpolación sobre cultivos — {FECHA}")
    print(f"   IDW adaptativo : radio {RADIO_INICIAL_KM}→{RADIO_MAX_KM} km "
          f"(paso {PASO_RADIO_KM} km) | "
          f"vecinos {MIN_VECINOS}–{MAX_VECINOS}")
    print(f"   Potencias IDW específicas por variable:")
    for var in sorted(POTENCIAS_IDW.keys()):
        print(f"      • {var:15s} → {POTENCIAS_IDW[var]}")
    if ESTACIONES_EXCLUIR:
        print(f"   Estaciones excluidas del IDW: {', '.join(ESTACIONES_EXCLUIR)}")
    print()

    fecha_dt = datetime.strptime(FECHA, "%Y-%m-%d")

    # Conexión a BD
    session = conectar_bd()
    if not session:
        return

    # Cargar cultivos (solo los que tienen cultivo asignado)
    df = obtener_cultivos(session)

    # Reproyectar todos los cultivos a UTM una sola vez
    lon_med         = df['lon'].median()
    lat_med         = df['lat'].median()
    transformer_utm = get_utm_proj(lon_med, lat_med)

    x_cult, y_cult         = transformer_utm.transform(df['lon'].values, df['lat'].values)
    puntos_cultivos_utm    = np.column_stack((x_cult, y_cult))
    puntos_cultivos_lonlat = df[["lon", "lat"]].values

    # ── Interpolación de ETo (días hacia atrás) ───────────────────────────
    print(f"\n📡 Interpolando ETo ({DIAS_ATRAS_ETO + 1} días)...")
    potencia_eto = POTENCIAS_IDW.get("etpmon", 2.5)

    for dias in range(DIAS_ATRAS_ETO + 1):
        fecha_iter = (fecha_dt - timedelta(days=dias)).strftime("%Y-%m-%d")
        col_nombre = "eto_0" if dias == 0 else f"eto_-{dias}"

        datos = obtener_estaciones(session, "etpmon", fecha_iter)
        if datos is None:
            df[col_nombre] = np.nan
            continue

        # Filtrar estaciones con ETo = 0 (error de sensor)
        mask        = datos['valor'] > 0
        n_filtrados = (~mask).sum()
        if n_filtrados:
            nombres = [str(datos['nombre'][i]) for i in range(len(datos)) if not mask[i]]
            print(f"  🚫 [etpmon] {n_filtrados} estación(es) con valor=0 descartadas "
                  f"en {fecha_iter}: {nombres}")
        datos = datos[mask]

        if len(datos) == 0:
            print(f"  ⚠️  Sin datos válidos de ETo en {fecha_iter} → NaN")
            df[col_nombre] = np.nan
            continue

        x_est, y_est   = transformer_utm.transform(datos['lon'], datos['lat'])
        puntos_est_utm = np.column_stack((x_est, y_est))

        df[col_nombre] = idw_adaptativo_metrico(
            puntos_est_utm, datos['valor'], puntos_cultivos_utm,
            potencia=potencia_eto,
            min_vecinos=MIN_VECINOS, max_vecinos=MAX_VECINOS,
            radio_inicial_m=RADIO_INICIAL_KM * 1000,
            radio_max_m=RADIO_MAX_KM * 1000,
            paso_m=PASO_RADIO_KM * 1000,
        )

        validar_interpolacion(df, col_nombre, datos, puntos_cultivos_lonlat)

    # ── Interpolación del resto de variables del día FECHA ────────────────
    print(f"\n📡 Interpolando variables del día {FECHA}...")
    for variable in VARIABLES_DIA:
        datos = obtener_estaciones(session, variable, FECHA)
        if datos is None:
            df[variable] = np.nan
            continue

        potencia_var   = POTENCIAS_IDW.get(variable, 3.0)
        x_est, y_est   = transformer_utm.transform(datos['lon'], datos['lat'])
        puntos_est_utm = np.column_stack((x_est, y_est))

        df[variable] = idw_adaptativo_metrico(
            puntos_est_utm, datos['valor'], puntos_cultivos_utm,
            potencia=potencia_var,
            min_vecinos=MIN_VECINOS, max_vecinos=MAX_VECINOS,
            radio_inicial_m=RADIO_INICIAL_KM * 1000,
            radio_max_m=RADIO_MAX_KM * 1000,
            paso_m=PASO_RADIO_KM * 1000,
        )

        validar_interpolacion(df, variable, datos, puntos_cultivos_lonlat)

    session.close()
    print()

    # ── NDVI ──────────────────────────────────────────────────────────────
    df["ndvi"]            = muestrear_ndvi_zonal(df, RASTER_NDVI)
    df["ndvi_24-02-2026"] = muestrear_ndvi_zonal(df, RASTER_NDVI.replace("20260301", "20260224"))
    df["ndvi_19-02-2026"] = muestrear_ndvi_zonal(df, RASTER_NDVI.replace("20260301", "20260219"))

    # ── Limpieza final y guardado ─────────────────────────────────────────
    df   = df.drop(columns=["lon", "lat"])
    cols = [c for c in df.columns if c != "geometry_wkt"] + ["geometry_wkt"]
    df   = df[cols]
    df = df.sort_values(["cultivo", "parc_sistexp", "geometry_wkt"],na_position="last").reset_index(drop=True)
    df.insert(0, "id", df.index + 1)

    df = df.rename(columns=ALIAS_COLUMNAS)

    cols_numericas     = df.select_dtypes(include=[np.number]).columns.difference(["id"])
    df[cols_numericas] = df[cols_numericas].round(3)

    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    ruta_csv = os.path.join(CARPETA_SALIDA, NOMBRE_SALIDA)
    df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")

    print(f"\n💾 CSV guardado: {ruta_csv}  "
          f"({os.path.getsize(ruta_csv) / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()