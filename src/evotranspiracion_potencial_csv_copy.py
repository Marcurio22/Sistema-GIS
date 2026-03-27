import os
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

# ============================================================
# CONFIGURACIÓN
# ============================================================

engine  = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)

FECHA          = "2026-03-01"
DIAS_ATRAS_ETO = 12

VARIABLES_DIA  = ["tempmax", "tempmin", "tempmedia", "humedadd"]

# IDW adaptativo — parámetros
POTENCIA         = 3.0
MIN_VECINOS      = 4
MAX_VECINOS      = 6
RADIO_INICIAL_KM = 80
RADIO_MAX_KM     = 180
PASO_RADIO_KM    = 30

# Umbrales de alerta por variable (diff máximo antes de mostrar ⚠️)
UMBRALES_ALERTA = {
    "tempmax":   2.0,
    "tempmin":   2.0,
    "tempmedia": 1.5,
    "humedadd": 10.0,
    "etpmon":    0.4,
}

# Estaciones a excluir del IDW por datos anómalos recurrentes.
# Se siguen mostrando en la validación pero no se usan como fuente.
# Ejemplo: ESTACIONES_EXCLUIR = {"ZA02", "SG01"}
ESTACIONES_EXCLUIR = set()

RASTER_NDVI    = r"C:\Users\Instalador\Documents\Sistema-GIS-main\data\processed\ndvi_composite\\ndvi_pc_20260301_mosaic_utm.tif"

CARPETA_SALIDA = r"C:\datos\salida"
NOMBRE_SALIDA  = f"cultivospacheco2_{FECHA}.csv"

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
    """
    Carga los cultivos con su geometría completa en WKT (para NDVI zonal)
    y el centroide lon/lat (para la interpolación meteorológica).
    """
    query = text("""
        SELECT
            ST_AsText(c.geometry)         AS geometry_wkt,
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
    """
    Carga estaciones con datos para una variable y fecha,
    excluyendo las marcadas en ESTACIONES_EXCLUIR.
    """
    excluir_sql = ""
    params = {"fecha": fecha}
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
    filas = resultado.fetchall()
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
    return datos

# ============================================================
# IDW ADAPTATIVO CON RADIO DINÁMICO
# ============================================================

def idw_adaptativo(puntos_conocidos, valores_conocidos, puntos_destino,
                   potencia=3.0, min_vecinos=4, max_vecinos=6,
                   radio_inicial_km=80, radio_max_km=180, paso_km=30):
    """
    IDW con radio dinámico.
    Parte de radio_inicial_km y amplía en paso_km hasta radio_max_km
    si no encuentra min_vecinos estaciones. Usa como máximo max_vecinos.
    """
    tree      = cKDTree(puntos_conocidos)
    resultado = np.full(len(puntos_destino), np.nan)
    k_buscar  = min(max_vecinos, len(puntos_conocidos))
    sin_cob   = 0

    for i, punto in enumerate(puntos_destino):
        radio_km = radio_inicial_km
        asignado = False

        while radio_km <= radio_max_km:
            radio_grados = radio_km / 111.0
            dists, idxs  = tree.query([punto], k=k_buscar)
            dists, idxs  = dists[0], idxs[0]

            mascara  = dists <= radio_grados
            if mascara.sum() >= min_vecinos:
                d = np.maximum(dists[mascara], 1e-12)
                v = valores_conocidos[idxs[mascara]]
                pesos = 1.0 / (d ** potencia)
                resultado[i] = np.sum(pesos * v) / np.sum(pesos)
                asignado = True
                break
            radio_km += paso_km

        if not asignado:
            sin_cob += 1

    if sin_cob:
        print(f"  ⚠️  {sin_cob:,} cultivos sin cobertura → NaN "
              f"(radio máx {radio_max_km} km, mín {min_vecinos} vecinos).")
    return resultado

# ============================================================
# VALIDACIÓN
# ============================================================

def validar_interpolacion(df, col_nombre, datos, puntos_cultivos):
    """
    Para cada estación busca el cultivo más cercano y compara
    el valor real con el interpolado. Usa umbrales por variable.
    """
    tree   = cKDTree(puntos_cultivos)
    umbral = UMBRALES_ALERTA.get(col_nombre, 3.0)
    print(f"\n  📍 Validación {col_nombre} (umbral ⚠️ > {umbral}):")
    for i in range(len(datos)):
        lon, lat, valor_real = datos['lon'][i], datos['lat'][i], datos['valor'][i]
        dist, idx = tree.query([[lon, lat]], k=1)
        valor_csv = df[col_nombre].iloc[idx[0]]
        diff      = abs(valor_real - valor_csv)
        dist_km   = dist[0] * 111
        alerta    = "  ⚠️ " if diff > umbral else ""
        print(f"     {datos['nombre'][i]:25s} ({datos['codigo'][i]:6s}): "
              f"real={valor_real:.3f} | interpolado={valor_csv:.3f} | "
              f"diff={diff:.3f} | dist={dist_km:.1f}km{alerta}")

# ============================================================
# NDVI ZONAL — media de TODOS los píxeles dentro del recinto
# ============================================================

def muestrear_ndvi_zonal(df, ruta_raster):
    """
    Calcula el NDVI medio de cada recinto usando estadística zonal:
    - Reproyecta la geometría completa de cada recinto al CRS del raster.
    - Enmascara el raster con esa geometría (rasterio.mask).
    - Promedia todos los píxeles válidos que caen dentro.

    Si el recinto es muy pequeño (ningún centro de píxel cae dentro)
    se reintenta con all_touched=True antes de asignar NaN.
    """
    print(f"🛰️  Leyendo NDVI (estadística zonal): {ruta_raster}")

    with rasterio.open(ruta_raster) as src:
        raster_crs = src.crs
        nodata_val = src.nodata
        bounds     = src.bounds
        raster_box = shapely_box(bounds.left, bounds.bottom, bounds.right, bounds.top)

        print(f"  CRS del raster : {raster_crs}")
        print(f"  NoData value   : {nodata_val}")
        print(f"  Procesando {len(df):,} recintos...")

        # Transformador WGS84 → CRS del raster (hecho UNA SOLA VEZ)
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
        n_pequenos  = 0   # recintos donde solo all_touched funcionó
        n_vacios    = 0   # recintos dentro del raster pero sin píxel válido
        n_fuera     = 0
        n_error_wkt = 0

        for i, wkt_str in enumerate(df["geometry_wkt"]):

            # 1. Parsear WKT
            try:
                geom_wgs84 = shapely_wkt.loads(wkt_str)
            except Exception:
                n_error_wkt += 1
                continue

            # 2. Reproyectar
            try:
                geom_proj = reproyectar(geom_wgs84)
            except Exception:
                n_fuera += 1
                continue

            # 3. Comprobar intersección con el raster
            if not geom_proj.intersects(raster_box):
                n_fuera += 1
                continue

            # 4. Estadística zonal
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

                # Recinto muy pequeño: ningún centro de píxel cae dentro
                # → reintentamos tocando todos los píxeles que intersectan
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
        print(f"  🔹 Recintos muy pequeños   : {n_pequenos:,}  "
              f"(resueltos con all_touched)")
        print(f"  ⬜ Sin píxeles válidos      : {n_vacios:,}  "
              f"(nubes / nodata completo)")
        print(f"  🔲 Fuera del raster        : {n_fuera:,}")
        if n_error_wkt:
            print(f"  ❌ Error WKT               : {n_error_wkt:,}")

    return ndvi_vals

# ============================================================
# MAIN
# ============================================================

def main():
    print(f"\n🌱 Interpolación sobre cultivos — {FECHA}")
    print(f"   IDW adaptativo : radio {RADIO_INICIAL_KM}→{RADIO_MAX_KM} km "
          f"(paso {PASO_RADIO_KM} km) | "
          f"vecinos {MIN_VECINOS}–{MAX_VECINOS} | potencia {POTENCIA}")
    if ESTACIONES_EXCLUIR:
        print(f"   Estaciones excluidas del IDW: {', '.join(ESTACIONES_EXCLUIR)}")
    print()

    fecha_dt = datetime.strptime(FECHA, "%Y-%m-%d")

    session = conectar_bd()
    if not session:
        return

    df = obtener_cultivos(session)
    puntos_cultivos = df[["lon", "lat"]].values

    # ---- ETo ----
    print(f"\n📡 Interpolando ETo ({DIAS_ATRAS_ETO + 1} días)...")
    for dias in range(DIAS_ATRAS_ETO + 1):
        fecha_iter = (fecha_dt - timedelta(days=dias)).strftime("%Y-%m-%d")
        col_nombre = "eto_0" if dias == 0 else f"eto_-{dias}"

        datos = obtener_estaciones(session, "etpmon", fecha_iter)
        if datos is None:
            df[col_nombre] = np.nan
            continue

        puntos_est     = np.column_stack((datos['lon'], datos['lat']))
        df[col_nombre] = idw_adaptativo(
            puntos_est, datos['valor'], puntos_cultivos,
            potencia=POTENCIA, min_vecinos=MIN_VECINOS, max_vecinos=MAX_VECINOS,
            radio_inicial_km=RADIO_INICIAL_KM, radio_max_km=RADIO_MAX_KM,
            paso_km=PASO_RADIO_KM,
        )
        validar_interpolacion(df, col_nombre, datos, puntos_cultivos)

    # ---- Variables meteorológicas ----
    print(f"\n📡 Interpolando variables del día {FECHA}...")
    for variable in VARIABLES_DIA:
        datos = obtener_estaciones(session, variable, FECHA)
        if datos is None:
            df[variable] = np.nan
            continue

        puntos_est   = np.column_stack((datos['lon'], datos['lat']))
        df[variable] = idw_adaptativo(
            puntos_est, datos['valor'], puntos_cultivos,
            potencia=POTENCIA, min_vecinos=MIN_VECINOS, max_vecinos=MAX_VECINOS,
            radio_inicial_km=RADIO_INICIAL_KM, radio_max_km=RADIO_MAX_KM,
            paso_km=PASO_RADIO_KM,
        )
        validar_interpolacion(df, variable, datos, puntos_cultivos)

    session.close()

    # ---- NDVI zonal ----
    print()
    df["ndvi"] = muestrear_ndvi_zonal(df, RASTER_NDVI)

    # ---- Guardar CSV (geometry_wkt como última columna) ----
    df = df.drop(columns=["lon", "lat"])
    cols = [c for c in df.columns if c != "geometry_wkt"] + ["geometry_wkt"]
    df = df[cols]
    df = df.sort_values(["cultivo", "parc_sistexp"], na_position="last").reset_index(drop=True)
    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    ruta_csv = os.path.join(CARPETA_SALIDA, NOMBRE_SALIDA)
    df.to_csv(ruta_csv, index=False)

    print(f"\n💾 CSV guardado: {ruta_csv}  "
          f"({os.path.getsize(ruta_csv) / 1024 / 1024:.1f} MB)")

    # ---- Resumen estadístico ----
    print("\n📊 Resumen:")
    cols_resumen = (
        ["eto_0"] + [f"eto_-{d}" for d in range(1, DIAS_ATRAS_ETO + 1)]
        + VARIABLES_DIA + ["ndvi"]
    )
    for col in cols_resumen:
        serie = df[col].dropna()
        if len(serie):
            print(f"   {col:14s} — min: {serie.min():.3f}  max: {serie.max():.3f}  "
                  f"media: {serie.mean():.3f}  NaN: {df[col].isna().sum():,}")
    print("\n✨ Hecho.")


if __name__ == "__main__":
    main()