#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
from requests.auth import HTTPBasicAuth
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from webapp.config import Config
from scipy.spatial import cKDTree
from scipy.interpolate import Rbf, LinearNDInterpolator
import pyproj
import rasterio
from rasterio.transform import from_origin
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

try:
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel
    KRIGING_DISPONIBLE = True
except ImportError:
    KRIGING_DISPONIBLE = False
    print("⚠️  scikit-learn no instalado. El método KRIGING no estará disponible.")

# ============================================================
# PARÁMETROS DE CONFIGURACIÓN (CÁMBIALOS AQUÍ)
# ============================================================

# ── CAMBIO: motor SQLAlchemy en lugar de DB_CONFIG dict ─────────────────────
engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)
# ────────────────────────────────────────────────────────────────────────────

VARIABLE = "etpmon"
FECHA = "2026-03-22"
METODO = "IDW"
POTENCIA_IDW = 2.0
KRIGING_KERNEL = None
TIN_EXTRAPOLAR = False

USAR_RESOLUCION_EXACTA = True
RESOLUCION_X = 0.09897341412765957303
RESOLUCION_Y = 0.09963900334615380383

FORZAR_EXTENSION = True
X_MIN = -6.7330400360000002
X_MAX = -2.0812895720000002
Y_MIN = 40.3971466790000022
Y_MAX = 42.9877607660000010

MARGEN_GRADOS = 0.5
GUARDAR_DISTANCIAS = False
CARPETA_SALIDA = "C:\\ProgramData\\GeoServer\\data\\mapascontinuos"

REPROYECTAR = False
RESOLUCION_M = 5000
MARGEN_M = 20000
EPSG_UTM = 32630

# ============================================================
# GEOSERVER 
# ============================================================

GEOSERVER_URL  = "http://localhost:8080/geoserver"
GEOSERVER_USER = "admin"
GEOSERVER_PASS = "geoserver"   
WORKSPACE      = "gis_project"
STORE          = "mapascontinuos"

# ============================================================
# FIN DE LA CONFIGURACIÓN
# ============================================================

# ── CAMBIO: conectar_bd ahora devuelve una sesión SQLAlchemy ─────────────────
def conectar_bd():
    try:
        session = Session()
        session.execute(text("SELECT 1"))  # ping de comprobación
        print("✅ Conexión exitosa a la base de datos.")
        return session
    except Exception as e:
        print(f"❌ Error al conectar a la base de datos: {e}")
        return None
# ────────────────────────────────────────────────────────────────────────────

# ── CAMBIO: obtener_datos usa session.execute(text(...)) ─────────────────────
def obtener_datos(session, variable, fecha):
    query = text(f"""
        SELECT ST_X(e.geom) AS lon, ST_Y(e.geom) AS lat, d.{variable} AS valor
        FROM estaciones e
        JOIN datos_diarios d ON e.id = d.estacion_id
        WHERE d.fecha = :fecha AND d.{variable} IS NOT NULL;
    """)
    try:
        resultado = session.execute(query, {"fecha": fecha})
        filas = resultado.fetchall()
        if not filas:
            print(f"⚠️ No se encontraron datos para '{variable}' en {fecha}.")
            return None
        datos = np.array([(f[0], f[1], f[2]) for f in filas],
                         dtype=[('lon', float), ('lat', float), ('valor', float)])
        print(f"✅ {len(datos)} estaciones con datos válidos.")
        return datos
    except Exception as e:
        print(f"❌ Error en la consulta: {e}")
        return None
# ────────────────────────────────────────────────────────────────────────────

def reproyectar_a_utm(datos, epsg_origen=4326, epsg_destino=32630):
    transformer = pyproj.Transformer.from_crs(epsg_origen, epsg_destino, always_xy=True)
    x_utm, y_utm = transformer.transform(datos['lon'], datos['lat'])
    datos_utm = np.empty(len(datos), dtype=[('x', float), ('y', float), ('valor', float)])
    datos_utm['x'] = x_utm
    datos_utm['y'] = y_utm
    datos_utm['valor'] = datos['valor']
    return datos_utm

def crear_grid(datos, resolucion_x, resolucion_y, forzar_extension=False,
               x_min=None, x_max=None, y_min=None, y_max=None, margen=0.0):
    """
    Crea una malla de puntos centrados en las celdas.
    Si forzar_extension=True, usa los límites dados; si no, los calcula de los datos + margen.
    Devuelve X, Y (mallas de centros) y bounds (esquinas del raster ajustadas).
    """
    if forzar_extension and all(v is not None for v in [x_min, x_max, y_min, y_max]):
        min_x, max_x, min_y, max_y = x_min, x_max, y_min, y_max
    else:
        # Usar coordenadas de los datos (primeras dos columnas: x, y)
        xs = datos['x'] if 'x' in datos.dtype.names else datos['lon']
        ys = datos['y'] if 'y' in datos.dtype.names else datos['lat']
        min_x, max_x = np.min(xs) - margen, np.max(xs) + margen
        min_y, max_y = np.min(ys) - margen, np.max(ys) + margen

    # Calcular número de celdas (truncamiento)
    ncols = int((max_x - min_x) / resolucion_x)
    nrows = int((max_y - min_y) / resolucion_y)

    # Ajustar los límites para que coincidan exactamente con las celdas
    max_x = min_x + ncols * resolucion_x
    max_y = min_y + nrows * resolucion_y

    # Coordenadas de los centros (x creciente, y descendente para que fila0 = y_max)
    x_centers = np.linspace(min_x + resolucion_x/2, max_x - resolucion_x/2, ncols)
    y_centers = np.linspace(max_y - resolucion_y/2, min_y + resolucion_y/2, nrows)

    X, Y = np.meshgrid(x_centers, y_centers)
    bounds = (min_x, max_x, min_y, max_y)
    print(f"📐 Grid ajustado: {nrows} filas x {ncols} columnas.")
    print(f"   Extensión real: X[{min_x:.6f}, {max_x:.6f}], Y[{min_y:.6f}, {max_y:.6f}]")
    return X, Y, bounds

def idw_interpolacion(puntos_conocidos, valores_conocidos, X, Y, potencia=2, num_vecinos=None):
    puntos_grid = np.column_stack((X.ravel(), Y.ravel()))
    
    # Si num_vecinos es None, usar todos los puntos
    if num_vecinos is None:
        k = len(puntos_conocidos)
    else:
        k = min(num_vecinos, len(puntos_conocidos))
    
    tree = cKDTree(puntos_conocidos)
    distancias, indices = tree.query(puntos_grid, k=k)
    
    epsilon = 1e-12
    distancias = np.maximum(distancias, epsilon)
    pesos = 1.0 / (distancias ** potencia)
    
    valores_vecinos = valores_conocidos[indices]
    numerador = np.sum(pesos * valores_vecinos, axis=1)
    denominador = np.sum(pesos, axis=1)
    interpolado = numerador / denominador
    
    dist_min = np.min(distancias, axis=1)
    return interpolado.reshape(X.shape), dist_min.reshape(X.shape)

def rbf_interpolacion(puntos_conocidos, valores_conocidos, X, Y, funcion='multiquadric'):
    puntos_grid = np.column_stack((X.ravel(), Y.ravel()))
    rbf = Rbf(puntos_conocidos[:,0], puntos_conocidos[:,1], valores_conocidos, function=funcion)
    interpolado = rbf(X, Y).ravel()
    tree = cKDTree(puntos_conocidos)
    dist_min, _ = tree.query(puntos_grid, k=1)
    dist_min = np.where(np.isfinite(dist_min), dist_min, 1e6)
    return interpolado.reshape(X.shape), dist_min.reshape(X.shape)

def kriging_interpolacion(puntos_conocidos, valores_conocidos, X, Y, kernel=None):
    if not KRIGING_DISPONIBLE:
        raise ImportError("scikit-learn no está instalado.")
    puntos_grid = np.column_stack((X.ravel(), Y.ravel()))
    if kernel is None:
        kernel = ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(noise_level=1.0)
    gpr = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=5, random_state=42)
    gpr.fit(puntos_conocidos, valores_conocidos)
    interpolado, _ = gpr.predict(puntos_grid, return_std=True)
    tree = cKDTree(puntos_conocidos)
    dist_min, _ = tree.query(puntos_grid, k=1)
    dist_min = np.where(np.isfinite(dist_min), dist_min, 1e6)
    print(f"   Kernel utilizado: {gpr.kernel_}")
    return interpolado.reshape(X.shape), dist_min.reshape(X.shape)

def tin_interpolacion(puntos_conocidos, valores_conocidos, X, Y, extrapolar=False):
    puntos_grid = np.column_stack((X.ravel(), Y.ravel()))
    lin_interp = LinearNDInterpolator(puntos_conocidos, valores_conocidos, fill_value=np.nan)
    interpolado = lin_interp(puntos_grid)
    if extrapolar:
        nan_mask = np.isnan(interpolado)
        if np.any(nan_mask):
            tree = cKDTree(puntos_conocidos)
            dist, idx = tree.query(puntos_grid[nan_mask], k=1)
            interpolado[nan_mask] = valores_conocidos[idx]
    tree = cKDTree(puntos_conocidos)
    dist_min, _ = tree.query(puntos_grid, k=1)
    dist_min = np.where(np.isfinite(dist_min), dist_min, 1e6)
    return interpolado.reshape(X.shape), dist_min.reshape(X.shape)

def guardar_geotiff(matriz, bounds, resolucion_x, resolucion_y, crs_epsg=4326, filename="salida.tif"):
    min_x, max_x, min_y, max_y = bounds
    transform = from_origin(min_x, max_y, resolucion_x, resolucion_y)
    matriz = matriz[::-1, :]
    # Sin astype, sin nodata — igual que los que funcionan

    os.makedirs(os.path.dirname(filename) or '.', exist_ok=True)
    with rasterio.open(
        filename, 'w',
        driver='GTiff',
        height=matriz.shape[0],
        width=matriz.shape[1],
        count=1,
        dtype=matriz.dtype,   # float64 nativo
        crs=f'EPSG:{crs_epsg}',
        transform=transform,
        compress='lzw'
        # sin nodata
    ) as dst:
        dst.write(matriz, 1)
    print(f"💾 Guardado: {filename}")

def actualizar_imagemosaic():
    auth = HTTPBasicAuth(GEOSERVER_USER, GEOSERVER_PASS)

    # Borrar el shapefile de índice (GeoServer lo regenera solo con todos los .tif)
    extensiones_indice = [".shp", ".dbf", ".shx", ".qix", ".fix", ".prj"]
    nombre_indice = "mapascontinuos"

    for ext in extensiones_indice:
        ruta = os.path.join(CARPETA_SALIDA, nombre_indice + ext)
        if os.path.exists(ruta):
            try:
                os.remove(ruta)
                print(f"🗑️  Eliminado: {nombre_indice + ext}")
            except Exception as e:
                print(f"⚠️  No se pudo eliminar {ruta}: {e}")

    # Recargar GeoServer para que regenere el índice
    r = requests.post(f"{GEOSERVER_URL}/rest/reload", auth=auth)

    if r.status_code == 200:
        print("✅ GeoServer recargado, índice regenerado con todos los .tif")
    else:
        print(f"❌ HTTP {r.status_code}: {r.text[:200]}")

def main():
    print("\n🌍 Interpolador meteorológico\n")

    if METODO.upper() == "KRIGING" and not KRIGING_DISPONIBLE:
        print("❌ El método KRIGING requiere scikit-learn.")
        return None

    try:
        datetime.strptime(FECHA, "%Y-%m-%d")
    except ValueError:
        print("❌ La fecha debe tener formato YYYY-MM-DD")
        return None

    # ── CAMBIO: se usa sesión SQLAlchemy y se cierra con session.close() ─────
    session = conectar_bd()
    if not session:
        return None
    datos = obtener_datos(session, VARIABLE, FECHA)
    session.close()
    # ─────────────────────────────────────────────────────────────────────────
    if datos is None:
        return None

    if REPROYECTAR:
        datos_trabajo = reproyectar_a_utm(datos, epsg_destino=EPSG_UTM)
        coord_x, coord_y = datos_trabajo['x'], datos_trabajo['y']
        valores = datos_trabajo['valor']
        resol_x = resol_y = RESOLUCION_M
        usar_forzar = False
        margen_local = MARGEN_M
        crs_destino = EPSG_UTM
    else:
        datos_trabajo = datos
        coord_x, coord_y = datos_trabajo['lon'], datos_trabajo['lat']
        valores = datos_trabajo['valor']
        resol_x, resol_y = RESOLUCION_X, RESOLUCION_Y
        usar_forzar = FORZAR_EXTENSION
        margen_local = MARGEN_GRADOS
        crs_destino = 4326

    if usar_forzar:
        X, Y, bounds = crear_grid(datos_trabajo, resol_x, resol_y,
                                   forzar_extension=True,
                                   x_min=X_MIN, x_max=X_MAX,
                                   y_min=Y_MIN, y_max=Y_MAX)
    else:
        datos_temp = np.empty(len(coord_x), dtype=[('x', float), ('y', float)])
        datos_temp['x'] = coord_x
        datos_temp['y'] = coord_y
        X, Y, bounds = crear_grid(datos_temp, resol_x, resol_y,
                                   forzar_extension=False, margen=margen_local)

    puntos_conocidos = np.column_stack((coord_x, coord_y))

    print(f"🌀 Aplicando método {METODO}...")
    if METODO.upper() == 'IDW':
        Z, D = idw_interpolacion(puntos_conocidos, valores, X, Y, potencia=POTENCIA_IDW, num_vecinos=None)
    elif METODO.upper() == 'RBF':
        Z, D = rbf_interpolacion(puntos_conocidos, valores, X, Y)
    elif METODO.upper() == 'KRIGING':
        Z, D = kriging_interpolacion(puntos_conocidos, valores, X, Y, kernel=KRIGING_KERNEL)
    elif METODO.upper() == 'TIN':
        Z, D = tin_interpolacion(puntos_conocidos, valores, X, Y, extrapolar=TIN_EXTRAPOLAR)
    else:
        print("❌ Método no válido. Use IDW, RBF, KRIGING o TIN.")
        return None

    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    if REPROYECTAR:
        nombre_base = f"{VARIABLE}_{FECHA}_{METODO}_utm{RESOLUCION_M}m"
    else:
        nombre_base = f"{VARIABLE}_{FECHA}_{METODO}"

    # ── CAMBIO: el nombre del archivo debe contener la fecha para que el
    #    ImageMosaic la detecte via timeregex.properties (regex: [0-9]{4}-[0-9]{2}-[0-9]{2})
    archivo_salida = os.path.join(CARPETA_SALIDA, f"{nombre_base}.tif")
    guardar_geotiff(Z, bounds, resol_x, resol_y, crs_epsg=crs_destino, filename=archivo_salida)

    if GUARDAR_DISTANCIAS:
        archivo_dist = os.path.join(CARPETA_SALIDA, f"{nombre_base}_distancias.tif")
        guardar_geotiff(D, bounds, resol_x, resol_y, crs_epsg=crs_destino, filename=archivo_dist)

    print("\n✨ Proceso completado.")
    print(f"📁 Archivo: {os.path.abspath(archivo_salida)}")

    # ── CAMBIO: devolver la ruta para que el bloque principal pueda pasarla
    #    a actualizar_imagemosaic()
    return archivo_salida


if __name__ == "__main__":
    archivo = main()
    if archivo:
        actualizar_imagemosaic()