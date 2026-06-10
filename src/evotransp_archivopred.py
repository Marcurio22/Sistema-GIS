# -*- coding: utf-8-sig -*-

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from scipy.spatial import cKDTree
import pyproj
from webapp.config import Config

engine  = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)

HOY   = datetime.today()
FECHA = (HOY + timedelta(days=3)).strftime("%Y-%m-%d")
N_DIAS = 14

VARIABLES = ["tempmedia", "humedadmedia", "etpmon"]

MIN_VECINOS      = 4
MAX_VECINOS      = 6
RADIO_INICIAL_KM = 80
RADIO_MAX_KM     = 180
PASO_RADIO_KM    = 30

POTENCIAS_IDW = {
    "tempmedia":    2.0,
    "humedadmedia": 2.5,
    "etpmon":       2.5,
}

ESTACIONES_EXCLUIR = set()

CARPETA_SALIDA = r"C:\datos\salida"
NOMBRE_SALIDA  = f"datoscultivos33final{FECHA}.csv"

# Mapeo de nombre interno → prefijo de columna en el CSV
PREFIJO_COL = {
    "tempmedia":    "Tp",
    "humedadmedia": "Hd",
    "etpmon":       "Ev",
}

# Orden de variables en el CSV: Tp primero, luego Hd, luego Ev
VARIABLES_ORDEN = ["tempmedia", "humedadmedia", "etpmon"]


# ------------------------------------------------------------
# FUNCIONES  (sin cambios)
# ------------------------------------------------------------

def get_utm_proj(lon, lat):
    zone = int((lon + 180) // 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)


def idw_adaptativo_metrico(puntos_conocidos_m, valores_conocidos, puntos_destino_m,
                           potencia=2.5, min_vecinos=4, max_vecinos=6,
                           radio_inicial_m=80000, radio_max_m=180000, paso_m=30000):
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
                d            = np.maximum(dists[mascara], 1e-12)
                v            = valores_conocidos[idxs[mascara]]
                pesos        = 1.0 / (d ** potencia)
                resultado[i] = np.sum(pesos * v) / np.sum(pesos)
                asignado     = True
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
    params      = {"fecha": fecha}
    excluir_sql = ""
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
    print(f"  ✅ {variable} ({fecha}): {len(datos)} estaciones.")
    return np.sort(datos, order='codigo')


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():
    fecha_dt = datetime.strptime(FECHA, "%Y-%m-%d")
    n_cols   = (N_DIAS + 1) * len(VARIABLES)  # 16 × 3 = 48

    print(f"\n📅 Interpolación — {FECHA}")
    print(f"   Variables : {VARIABLES}")
    print(f"   Días      : 0 (hoy) → -{N_DIAS}  →  {n_cols} columnas totales\n")

    session = conectar_bd()
    if not session:
        return

    df = obtener_cultivos(session)

    transformer_utm     = get_utm_proj(df['lon'].median(), df['lat'].median())
    x_cult, y_cult      = transformer_utm.transform(df['lon'].values, df['lat'].values)
    puntos_cultivos_utm = np.column_stack((x_cult, y_cult))

    # ── Bucle: día 0 hasta día -15, por cada variable ─────────────────────
    for dias in range(4, N_DIAS + 1):
        fecha_iter = (fecha_dt - timedelta(days=dias)).strftime("%Y-%m-%d")

        for variable in VARIABLES:
            # Nombre interno temporal (se renombrará al final)
            col_nombre = f"{variable}_0" if dias == 0 else f"{variable}_-{dias}"

            datos = obtener_estaciones(session, variable, fecha_iter)
            if datos is None:
                df[col_nombre] = np.nan
                continue

            if variable == "etpmon":
                mask        = datos['valor'] > 0
                n_filtrados = (~mask).sum()
                if n_filtrados:
                    nombres = [str(datos['nombre'][i]) for i in range(len(datos)) if not mask[i]]
                    print(f"  🚫 [etpmon] {n_filtrados} estación(es) con valor=0 descartadas "
                          f"en {fecha_iter}: {nombres}")
                datos = datos[mask]
                if len(datos) == 0:
                    print(f"  ⚠️  Sin datos válidos de etpmon en {fecha_iter} → NaN")
                    df[col_nombre] = np.nan
                    continue

            potencia       = POTENCIAS_IDW.get(variable, 2.5)
            x_est, y_est   = transformer_utm.transform(datos['lon'], datos['lat'])
            puntos_est_utm = np.column_stack((x_est, y_est))

            df[col_nombre] = idw_adaptativo_metrico(
                puntos_est_utm, datos['valor'], puntos_cultivos_utm,
                potencia=potencia,
                min_vecinos=MIN_VECINOS, max_vecinos=MAX_VECINOS,
                radio_inicial_m=RADIO_INICIAL_KM * 1000,
                radio_max_m=RADIO_MAX_KM * 1000,
                paso_m=PASO_RADIO_KM * 1000,
            )

    session.close()

    # ── Renombrar columnas de variables al formato final ───────────────────
    rename_map = {}
    for variable, prefijo in PREFIJO_COL.items():
        for dias in range(4, N_DIAS + 1):
            col_interna = f"{variable}_0" if dias == 0 else f"{variable}_-{dias}"
            # t-0 → _t  |  t-x → _t-x
            col_final   = f"{prefijo}_t" if dias == 0 else f"{prefijo}_t-{dias}"
            rename_map[col_interna] = col_final

    df = df.rename(columns=rename_map)

    # ── Renombrar columnas 
    df = df.rename(columns={
        "cultivo":      "Cl",
        "parc_sistexp": "Rg",
    })

    # ── Orden final de columnas de variables: Tp → Hd → Ev, de t-14 a t ──
    def col_final(prefijo, dias):
        return f"{prefijo}_t" if dias == 0 else f"{prefijo}_t-{dias}"

    cols_vars = [
        col_final(PREFIJO_COL[v], d)
        for v in VARIABLES_ORDEN
        for d in range(N_DIAS, 3, -1)   # t-14, t-13, …, t-4  (solo las 33 entradas)
    ]

    df = df.drop(columns=["lon", "lat"])

    # Añadir id → Rf
    df = df[["Cl", "Rg"] + cols_vars + ["geometry_wkt"]]
    df = df.sort_values(["Cl", "Rg", "geometry_wkt"],
                        na_position="last").reset_index(drop=True)
    df.insert(0, "Rf", df.index + 1)

    cols_numericas     = df.select_dtypes(include=[np.number]).columns.difference(["Rf"])
    df[cols_numericas] = df[cols_numericas].round(3)

    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    ruta_csv = os.path.join(CARPETA_SALIDA, NOMBRE_SALIDA)
    df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")

    print(f"\n💾 CSV guardado: {ruta_csv}  "
          f"({os.path.getsize(ruta_csv) / 1024 / 1024:.1f} MB)")
    print(f"   {n_cols} columnas de variables + Rf/Cl/Rg/geometry_wkt")
    print(f"   Orden: Rf, Cl, Rg, Tp_t-{N_DIAS}…Tp_t, Hd_t-{N_DIAS}…Hd_t, Ev_t-{N_DIAS}…Ev_t, geometry_wkt")


if __name__ == "__main__":
    main()