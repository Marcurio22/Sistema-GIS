

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from scipy.spatial import cKDTree
import rasterio
from rasterio.transform import rowcol
import pyproj
from webapp.config import Config

# ============================================================
# CONFIGURACIÓN
# ============================================================

engine  = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)

FECHA          = "2026-03-01"   # día principal (eto_0)
DIAS_ATRAS_ETO = 12             # cuántos días anteriores de ETo incluir

VARIABLES_DIA  = ["tempmax", "tempmin", "tempmedia", "humedadd"]

POTENCIA_IDW   = 3.0
NUM_VECINOS    = 8          


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from scipy.spatial import cKDTree
import rasterio
from rasterio.transform import rowcol
import pyproj
from webapp.config import Config

# ============================================================
# CONFIGURACIÓN
# ============================================================

engine  = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)

FECHA          = "2026-03-01"
DIAS_ATRAS_ETO = 12

VARIABLES_DIA  = ["tempmax", "tempmin", "tempmedia", "humedadd"]

POTENCIA_IDW   = 3.0
NUM_VECINOS    = 8

# Distancia máxima para incluir una estación en el IDW.
# Estaciones más lejanas se ignoran — si un cultivo no tiene ninguna
# estación dentro del radio, su valor saldrá NaN.
# Ajusta según la densidad de tu red: con 3 estaciones en el bbox
# y las más cercanas a ~50-80km, un radio de 100km es razonable.
MAX_DIST_KM  = 100
MAX_DIST_GRA = MAX_DIST_KM / 111.0   # conversión aproximada a grados

RASTER_NDVI    = r"C:\Users\Instalador\Documents\Sistema-GIS-main\data\processed\ndvi_composite\\ndvi_pc_20260301_mosaic_utm.tif"

CARPETA_SALIDA = r"C:\datos\salida"
NOMBRE_SALIDA  = f"cultivosn_{FECHA}.csv"

# ============================================================
# CONEXIÓN
# ============================================================

def conectar_bd():
    try:
        session = Session()
        session.execute(text("SELECT 1"))
        print("✅ Conexión exitosa a la base de datos.")
        return session
    except Exception as e:
        print(f"❌ Error al conectar: {e}")
        return None

# ============================================================
# CARGA DE DATOS
# ============================================================

def obtener_cultivos(session):
    query = text("""
        SELECT
            ST_AsText(c.geometry)         AS geometry,
            ST_X(ST_Centroid(c.geometry)) AS lon,
            ST_Y(ST_Centroid(c.geometry)) AS lat,
            p.descripcion                 AS cultivo,
            c.parc_sistexp
        FROM sigpac.cultivo_declarado c
        LEFT JOIN public.productos_fega p ON p.codigo = c.parc_producto
        WHERE c.geometry IS NOT NULL;
    """)
    resultado = session.execute(query)
    df = pd.DataFrame(resultado.fetchall(), columns=resultado.keys())
    print(f"✅ {len(df):,} cultivos cargados.")
    return df

def obtener_estaciones(session, variable, fecha):
    query = text(f"""
        SELECT e.nombre, e.codigo,
               ST_X(e.geom) AS lon, ST_Y(e.geom) AS lat,
               d.{variable} AS valor
        FROM estaciones e
        JOIN datos_diarios d ON e.id = d.estacion_id
        WHERE d.fecha = :fecha AND d.{variable} IS NOT NULL;
    """)
    resultado = session.execute(query, {"fecha": fecha})
    filas = resultado.fetchall()
    if not filas:
        print(f"  ⚠️  Sin datos para '{variable}' en {fecha}.")
        return None
    datos = np.array(
        [(f[0], f[1], f[2], f[3], f[4]) for f in filas],
        dtype=[('nombre', 'U64'), ('codigo', 'U16'),
               ('lon', float), ('lat', float), ('valor', float)]
    )
    print(f"  ✅ {variable} ({fecha}): {len(datos)} estaciones.")
    return datos

# ============================================================
# IDW CON RADIO MÁXIMO
# ============================================================

def idw_en_puntos(puntos_conocidos, valores_conocidos, puntos_destino,
                  potencia=2.0, num_vecinos=None, max_dist=None):
    """
    IDW con radio máximo opcional.
    - num_vecinos: cuántos vecinos más cercanos considerar como candidatos
    - max_dist: distancia máxima en las mismas unidades que las coordenadas
                (grados si trabajas en 4326). Estaciones más lejanas se descartan.
    Si un cultivo no tiene ninguna estación dentro del radio → NaN.
    """
    k = len(puntos_conocidos) if num_vecinos is None else min(num_vecinos, len(puntos_conocidos))
    tree = cKDTree(puntos_conocidos)
    distancias, indices = tree.query(puntos_destino, k=k)

    if k == 1:
        distancias = distancias[:, np.newaxis]
        indices    = indices[:, np.newaxis]

    # Descarta estaciones fuera del radio (peso = 0)
    if max_dist is not None:
        fuera = distancias > max_dist
        distancias = np.where(fuera, np.inf, distancias)

    distancias = np.maximum(distancias, 1e-12)
    pesos = np.where(np.isfinite(distancias), 1.0 / (distancias ** potencia), 0.0)

    suma_pesos = np.sum(pesos, axis=1)
    interpolado = np.where(
        suma_pesos > 0,
        np.sum(pesos * valores_conocidos[indices], axis=1) / suma_pesos,
        np.nan
    )
    return interpolado

# ============================================================
# VALIDACIÓN
# ============================================================

def validar_interpolacion(df, col_nombre, datos, puntos_cultivos):
    tree = cKDTree(puntos_cultivos)
    print(f"\n  📍 Validación {col_nombre}:")
    for i in range(len(datos)):
        lon, lat, valor_real = datos['lon'][i], datos['lat'][i], datos['valor'][i]
        dist, idx = tree.query([[lon, lat]], k=1)
        valor_csv = df[col_nombre].iloc[idx[0]]
        print(f"     {datos['nombre'][i]:25s} ({datos['codigo'][i]:6s}): "
              f"real={valor_real:.3f} | interpolado={valor_csv:.3f} | "
              f"diff={abs(valor_real - valor_csv):.3f} | dist={dist[0]*111:.1f}km")

# ============================================================
# NDVI desde TIF
# ============================================================

def muestrear_ndvi(df, ruta_raster):
    print(f"🛰️  Leyendo NDVI: {ruta_raster}")
    with rasterio.open(ruta_raster) as src:
        raster_crs = src.crs
        data   = src.read(1)
        nodata = src.nodata
        nrows, ncols = data.shape

        print(f"  CRS del raster: {raster_crs}")
        transformer = pyproj.Transformer.from_crs("EPSG:4326", raster_crs, always_xy=True)
        x_proj, y_proj = transformer.transform(df["lon"].values, df["lat"].values)

        filas, cols = rowcol(src.transform, x_proj, y_proj)
        filas = np.asarray(filas)
        cols  = np.asarray(cols)

        dentro = (filas >= 0) & (filas < nrows) & (cols >= 0) & (cols < ncols)
        ndvi_vals = np.full(len(df), np.nan)
        ndvi_vals[dentro] = data[filas[dentro], cols[dentro]]

        if nodata is not None:
            ndvi_vals[ndvi_vals == nodata] = np.nan

    n_fuera = (~dentro).sum()
    n_vacio = np.isnan(ndvi_vals).sum() - n_fuera
    print(f"  ✅ Dentro: {dentro.sum():,} | Fuera: {n_fuera:,} | "
          f"Sin valor (nubes/vacío): {n_vacio:,}")
    return ndvi_vals

# ============================================================
# MAIN
# ============================================================

def main():
    print(f"\n🌱 Interpolación sobre cultivos — {FECHA}")
    print(f"   Radio máximo IDW: {MAX_DIST_KM} km | "
          f"Vecinos: {NUM_VECINOS} | Potencia: {POTENCIA_IDW}\n")

    fecha_dt = datetime.strptime(FECHA, "%Y-%m-%d")

    session = conectar_bd()
    if not session:
        return

    df = obtener_cultivos(session)
    puntos_cultivos = df[["lon", "lat"]].values

    # ETo: eto_0, eto_-1, ..., eto_-12
    print(f"\n📡 Interpolando ETo ({DIAS_ATRAS_ETO + 1} días)...")
    for dias in range(DIAS_ATRAS_ETO + 1):
        fecha_iter = (fecha_dt - timedelta(days=dias)).strftime("%Y-%m-%d")
        col_nombre = "eto_0" if dias == 0 else f"eto_-{dias}"

        datos = obtener_estaciones(session, "etpmon", fecha_iter)
        if datos is None:
            df[col_nombre] = np.nan
            continue

        puntos_est     = np.column_stack((datos['lon'], datos['lat']))
        df[col_nombre] = idw_en_puntos(
            puntos_est, datos['valor'], puntos_cultivos,
            potencia=POTENCIA_IDW, num_vecinos=NUM_VECINOS, max_dist=MAX_DIST_GRA
        )
        validar_interpolacion(df, col_nombre, datos, puntos_cultivos)

    # Resto de variables del día principal
    print(f"\n📡 Interpolando variables del día {FECHA}...")
    for variable in VARIABLES_DIA:
        datos = obtener_estaciones(session, variable, FECHA)
        if datos is None:
            df[variable] = np.nan
            continue

        puntos_est   = np.column_stack((datos['lon'], datos['lat']))
        df[variable] = idw_en_puntos(
            puntos_est, datos['valor'], puntos_cultivos,
            potencia=POTENCIA_IDW, num_vecinos=NUM_VECINOS, max_dist=MAX_DIST_GRA
        )
        validar_interpolacion(df, variable, datos, puntos_cultivos)

    session.close()

    # NDVI
    print()
    df["ndvi"] = muestrear_ndvi(df, RASTER_NDVI)

    # Guardar
    df = df.drop(columns=["lon", "lat"])
    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    ruta_csv = os.path.join(CARPETA_SALIDA, NOMBRE_SALIDA)
    df.to_csv(ruta_csv, index=False)

    print(f"\n💾 CSV guardado: {ruta_csv}  ({os.path.getsize(ruta_csv)/1024/1024:.1f} MB)")
    print("\n📊 Resumen:")
    cols_resumen = (["eto_0"] + [f"eto_-{d}" for d in range(1, DIAS_ATRAS_ETO + 1)]
                    + VARIABLES_DIA + ["ndvi"])
    for col in cols_resumen:
        serie = df[col].dropna()
        if len(serie):
            print(f"   {col:14s} — min: {serie.min():.3f}  max: {serie.max():.3f}  "
                  f"media: {serie.mean():.3f}  NaN: {df[col].isna().sum():,}")
    print("\n✨ Hecho.")

if __name__ == "__main__":
    main()