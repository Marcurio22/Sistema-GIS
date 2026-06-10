import pandas as pd
import json
import os
import requests
import glob
import geopandas as gpd
from shapely import wkt
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
GEOSERVER_BASE_URL = os.getenv("GEOSERVER_WMS_URL", "").replace("/wms", "").rstrip("/")
GEOSERVER_USER     = os.getenv("GEOSERVER_USER")
GEOSERVER_PASSWORD = os.getenv("GEOSERVER_PASSWORD")
WORKSPACE          = "gis_project"

DB_USER     = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST     = os.getenv("POSTGRES_HOST")
DB_PORT     = os.getenv("POSTGRES_PORT")
DB_NAME     = os.getenv("POSTGRES_DB")

CARPETA_CSV = r"C:\Users\Instalador\Documents\Sistema-GIS-main\Prediccion\salidaPred"
STATIC_DIR  = r"C:\Users\Instalador\Documents\Sistema-GIS-main\src\webapp\static\etp_prediccion"
os.makedirs(STATIC_DIR, exist_ok=True)

AUTH         = (GEOSERVER_USER, GEOSERVER_PASSWORD)
HEADERS_JSON = {"Content-Type": "application/json"}
HEADERS_XML  = {"Content-Type": "application/xml"}

engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ── Lógica de color ───────────────────────────────────────────────────────────
def calcular_color(row, etp_valor):
    ayer = row["Ev_t"]
    return "green" if float(etp_valor) > float(ayer) else "red"

# ── Buscar CSV más reciente ───────────────────────────────────────────────────
def buscar_csv_reciente():
    archivos = glob.glob(os.path.join(CARPETA_CSV, "predicciones_*.csv"))
    if not archivos:
        raise FileNotFoundError(f"No se encontró ningún CSV en {CARPETA_CSV}")
    return max(archivos, key=os.path.getmtime)

# ── Detectar columnas ET ──────────────────────────────────────────────────────
def detectar_columnas_et(df):
    cols = [c for c in df.columns if c.startswith("ET_")]
    def parse_fecha(col):
        d, m = col.replace("ET_", "").split("/")
        return datetime(datetime.now().year, int(m), int(d))
    return sorted(cols, key=parse_fecha)

# ── Escribir tablas PostGIS ───────────────────────────────────────────────────
def generar_tablas_postgis():
    csv_path = buscar_csv_reciente()
    print(f"CSV encontrado: {csv_path}")

    df = pd.read_csv(csv_path)
    columnas_et = detectar_columnas_et(df)
    print(f"Columnas ET detectadas: {columnas_et}")

    indice = {}

    for offset, col in enumerate(columnas_et):
        fecha_str = col.replace("ET_", "")
        tabla     = f"etp_prediccion_{offset}"
        filas     = []

        for _, row in df.iterrows():
            try:
                geom = wkt.loads(row["geometry_wkt"])
                geom = geom.simplify(0.00005, preserve_topology=True)
            except Exception as e:
                print(f"  Error geometría fila {_}: {e}")
                continue

            etp_valor = row[col]
            filas.append({
                "cultivo":  str(row["Cl"]),
                "riego":    str(row["Rg"]),
                "etp": round(float(etp_valor), 3),
                "color":    calcular_color(row, etp_valor),
                "fecha":    fecha_str,
                "geometry": geom
            })

        gdf = gpd.GeoDataFrame(filas, crs="EPSG:4326")

        gdf.to_postgis(
            tabla,
            engine,
            if_exists="replace",
            index=False,
            chunksize=1000
        )

        with engine.connect() as conn:
            conn.execute(text(
                f'CREATE INDEX IF NOT EXISTS {tabla}_geom_idx '
                f'ON "{tabla}" USING GIST (geometry)'
            ))
            conn.commit()

        indice[str(offset)] = fecha_str
        print(f"  → tabla {tabla}  ({fecha_str}, {len(filas)} registros)")

    with open(os.path.join(STATIC_DIR, "indice.json"), "w") as f:
        json.dump(indice, f)
    print(f"  → indice.json guardado")

    print("Tablas PostGIS generadas.\n")
    return list(range(len(columnas_et)))

# ── GeoServer: comprobar si existe el datastore PostGIS ──────────────────────
def datastore_postgis_existe():
    url = f"{GEOSERVER_BASE_URL}/rest/workspaces/{WORKSPACE}/datastores/postgis_etp.json"
    return requests.get(url, auth=AUTH).status_code == 200

# ── GeoServer: crear datastore PostGIS ───────────────────────────────────────
def crear_datastore_postgis():
    ds_body = json.dumps({
        "dataStore": {
            "name": "postgis_etp",
            "type": "PostGIS",
            "enabled": True,
            "connectionParameters": {
                "entry": [
                    {"@key": "host",                "$": DB_HOST},
                    {"@key": "port",                "$": DB_PORT},
                    {"@key": "database",            "$": DB_NAME},
                    {"@key": "user",                "$": DB_USER},
                    {"@key": "passwd",              "$": DB_PASSWORD},
                    {"@key": "dbtype",              "$": "postgis"},
                    {"@key": "schema",              "$": "public"},
                    {"@key": "Expose primary keys", "$": "true"}
                ]
            }
        }
    })
    r = requests.post(
        f"{GEOSERVER_BASE_URL}/rest/workspaces/{WORKSPACE}/datastores",
        auth=AUTH, headers=HEADERS_JSON, data=ds_body
    )
    print(f"  Datastore PostGIS: {r.status_code} — {r.text[:200]}")
    return r.status_code in (200, 201)

# ── GeoServer: comprobar si existe la capa ───────────────────────────────────
def capa_existe(nombre):
    url = f"{GEOSERVER_BASE_URL}/rest/workspaces/{WORKSPACE}/datastores/postgis_etp/featuretypes/{nombre}.json"
    return requests.get(url, auth=AUTH).status_code == 200

# ── GeoServer: publicar capa desde PostGIS ───────────────────────────────────
def crear_capa(nombre, offset):
    ft_body = json.dumps({
        "featureType": {
            "name":       nombre,
            "nativeName": nombre,
            "title":      f"ETP Predicción día +{offset}",
            "enabled":    True,
            "srs":        "EPSG:4326",
            "defaultStyle": {
                "name": "etp_prediccion_estilo"
            }
        }
    })
    r = requests.post(
        f"{GEOSERVER_BASE_URL}/rest/workspaces/{WORKSPACE}/datastores/postgis_etp/featuretypes",
        auth=AUTH, headers=HEADERS_JSON, data=ft_body
    )
    print(f"  [FT] {r.status_code} — {r.text[:300]}")
    if r.status_code not in (200, 201):
        print(f"  [ERROR] No se pudo publicar capa {nombre}")
    else:
        print(f"  Capa {nombre} publicada correctamente.")

# ── GeoServer: recargar capa ──────────────────────────────────────────────────
def recargar_capa(nombre):
    url  = f"{GEOSERVER_BASE_URL}/rest/workspaces/{WORKSPACE}/datastores/postgis_etp/featuretypes/{nombre}.json"
    body = json.dumps({"featureType": {"enabled": True}})
    r    = requests.put(url, auth=AUTH, headers=HEADERS_JSON, data=body)
    print(f"  Recarga {nombre}: {r.status_code}")

# ── GeoServer: asignar estilo a la capa ──────────────────────────────────────
def asignar_estilo(nombre):
    url  = f"{GEOSERVER_BASE_URL}/rest/layers/{WORKSPACE}:{nombre}.json"
    body = json.dumps({
        "layer": {
            "defaultStyle": {
                "name": "etp_prediccion_estilo"
            }
        }
    })
    r = requests.put(url, auth=AUTH, headers=HEADERS_JSON, data=body)
    print(f"  Estilo asignado {nombre}: {r.status_code}")

# ── GeoServer: limpiar caché ──────────────────────────────────────────────────
def limpiar_cache(nombre):
    url = f"{GEOSERVER_BASE_URL}/gwc/rest/layers/{WORKSPACE}:{nombre}.json"
    r   = requests.delete(url, auth=AUTH)
    print(f"  Cache {nombre}: {r.status_code}")

# ── GeoServer: crear estilo SLD ───────────────────────────────────────────────
def asegurar_estilo():
    nombre = "etp_prediccion_estilo"

    sld = """<?xml version="1.0" encoding="UTF-8"?><sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>Default Styler</sld:Name>
    <sld:UserStyle>
      <sld:Name>Default Styler</sld:Name>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:Name>Verde</sld:Name>
          <ogc:Filter>
            <ogc:PropertyIsEqualTo>
              <ogc:PropertyName>color</ogc:PropertyName>
              <ogc:Literal>green</ogc:Literal>
            </ogc:PropertyIsEqualTo>
          </ogc:Filter>
          <sld:PolygonSymbolizer>
            <sld:Fill>
              <sld:CssParameter name="fill">#2e7d32</sld:CssParameter>
              <sld:CssParameter name="fill-opacity">0.3</sld:CssParameter>
            </sld:Fill>
            <sld:Stroke>
              <sld:CssParameter name="stroke">#1b5e20</sld:CssParameter>
            </sld:Stroke>
          </sld:PolygonSymbolizer>
        </sld:Rule>
        <sld:Rule>
          <sld:Name>Rojo</sld:Name>
          <ogc:Filter>
            <ogc:PropertyIsEqualTo>
              <ogc:PropertyName>color</ogc:PropertyName>
              <ogc:Literal>red</ogc:Literal>
            </ogc:PropertyIsEqualTo>
          </ogc:Filter>
          <sld:PolygonSymbolizer>
            <sld:Fill>
              <sld:CssParameter name="fill">#c62828</sld:CssParameter>
              <sld:CssParameter name="fill-opacity">0.3</sld:CssParameter>
            </sld:Fill>
            <sld:Stroke>
              <sld:CssParameter name="stroke">#b71c1c</sld:CssParameter>
            </sld:Stroke>
          </sld:PolygonSymbolizer>
        </sld:Rule>
        <sld:Rule>
          <sld:Name>ETP Label</sld:Name>
		  <MinScaleDenominator>1</MinScaleDenominator>
          <MaxScaleDenominator>25000</MaxScaleDenominator>
          <sld:TextSymbolizer>
            <sld:Label>
              <ogc:PropertyName>etp</ogc:PropertyName>
            </sld:Label>
            <sld:Font>
              <sld:CssParameter name="font-family">Arial</sld:CssParameter>
              <sld:CssParameter name="font-size">11</sld:CssParameter>
              <sld:CssParameter name="font-style">normal</sld:CssParameter>
              <sld:CssParameter name="font-weight">bold</sld:CssParameter>
            </sld:Font>
            <sld:LabelPlacement>
              <sld:PointPlacement>
                <sld:AnchorPoint>
                  <sld:AnchorPointX>0.5</sld:AnchorPointX>
                  <sld:AnchorPointY>0.5</sld:AnchorPointY>
                </sld:AnchorPoint>
              </sld:PointPlacement>
            </sld:LabelPlacement>
            <sld:Halo>
              <sld:Radius>2</sld:Radius>
              <sld:Fill>
                <sld:CssParameter name="fill">#000000</sld:CssParameter>
                <sld:CssParameter name="fill-opacity">0.5</sld:CssParameter>
              </sld:Fill>
            </sld:Halo>
            <sld:Fill>
              <sld:CssParameter name="fill">#ffffff</sld:CssParameter>
            </sld:Fill>
            <sld:VendorOption name="autoWrap">60</sld:VendorOption>
            <sld:VendorOption name="maxDisplacement">10</sld:VendorOption>
            <sld:VendorOption name="conflictResolution">true</sld:VendorOption>
          </sld:TextSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
"""

    existe = requests.get(
        f"{GEOSERVER_BASE_URL}/rest/styles/{nombre}.json", auth=AUTH
    ).status_code == 200

    if not existe:
        r = requests.post(
            f"{GEOSERVER_BASE_URL}/rest/styles",
            auth=AUTH,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"style": {"name": nombre, "filename": f"{nombre}.sld"}})
        )
        print(f"  Estilo creado: {r.status_code}")
    else:
        print("  Estilo ya existe, actualizando SLD...")

    r = requests.put(
        f"{GEOSERVER_BASE_URL}/rest/styles/{nombre}",
        auth=AUTH,
        headers={"Content-Type": "application/vnd.ogc.sld+xml"},
        data=sld.encode("utf-8")
    )
    print(f"  SLD subido: {r.status_code} — {r.text[:200]}")


def main():
    print("=" * 50)
    print(f"Iniciando generación ETP — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # 1. Escribir tablas en PostGIS
    offsets = generar_tablas_postgis()

    # 2. Asegurar estilo
    print("Comprobando estilo GeoServer...")
    asegurar_estilo()

    # 3. Asegurar datastore PostGIS
    print("\nComprobando datastore PostGIS...")
    if not datastore_postgis_existe():
        print("  Creando datastore PostGIS...")
        if not crear_datastore_postgis():
            print("  [ERROR] No se pudo crear el datastore, abortando.")
            return
    else:
        print("  Datastore PostGIS ya existe.")

    # 4. Crear o recargar capas y asignar estilo
    print("\nPublicando capas en GeoServer...")
    for offset in offsets:
        nombre = f"etp_prediccion_{offset}"
        if capa_existe(nombre):
            print(f"  {nombre} ya existe → recargando...")
            recargar_capa(nombre)
        else:
            print(f"  {nombre} no existe → creando...")
            crear_capa(nombre, offset)
        asignar_estilo(nombre)
        limpiar_cache(nombre)

    print("\nFinalizado.")

if __name__ == "__main__":
    main()