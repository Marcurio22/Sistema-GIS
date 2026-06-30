"""
historico_cultivos_itacyl.py
════════════════════════════
Extrae el cultivo histórico de los recintos del usuario consultando las capas
WMS del ITACYL publicadas en GeoServer, usando WMS GetFeatureInfo.

Ejecutar UNA SOLA VEZ (o las veces que añadas nuevas capas de año).
Los resultados se guardan en la tabla public.cultivo_historico_itacyl.

Uso:
    # Ver qué devuelve la primera parcela en cada capa (sin guardar nada):
    python historico_cultivos_itacyl.py --dry-run

    # Procesar todas las capas:
    python historico_cultivos_itacyl.py

    # Procesar sólo una capa concreta:
    python historico_cultivos_itacyl.py --capa "gis_project:Cultivos_y_Ocupación_del_suelo_2011"

    # Procesar sólo recintos de un propietario:
    python historico_cultivos_itacyl.py --propietario 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import date

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ── Rutas ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

# ── Configuración ─────────────────────────────────────────────────────────────
DB_URL = (
    os.getenv("DATABASE_URL")
    or "postgresql://{u}:{p}@{h}:{port}/{db}".format(
        u=os.getenv("POSTGRES_USER"),
        p=os.getenv("POSTGRES_PASSWORD"),
        h=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        db=os.getenv("POSTGRES_DB"),
    )
)
GEOSERVER_BASE = os.getenv("GEOSERVER_WMS_URL", "").replace("/wms", "").rstrip("/")
GEOSERVER_WMS  = GEOSERVER_BASE + "/wms"
GS_USER        = os.getenv("GEOSERVER_USER")
GS_PASS        = os.getenv("GEOSERVER_PASSWORD")
GS_AUTH        = (GS_USER, GS_PASS) if GS_USER else None
WORKSPACE      = "gis_project"
STORE_NAME     = "mcsncyl_itacyl_wms"   # nombre del WMS store en GeoServer

# ── Capas ITACYL: año → nombre publicado en GeoServer ────────────────────────
# El script llama al REST API de GeoServer para obtener el nativeName de cada
# capa automáticamente, así que solo necesitas el nombre de GeoServer aquí.
# Para 2022 y 2023 ITACYL publicó la capa a nivel nacional (España).
CAPAS_POR_AÑO: dict[int, str] = {
    2011: "gis_project:Cultivos_y_Ocupación_del_suelo_2011",
    2012: "gis_project:Cultivos_y_Ocupación_del_suelo_2012",
    2013: "gis_project:Cultivos_y_Ocupación_del_suelo_2013",
    2014: "gis_project:Cultivos_y_Ocupación_del_suelo_2014",
    2015: "gis_project:Cultivos_y_Ocupación_del_suelo_2015",
    2016: "gis_project:Cultivos_y_Ocupación_del_suelo_2016",
    2017: "gis_project:Cultivos_y_Ocupación_del_suelo_2017",
    2018: "gis_project:Cultivos_y_Ocupación_del_suelo_2018",
    2019: "gis_project:Cultivos_y_Ocupación_del_suelo_2019",
    2020: "gis_project:Cultivos_y_Ocupación_del_suelo_2020",
    2021: "gis_project:Cultivos_y_Ocupación_del_suelo_2021",
    2022: "gis_project:Cultivos_y_Ocupación_del_suelo_2022",  # capa España
    2023: "gis_project:Cultivos_y_Ocupación_del_suelo_2023",  # capa España
    2024: "gis_project:Cultivos_y_Ocupación_del_suelo_2024",
    2025: "gis_project:Cultivos_y_Ocupación_del_suelo_2025",
}

# Pausa entre peticiones WMS (segundos) para no saturar el servidor upstream.
# A 0.10 s/recinto: 1000 recintos ≈ 100 s  (~1.7 min)
DELAY_SEG = 0.10

# ── DB engine ─────────────────────────────────────────────────────────────────
engine = create_engine(DB_URL)


LEGENDS_DIR = ROOT / "src" / "webapp" / "static" / "csv" / "legends"


def cargar_leyenda_csv(año: int) -> dict[str, str]:
    """
    Carga código → cultivo desde mcsncyl_{año}.csv (ya existente en el proyecto).
    Es la fuente fiable para capas España 2022/2023 y cualquier raster sin 'Cobertura'.
    """
    csv_path = LEGENDS_DIR / f"mcsncyl_{año}.csv"
    if not csv_path.exists():
        return {}
    legend: dict[str, str] = {}
    try:
        import csv as _csv
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            reader = _csv.DictReader(f, delimiter=";")
            for row in reader:
                cod = (row.get("Cod") or row.get("cod") or "").strip()
                label = (row.get("Cubierta") or row.get("cubierta") or "").strip()
                if cod and label:
                    legend[cod] = label
        print(f"  Leyenda CSV ({csv_path.name}): {len(legend)} entradas")
    except Exception as e:
        print(f"  [WARN] No se pudo leer {csv_path.name}: {e}")
    return legend


# ── Leyenda ArcGIS REST (fallback si no hay CSV) ─────────────────────────────
def obtener_leyenda_arcgis(wms_base_url: str, native_name: str) -> dict:
    """
    Consulta el REST API de ArcGIS MapServer para obtener código → descripción.
    Útil cuando la capa WMS solo devuelve 'Pixel Value' sin texto (p.ej. capas España).
    """
    import re as _re
    # WMS URL:  .../arcgis/services/MCSNCyL/MapServer/WMSServer
    # REST URL: .../arcgis/rest/services/MCSNCyL/MapServer
    rest_base = wms_base_url.replace("/WMSServer", "").replace("/wms", "")
    # Insertar /rest/ si no está ya
    if "/arcgis/services/" in rest_base:
        rest_base = rest_base.replace("/arcgis/services/", "/arcgis/rest/services/")
    m = _re.search(r'(\d+)$', native_name)
    if not m:
        return {}
    layer_id = m.group(1)
    legend_url = f"{rest_base}/{layer_id}/legend?f=json"
    print(f"  Leyenda ArcGIS: {legend_url}")
    try:
        r = requests.get(legend_url, timeout=15)
        r.raise_for_status()
        data = r.json()
        legend = {}
        for item in data.get("legend", []):
            label = (item.get("label") or "").strip()
            values = item.get("values", [])
            val = values[0] if values else None
            if label and val is not None:
                legend[str(val)] = label
        print(f"  {len(legend)} entradas en leyenda")
        return legend
    except Exception as e:
        print(f"  [WARN] No se pudo obtener leyenda ({e})")
        return {}


# ── Obtener WMS upstream desde GeoServer REST API ────────────────────────────
def _gs_rest(path: str) -> dict:
    url = f"{GEOSERVER_BASE}/rest/{path}"
    r = requests.get(url, auth=GS_AUTH,
                     headers={"Accept": "application/json"}, timeout=10)
    r.raise_for_status()
    return r.json()


def obtener_wms_upstream() -> str:
    """
    Lee el store 'mcsncyl_itacyl_wms' del REST API de GeoServer
    y devuelve la URL base del WMS de ITACYL.
    """
    data = _gs_rest(f"workspaces/{WORKSPACE}/wmsstores/{STORE_NAME}.json")
    caps_url = data["wmsStore"]["capabilitiesURL"]
    # caps_url suele terminar en '?SERVICE=WMS&VERSION=...&REQUEST=GetCapabilities'
    base = caps_url.split("?")[0]
    print(f"  WMS upstream: {base}")
    return base


def obtener_store_de_capa(capa_gs: str) -> str:
    """Devuelve el store name de una capa publicada en GeoServer."""
    nombre_local = capa_gs.split(":")[-1]
    try:
        data = _gs_rest(f"layers/{WORKSPACE}:{nombre_local}.json")
        resource_href = data.get("layer", {}).get("resource", {}).get("href", "")
        # href suele ser: .../workspaces/X/wmsstores/STORE/wmslayers/CAPA.json
        # o              .../workspaces/X/datastores/STORE/featuretypes/CAPA.json
        import re as _re
        m = _re.search(r"/(?:wmsstores|datastores)/([^/]+)/", resource_href)
        if m:
            store = m.group(1)
            print(f"  Store de '{nombre_local}': {store}")
            return store
    except Exception as e:
        print(f"  [WARN] No se pudo detectar store ({e})")
    return STORE_NAME   # fallback


def obtener_nombre_nativo(capa_gs: str, store: str = STORE_NAME) -> str:
    """
    Dado 'workspace:NombreCapa', devuelve el nativeName (nombre en el WMS upstream).
    """
    nombre_local = capa_gs.split(":")[-1]
    try:
        data = _gs_rest(
            f"workspaces/{WORKSPACE}/wmsstores/{store}/wmslayers/{nombre_local}.json"
        )
        native = data.get("wmsLayer", {}).get("nativeName", nombre_local)
        print(f"  Nombre nativo en upstream: {native}")
        return native
    except Exception as e:
        print(f"  [WARN] No se pudo obtener nativeName ({e}), usando '{nombre_local}'")
        return nombre_local


def obtener_wms_upstream_de_store(store: str) -> str:
    """Lee la URL del WMS upstream para el store indicado."""
    data = _gs_rest(f"workspaces/{WORKSPACE}/wmsstores/{store}.json")
    caps_url = data["wmsStore"]["capabilitiesURL"]
    base = caps_url.split("?")[0]
    print(f"  WMS upstream ({store}): {base}")
    return base


# ── Crear tabla destino ───────────────────────────────────────────────────────
DDL = text("""
CREATE TABLE IF NOT EXISTS public.cultivo_historico_itacyl (
    id               SERIAL PRIMARY KEY,
    id_recinto       INTEGER NOT NULL,
    año              INTEGER NOT NULL,
    capa             TEXT,
    uso_codigo       TEXT,
    uso_descripcion  TEXT,
    atributos_raw    TEXT,          -- JSON con todos los atributos recibidos
    fecha_consulta   DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE (id_recinto, año)
);
CREATE INDEX IF NOT EXISTS cultivo_hist_itacyl_recinto_idx
    ON public.cultivo_historico_itacyl (id_recinto);
""")


def crear_tabla():
    with engine.begin() as conn:
        conn.execute(DDL)
    print("Tabla public.cultivo_historico_itacyl lista.")


# ── Cargar recintos ───────────────────────────────────────────────────────────
def cargar_recintos(propietario: int | None = None,
                    todos: bool = False) -> list[dict]:
    """
    Por defecto devuelve solo recintos con propietario asignado (usuarios registrados).
    Con todos=True devuelve todos los recintos activos (348k+, muy lento).
    """
    if propietario is not None:
        filtro = "WHERE activa IS NOT FALSE AND id_propietario = :pid"
        params: dict = {"pid": propietario}
    elif todos:
        filtro = "WHERE activa IS NOT FALSE"
        params = {}
    else:
        # Por defecto: solo recintos con propietario (evita procesar el catálogo SIGPAC completo)
        filtro = "WHERE activa IS NOT FALSE AND id_propietario IS NOT NULL"
        params = {}

    sql = text(f"""
        SELECT
            id_recinto,
            id_propietario,
            ST_X(ST_Centroid(geom)) AS lon,
            ST_Y(ST_Centroid(geom)) AS lat,
            ST_XMin(geom) AS minx, ST_YMin(geom) AS miny,
            ST_XMax(geom) AS maxx, ST_YMax(geom) AS maxy
        FROM public.recintos
        {filtro}
        ORDER BY id_recinto
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


# ── WMS GetFeatureInfo ────────────────────────────────────────────────────────
def getfeatureinfo(capa: str, lon: float, lat: float,
                   pad: float = 0.0005,
                   verbose: bool = False,
                   wms_url: str | None = None,
                   nombre_nativo: str | None = None) -> dict | None:
    """
    Lanza WMS GetFeatureInfo para el punto (lon, lat) en la capa indicada.
    Devuelve el primer feature como dict, o None si no hay datos.
    """
    minx, miny = lon - pad, lat - pad
    maxx, maxy = lon + pad, lat + pad

    # Usar URL upstream si está disponible, si no fallback a GeoServer
    url_a_usar  = wms_url or GEOSERVER_WMS
    capa_query  = nombre_nativo or capa   # nombre en el servidor destino

    # ArcGIS WMS suele devolver HTML; GeoServer soporta JSON/GML/texto
    es_arcgis = url_a_usar and "arcgis" in url_a_usar.lower()
    formatos = (
        ["text/html", "text/plain", "application/vnd.ogc.gml"]
        if es_arcgis
        else ["application/json", "text/plain", "application/vnd.ogc.gml"]
    )

    for info_fmt in formatos:
        params = {
            "SERVICE":       "WMS",
            "VERSION":       "1.1.1",
            "REQUEST":       "GetFeatureInfo",
            "LAYERS":        capa_query,
            "QUERY_LAYERS":  capa_query,
            "STYLES":        "",
            "BBOX":          f"{minx},{miny},{maxx},{maxy}",
            "WIDTH":         "101",
            "HEIGHT":        "101",
            "FORMAT":        "image/png",
            "INFO_FORMAT":   info_fmt,
            "X":             "50",
            "Y":             "50",
            "FEATURE_COUNT": "1",
            "SRS":           "EPSG:4326",
            # EXCEPTIONS: ArcGIS no soporta application/json; se omite para compatibilidad
        }
        if not es_arcgis:
            params["EXCEPTIONS"] = "application/json"

        auth_req = GS_AUTH if url_a_usar == GEOSERVER_WMS else None
        try:
            r = requests.get(url_a_usar, params=params, auth=auth_req, timeout=20)
            ct = r.headers.get("content-type", "").lower()

            if verbose:
                print(f"  INFO_FORMAT={info_fmt}")
                print(f"  HTTP {r.status_code}  Content-Type: {ct}")
                print(f"  URL: {r.url}")
                print(f"  Body (2000 chars): {r.text[:2000]!r}")

            if r.status_code != 200:
                continue

            # Imagen o respuesta vacía → sin features en ese punto
            if len(r.content) < 15 or r.content[:4] in (b'\x89PNG', b'GIF8', b'\xff\xd8'):
                if verbose:
                    print("  → Respuesta es imagen/vacío, sin features.")
                continue

            body = r.text.strip()
            if not body:
                continue

            # ── JSON GeoJSON (GeoServer) ───────────────────────────────────
            if "json" in ct:
                try:
                    data = r.json()
                    features = data.get("features", [])
                    if features:
                        return features[0].get("properties", {}) or {}
                    if verbose:
                        print("  → GeoJSON vacío (0 features).")
                    continue
                except Exception:
                    pass

            # ── HTML (ArcGIS WMS) ─────────────────────────────────────────
            if "html" in ct or "<html" in body.lower()[:200]:
                try:
                    import re as _re2

                    # ArcGIS puede devolver Latin-1 mal etiquetado como UTF-8
                    for enc in ("utf-8", "latin-1", "iso-8859-1", "cp1252"):
                        try:
                            body = r.content.decode(enc)
                            break
                        except Exception:
                            pass

                    def _strip_tags(s: str) -> str:
                        return _re2.sub(r"<[^>]+>", "", s).strip()

                    props: dict = {}

                    # ESRI pone headers (<th>) en una <tr> y valores (<td>) en la siguiente
                    rows = _re2.findall(r"<tr[^>]*>(.*?)</tr>", body, _re2.IGNORECASE | _re2.DOTALL)
                    headers: list[str] = []
                    for row_html in rows:
                        ths = _re2.findall(r"<th[^>]*>(.*?)</th>", row_html, _re2.IGNORECASE | _re2.DOTALL)
                        tds = _re2.findall(r"<td[^>]*>(.*?)</td>", row_html, _re2.IGNORECASE | _re2.DOTALL)
                        if ths and not tds:
                            # Fila de cabecera
                            headers = [_strip_tags(h) for h in ths]
                        elif tds and headers:
                            # Fila de valores: zip con headers
                            vals = [_strip_tags(v) for v in tds]
                            for k, v in zip(headers, vals):
                                if k:
                                    props[k] = v
                            break  # solo primera fila de datos

                    if props:
                        return props

                    # Fallback: pares <th>K</th><td>V</td> en la misma fila
                    for m in _re2.finditer(
                        r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>",
                        body, _re2.IGNORECASE | _re2.DOTALL
                    ):
                        k = _strip_tags(m.group(1))
                        v = _strip_tags(m.group(2))
                        if k:
                            props[k] = v
                    if props:
                        return props

                except Exception:
                    pass
                if verbose:
                    print("  → HTML sin tabla de atributos reconocible.")
                    # Mostrar más del body para debug
                    print(f"  Body completo ({len(body)} chars): {body[:2000]!r}")
                continue

            # ── Texto plano ────────────────────────────────────────────────
            if "text" in ct:
                lines = [l for l in body.splitlines() if "=" in l]
                if lines:
                    props = {}
                    for l in lines:
                        k, _, v = l.partition("=")
                        props[k.strip()] = v.strip()
                    if props:
                        return props
                if verbose:
                    print("  → Texto plano sin pares clave=valor.")
                continue

            # ── GML / XML ──────────────────────────────────────────────────
            if "xml" in ct or "gml" in ct:
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(body)
                    props = {}
                    for elem in root.iter():
                        if elem.text and elem.text.strip() and not list(elem):
                            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                            if tag.lower() not in ("serviceexception",):
                                props[tag] = elem.text.strip()
                    if props:
                        return props
                except Exception:
                    pass
                if verbose:
                    print("  → GML/XML sin propiedades extraíbles.")
                continue

        except Exception as e:
            if verbose:
                print(f"  [ERROR] {e}")
            continue

    return None


def _extraer_campos(props: dict) -> tuple[str | None, str | None]:
    """
    Extrae (codigo, descripcion) del dict de propiedades WMS.
    - Para capas ITACYL/ArcGIS raster: campo 'Cobertura' → descripcion, 'Pixel Value' → codigo.
    - Para capas vectoriales: busca campos comunes de uso/cultivo.
    """
    if not props:
        return None, None

    # ── ITACYL raster (MCSNCyL): Pixel Value + Cobertura ─────────────────
    if "Cobertura" in props:
        codigo = props.get("Pixel Value") or props.get("OID")
        return (str(codigo) if codigo else None), str(props["Cobertura"])

    # ── Capas vectoriales: código de uso ──────────────────────────────────
    for k in ("USO", "COD_USO", "CODIGO", "COD", "Uso", "uso", "codigo"):
        if k in props:
            # Buscar descripción en campos asociados
            desc = None
            for dk in ("DESC_USO", "DESCRIPCION", "CULTIVO", "Descripcion", "descripcion"):
                if dk in props:
                    desc = str(props[dk])
                    break
            return str(props[k]), desc

    # ── Descripción directa ────────────────────────────────────────────────
    for k in ("DESC_USO", "DESCRIPCION", "CULTIVO", "Descripcion", "descripcion", "cultivo"):
        if k in props:
            return None, str(props[k])

    # ── Fallback: primeros dos campos disponibles ──────────────────────────
    keys = [k for k in props if k not in ("OID", "Count", "count")]
    if keys:
        return str(props[keys[0]]), (str(props[keys[1]]) if len(keys) > 1 else None)

    return None, None


# ── Guardar resultado ─────────────────────────────────────────────────────────
UPSERT = text("""
INSERT INTO public.cultivo_historico_itacyl
    (id_recinto, año, capa, uso_codigo, uso_descripcion, atributos_raw, fecha_consulta)
VALUES
    (:id_recinto, :año, :capa, :uso_codigo, :uso_descripcion, :atributos_raw, :fecha_consulta)
ON CONFLICT (id_recinto, año)
DO UPDATE SET
    uso_codigo      = EXCLUDED.uso_codigo,
    uso_descripcion = EXCLUDED.uso_descripcion,
    atributos_raw   = EXCLUDED.atributos_raw,
    fecha_consulta  = EXCLUDED.fecha_consulta
""")


def guardar(conn, id_recinto: int, año: int, capa: str, props: dict | None):
    cod, desc = _extraer_campos(props)
    conn.execute(UPSERT, {
        "id_recinto":      id_recinto,
        "año":             año,
        "capa":            capa,
        "uso_codigo":      cod,
        "uso_descripcion": desc,
        "atributos_raw":   json.dumps(props, ensure_ascii=False) if props else None,
        "fecha_consulta":  date.today(),
    })


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Extrae cultivo histórico ITACYL → PostGIS")
    parser.add_argument("--dry-run",      action="store_true",
                        help="Muestra la respuesta del primer recinto en cada capa sin guardar nada.")
    parser.add_argument("--capa",         type=str, default=None,
                        help="Nombre completo de una capa concreta (p.ej. 'gis_project:Cultivos_...').")
    parser.add_argument("--propietario",  type=int, default=None,
                        help="Procesar solo los recintos de este id_propietario.")
    parser.add_argument("--todos",        action="store_true",
                        help="Procesar TODOS los recintos (348k+). Por defecto solo los que tienen propietario.")
    args = parser.parse_args()

    if not GEOSERVER_WMS:
        print("[ERROR] GEOSERVER_WMS_URL no está definida en .env")
        sys.exit(1)

    # Seleccionar capas a procesar
    if args.capa:
        # Buscar el año asociado o usar 0 como genérico
        año = next((a for a, c in CAPAS_POR_AÑO.items() if c == args.capa), 0)
        capas = {año: args.capa}
    else:
        capas = CAPAS_POR_AÑO

    if not args.dry_run:
        crear_tabla()

    recintos = cargar_recintos(args.propietario, todos=args.todos)
    print(f"Recintos a procesar: {len(recintos)}")

    # Cache de URL upstream por store (cada capa puede venir de un store diferente)
    _wms_cache: dict = {}

    def _get_wms_info(capa: str):
        """Devuelve (wms_url, nombre_nativo) para una capa, detectando su store."""
        store = obtener_store_de_capa(capa)
        if store not in _wms_cache:
            try:
                _wms_cache[store] = obtener_wms_upstream_de_store(store)
            except Exception as e:
                print(f"  [WARN] No se pudo leer store '{store}': {e}")
                _wms_cache[store] = None
        wms_url = _wms_cache[store]
        native = obtener_nombre_nativo(capa, store) if wms_url else None
        return wms_url, native

    for año, capa in capas.items():
        print(f"\n{'='*60}")
        print(f"Capa: {capa}  (año {año})")
        print(f"{'='*60}")

        wms_upstream, nombre_nativo = _get_wms_info(capa)

        # Leyenda código → cultivo: primero CSV local, luego REST ArcGIS
        leyenda = cargar_leyenda_csv(año)
        if not leyenda and wms_upstream and nombre_nativo:
            leyenda = obtener_leyenda_arcgis(wms_upstream, nombre_nativo)

        ok = 0
        sin_datos = 0

        with engine.begin() as conn:
            for n, rec in enumerate(recintos, start=1):
                rid  = rec["id_recinto"]
                lon  = float(rec["lon"])
                lat  = float(rec["lat"])

                props = getfeatureinfo(
                    capa, lon, lat,
                    verbose=args.dry_run,
                    wms_url=wms_upstream,
                    nombre_nativo=nombre_nativo,
                )

                if args.dry_run:
                    print(f"\n--- Dry-run recinto {rid} (lon={lon:.5f}, lat={lat:.5f}) ---")
                    print(f"  WMS usado:            {wms_upstream or GEOSERVER_WMS}")
                    print(f"  Capa en upstream:     {nombre_nativo or capa}")
                    print(f"  Propiedades parseadas: {props}")
                    # Sólo el primer recinto en dry-run
                    break

                if props:
                    # Si hay leyenda y no hay campo texto, añadir descripción desde leyenda
                    if leyenda and "Cobertura" not in props:
                        pv = str(props.get("Pixel Value", ""))
                        if pv in leyenda:
                            props = dict(props)
                            props["Cobertura"] = leyenda[pv]

                    cod, desc = _extraer_campos(props)
                    guardar(conn, rid, año, capa, props)
                    ok += 1
                    if n <= 3 or n % 500 == 0:
                        print(f"  [{n}/{len(recintos)}] recinto {rid}: {cod} — {desc}")
                else:
                    sin_datos += 1
                    if n <= 3 or n % 500 == 0:
                        print(f"  [{n}/{len(recintos)}] recinto {rid}: sin datos")

                if DELAY_SEG > 0:
                    time.sleep(DELAY_SEG)

        if not args.dry_run:
            print(f"\nResultado capa {año}: {ok} con datos, {sin_datos} sin datos.")

    if not args.dry_run:
        print("\nHecho. Datos guardados en public.cultivo_historico_itacyl")
    else:
        print("\n[Dry-run completado — no se ha guardado nada]")
        print("Si la respuesta parece correcta, vuelve a ejecutar sin --dry-run.")
        print("Si los campos no se parsean bien, edita _extraer_campos() en el script.")


def fix_encoding():
    """
    Corrige los valores ya guardados con encoding incorrecto (Latin-1 leído como UTF-8).
    Ejecutar una sola vez si los datos muestran caracteres como 'Ã­' en lugar de 'í'.
    """
    tiene = db.session.execute if False else None  # solo para importar engine
    with engine.begin() as conn:
        rows = conn.execute(sa_text("""
            SELECT id, uso_descripcion
            FROM public.cultivo_historico_itacyl
            WHERE uso_descripcion IS NOT NULL
        """)).mappings().all()

        fixed = 0
        for row in rows:
            s = row["uso_descripcion"]
            try:
                # Si fue decodificado como UTF-8 cuando era Latin-1, re-encodificar y decodificar
                corrected = s.encode("latin-1").decode("utf-8")
                if corrected != s:
                    conn.execute(sa_text("""
                        UPDATE public.cultivo_historico_itacyl
                        SET uso_descripcion = :v
                        WHERE id = :id
                    """), {"v": corrected, "id": row["id"]})
                    fixed += 1
            except Exception:
                pass
        print(f"  Corregidos {fixed} registros.")


from sqlalchemy import text as sa_text  # noqa: E402 (importado aquí para fix_encoding)


if __name__ == "__main__":
    import sys as _sys
    if "--fix-encoding" in _sys.argv:
        print("Corrigiendo encoding en cultivo_historico_itacyl...")
        fix_encoding()
    else:
        main()
