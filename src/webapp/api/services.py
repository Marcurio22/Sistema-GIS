from __future__ import annotations

from flask import current_app
from sqlalchemy import text
from .. import db
import requests
import json
from webapp.dashboard.utils_dashboard import municipios_finder


def recintos_geojson(bbox_str: str | None) -> dict:
    """
    Devuelve un FeatureCollection GeoJSON con los recintos obtenidos desde
    GeoServer (WFS), filtrados por un bounding box en WGS84.
    """
    if not bbox_str:
        return {"type": "FeatureCollection", "features": []}

    try:
        minx, miny, maxx, maxy = map(float, bbox_str.split(","))
    except ValueError:
        raise ValueError(f"Formato de bbox no válido: {bbox_str!r}")

    cfg = current_app.config
    wfs_url = cfg.get("GEOSERVER_WFS_URL", "http://100.102.237.86:8080/geoserver/wfs")
    type_name = cfg.get("GEOSERVER_RECINTOS_TYPENAME", "gis_project:recintos_con_propietario")
    gs_user = cfg.get("GEOSERVER_USER")
    gs_password = cfg.get("GEOSERVER_PASSWORD")

    auth = None
    if gs_user and gs_password:
        auth = (gs_user, gs_password)

    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": type_name,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:4326",
    }

    try:
        resp = requests.get(wfs_url, params=params, auth=auth, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Error al consultar GeoServer WFS: {exc}") from exc

    data = resp.json()

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise RuntimeError("Respuesta de GeoServer no es un FeatureCollection válido")

    # Enriquecer con nombres de provincia y municipio
    if data.get("features"):
        for feature in data["features"]:
            props = feature.get("properties", {})
            if props.get("provincia"):
                props["nombre_provincia"] = municipios_finder.obtener_nombre_provincia(props["provincia"])
            if props.get("provincia") and props.get("municipio"):
                props["nombre_municipio"] = municipios_finder.obtener_nombre_municipio(
                    props["provincia"], props["municipio"]
                )

    return data

def mis_recintos_geojson(bbox: str | None, user_id: int):
    """
    Devuelve GeoJSON de public.recintos del usuario (id_propietario=user_id),
    filtrado por bbox si viene.
    """
    if not bbox:
        raise ValueError("bbox requerido")

    parts = [p.strip() for p in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox debe tener 4 valores: minx,miny,maxx,maxy")

    minx, miny, maxx, maxy = map(float, parts)

    sql = text("""
        SELECT
            r.id_recinto,
            r.provincia, r.municipio, r.agregado, r.zona,
            r.poligono, r.parcela, r.recinto,
            COALESCE(u.username, 'N/A') AS propietario,
            ST_AsGeoJSON(r.geom)::json AS geom_json
        FROM public.recintos r
        LEFT JOIN public.usuarios u ON u.id_usuario = r.id_propietario
        WHERE r.id_propietario = :uid
          AND ST_Intersects(
                r.geom,
                ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
          )
    """)

    rows = db.session.execute(sql, {
        "uid": user_id,
        "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy
    }).mappings().all()

    


    features = []
    for r in rows:
        nombre_provincia = municipios_finder.obtener_nombre_provincia(r["provincia"])
        nombre_municipio = municipios_finder.obtener_nombre_municipio(r["provincia"], r["municipio"])

        features.append({
            "type": "Feature",
            "geometry": r["geom_json"],
            "properties": {
                "id_recinto": r["id_recinto"],
                "provincia": r["provincia"],
                "municipio": r["municipio"],
                "nombre_provincia": nombre_provincia,
                "nombre_municipio": nombre_municipio,
                "agregado": r["agregado"],
                "zona": r["zona"],
                "poligono": r["poligono"],
                "parcela": r["parcela"],
                "recinto": r["recinto"],
                "propietario": r["propietario"],
            },
        })



    
    return {"type": "FeatureCollection", "features": features}

def mis_recinto_detalle(id_recinto: int, user_id: int) -> dict:
    """
    Devuelve los datos completos de UN recinto del usuario, con geojson.
    """
    sql = text("""
        SELECT
            r.id_recinto,
            r.nombre,
            r.superficie_ha,
            r.fecha_creacion,
            r.activa,
            r.provincia, r.municipio, r.agregado, r.zona,
            r.poligono, r.parcela, r.recinto,
            COALESCE(u.username, 'N/A') AS propietario,
            ST_AsGeoJSON(r.geom)::json AS geom_json
        FROM public.recintos r
        LEFT JOIN public.usuarios u ON u.id_usuario = r.id_propietario
        WHERE r.id_recinto = :rid
          AND r.id_propietario = :uid
        LIMIT 1
    """)

    row = db.session.execute(sql, {"rid": id_recinto, "uid": user_id}).mappings().first()
    if not row:
        return None

    nombre_provincia = municipios_finder.obtener_nombre_provincia(row["provincia"])
    nombre_municipio = municipios_finder.obtener_nombre_municipio(row["provincia"], row["municipio"])
    return {
        "id": row["id_recinto"],
        "provincia": row["provincia"],
        "municipio": row["municipio"],
        "agregado": row["agregado"],
        "zona": row["zona"],
        "nombre_provincia": nombre_provincia,
        "nombre_municipio": nombre_municipio,
        "poligono": row["poligono"],
        "parcela": row["parcela"],
        "recinto": row["recinto"],
        "nombre": row["nombre"],
        "superficie_ha": float(row["superficie_ha"]) if row["superficie_ha"] is not None else None,
        "fecha_creacion": row["fecha_creacion"].isoformat() if row["fecha_creacion"] else None,
        "activa": bool(row["activa"]) if row["activa"] is not None else True,
        "propietario": row["propietario"],
        "geojson": json.dumps(row["geom_json"])
    }

# ---------------------------
# Catálogos
# ---------------------------

def catalogo_usos_sigpac() -> list[dict]:
    sql = text("""
        SELECT codigo, descripcion, grupo
        FROM public.usos_sigpac
        ORDER BY grupo, codigo
    """)
    rows = db.session.execute(sql).mappings().all()
    return [{"codigo": r["codigo"], "descripcion": r["descripcion"], "grupo": r["grupo"]} for r in rows]


def catalogo_productos_fega() -> list[dict]:
    sql = text("""
        SELECT codigo, descripcion
        FROM public.productos_fega
        ORDER BY codigo
    """)
    rows = db.session.execute(sql).mappings().all()
    return [{"codigo": int(r["codigo"]), "descripcion": r["descripcion"]} for r in rows]


# ---------------------------
# Cultivos
# ---------------------------

def get_cultivo_recinto(recinto_id: int) -> dict | None:
    # Devuelve el cultivo del recinto si existe.
    sql = text("""
        SELECT
          c.id_cultivo,
          c.id_recinto,
          c.tipo_cultivo,
          c.variedad,
          c.fecha_siembra,
          c.fecha_implantacion,
          c.fecha_cosecha_estimada,
          c.fecha_cosecha_real,
          c.estado,
          c.uso_sigpac,
          c.sistema_explotacion,
          c.tipo_registro,
          c.campana,
          c.id_padre,
          c.cod_producto,
          c.cultivo_custom,
          c.origen_cultivo,
          c.cosecha_estimada_auto,
          c.observaciones
        FROM public.cultivos c
        WHERE c.id_recinto = :rid
        ORDER BY c.id_cultivo DESC
        LIMIT 1
    """)
    row = db.session.execute(sql, {"rid": recinto_id}).mappings().first()
    if not row:
        return None

    def _d(x):
        return x.isoformat() if x else None

    return {
        "id_cultivo": row["id_cultivo"],
        "id_recinto": row["id_recinto"],
        "tipo_cultivo": row["tipo_cultivo"],
        "variedad": row["variedad"],
        "fecha_siembra": _d(row["fecha_siembra"]),
        "fecha_implantacion": _d(row["fecha_implantacion"]),
        "fecha_cosecha_estimada": _d(row["fecha_cosecha_estimada"]),
        "fecha_cosecha_real": _d(row["fecha_cosecha_real"]),
        "estado": row["estado"],
        "uso_sigpac": row["uso_sigpac"],
        "sistema_explotacion": row["sistema_explotacion"],
        "tipo_registro": row["tipo_registro"],
        "campana": row["campana"],
        "id_padre": row["id_padre"],
        "cod_producto": row["cod_producto"],
        "cultivo_custom": row["cultivo_custom"],
        "origen_cultivo": row["origen_cultivo"],
        "cosecha_estimada_auto": bool(row["cosecha_estimada_auto"]) if row["cosecha_estimada_auto"] is not None else False,
        "observaciones": row["observaciones"],
    }

def normalize_cultivo_payload(data: dict, existing: dict | None = None) -> dict:
    """
    Normaliza el payload para evitar errores típicos:
    - Si tipo_registro=CAMPANA: asegura fecha_siembra y fecha_implantacion (al menos una y las duplica).
    - Si tipo_registro=IMPLANTACION: asegura fecha_implantacion (y opcionalmente duplica a fecha_siembra).
    - Si campana es None en CAMPANA: la calcula como año de fecha inicio.
    """
    d = dict(data or {})

    # tipo_registro final
    tr = (d.get("tipo_registro") or (existing.get("tipo_registro") if existing else "") or "").upper().strip()
    if not tr:
        tr = "CAMPANA"  # default razonable

    # fechas nuevas o existentes
    fecha_siembra = d.get("fecha_siembra") or (existing.get("fecha_siembra") if existing else None)
    fecha_implantacion = d.get("fecha_implantacion") or (existing.get("fecha_implantacion") if existing else None)

    # Normalización
    if tr == "CAMPANA":
        # Si sólo llega una, copia a la otra
        if fecha_siembra and not fecha_implantacion:
            d["fecha_implantacion"] = fecha_siembra
            fecha_implantacion = fecha_siembra
        elif fecha_implantacion and not fecha_siembra:
            d["fecha_siembra"] = fecha_implantacion
            fecha_siembra = fecha_implantacion

        # Campaña: si viene vacía, usa el año de la fecha de inicio
        if d.get("campana") in (None, "", 0):
            base = fecha_siembra or fecha_implantacion
            if base and isinstance(base, str) and len(base) >= 4 and base[:4].isdigit():
                d["campana"] = int(base[:4])

    elif tr == "IMPLANTACION":
        # Para implantación, asegura fecha_implantacion si sólo llega siembra
        if fecha_siembra and not fecha_implantacion:
            d["fecha_implantacion"] = fecha_siembra
            fecha_implantacion = fecha_siembra

        # Garantizar que siempre exista fecha_siembra también:
        if fecha_implantacion and not d.get("fecha_siembra"):
            d["fecha_siembra"] = fecha_implantacion

    # Devuelve payload ya corregido
    d["tipo_registro"] = tr
    return d

def create_cultivo_recinto(recinto_id: int, data: dict) -> dict:
    """
    Crea el único cultivo del recinto. Si ya existe, error.
    """
    existing = get_cultivo_recinto(recinto_id)
    if existing:
        raise ValueError("ya_existe")

    # Normaliza antes de insertar
    data = normalize_cultivo_payload(data)

    params = {
        "id_recinto": recinto_id,
        "uso_sigpac": data.get("uso_sigpac"),
        "sistema_explotacion": data.get("sistema_explotacion"),
        "tipo_registro": data.get("tipo_registro"),
        "campana": data.get("campana"),
        "id_padre": data.get("id_padre"),
        "cod_producto": data.get("cod_producto"),
        "cultivo_custom": data.get("cultivo_custom"),
        "origen_cultivo": data.get("origen_cultivo"),
        "variedad": data.get("variedad"),
        "estado": data.get("estado", "planificado"),
        "fecha_siembra": data.get("fecha_siembra"),
        "fecha_implantacion": data.get("fecha_implantacion"),
        "fecha_cosecha_estimada": data.get("fecha_cosecha_estimada"),
        "fecha_cosecha_real": data.get("fecha_cosecha_real"),
        "cosecha_estimada_auto": data.get("cosecha_estimada_auto", False),
        "observaciones": data.get("observaciones"),
    }

    sql = text("""
        INSERT INTO public.cultivos (
          id_recinto,
          uso_sigpac,
          sistema_explotacion,
          tipo_registro,
          campana,
          id_padre,
          cod_producto,
          cultivo_custom,
          origen_cultivo,
          variedad,
          estado,
          fecha_siembra,
          fecha_implantacion,
          fecha_cosecha_estimada,
          fecha_cosecha_real,
          cosecha_estimada_auto,
          observaciones
        )
        VALUES (
          :id_recinto,
          :uso_sigpac,
          :sistema_explotacion,
          :tipo_registro,
          :campana,
          :id_padre,
          :cod_producto,
          :cultivo_custom,
          :origen_cultivo,
          :variedad,
          :estado,
          :fecha_siembra,
          :fecha_implantacion,
          :fecha_cosecha_estimada,
          :fecha_cosecha_real,
          :cosecha_estimada_auto,
          :observaciones
        )
        RETURNING id_cultivo
    """)

    new_id = db.session.execute(sql, params).scalar_one()
    db.session.commit()
    return get_cultivo_recinto(recinto_id)


def patch_cultivo_recinto(recinto_id: int, data: dict) -> dict:
    """
    Actualiza parcialmente el cultivo (por ejemplo observaciones, fechas, variedad, etc).
    """
    cultivo = get_cultivo_recinto(recinto_id)
    if not cultivo:
        raise ValueError("no_existe")
    
    # Normaliza antes de actualizar
    data = normalize_cultivo_payload(data, existing=cultivo)

    # Construcción dinámica del UPDATE
    allowed = {
        "uso_sigpac",
        "sistema_explotacion",
        "tipo_registro",
        "campana",
        "id_padre",
        "cod_producto",
        "cultivo_custom",
        "origen_cultivo",
        "variedad",
        "estado",
        "fecha_siembra",
        "fecha_implantacion",
        "fecha_cosecha_estimada",
        "fecha_cosecha_real",
        "cosecha_estimada_auto",
        "observaciones",
    }

    sets = []
    params = {"rid": recinto_id}

    for k, v in (data or {}).items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v

    if not sets:
        return cultivo  # nada que actualizar

    sql = text(f"""
        UPDATE public.cultivos
        SET {", ".join(sets)}
        WHERE id_recinto = :rid
        RETURNING id_cultivo
    """)

    db.session.execute(sql, params)
    db.session.commit()
    return get_cultivo_recinto(recinto_id)


def delete_cultivo_recinto(recinto_id: int) -> bool:
    sql = text("""
        DELETE FROM public.cultivos
        WHERE id_recinto = :rid
    """)
    res = db.session.execute(sql, {"rid": recinto_id})
    db.session.commit()
    return res.rowcount > 0
