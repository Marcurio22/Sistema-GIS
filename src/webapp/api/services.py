from __future__ import annotations

from flask import current_app
from sqlalchemy import text
from .. import db
import requests
import json


def recintos_geojson(bbox_str: str | None) -> dict:
    """
    Devuelve un FeatureCollection GeoJSON con los recintos obtenidos desde
    GeoServer (WFS), filtrados por un bounding box en WGS84.

    Parámetro bbox_str: "minx,miny,maxx,maxy" en lon/lat (EPSG:4326).
    """

    # Si no viene bbox, devolvemos un FeatureCollection vacío
    if not bbox_str:
        return {"type": "FeatureCollection", "features": []}

    # Parsear bbox
    try:
        minx, miny, maxx, maxy = map(float, bbox_str.split(","))
    except ValueError:
        raise ValueError(f"Formato de bbox no válido: {bbox_str!r}")

    # Config desde Flask (config.py / variables de entorno)
    cfg = current_app.config

    wfs_url = cfg.get(
        "GEOSERVER_WFS_URL",
        "http://100.102.237.86:8080/geoserver/wfs",
    )

    type_name = cfg.get("GEOSERVER_RECINTOS_TYPENAME", "gis_project:recintos_con_propietario")

    gs_user = cfg.get("GEOSERVER_USER")
    gs_password = cfg.get("GEOSERVER_PASSWORD")

    auth = None
    if gs_user and gs_password:
        auth = (gs_user, gs_password)

    # Parámetros WFS: GetFeature en GeoJSON, filtrado por bbox en EPSG:4326
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
        # Dejar que lo capture la ruta /api/recintos y devuelva un 500 genérico
        raise RuntimeError(f"Error al consultar GeoServer WFS: {exc}") from exc

    data = resp.json()

    # Nos aseguramos de devolver siempre un FeatureCollection
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise RuntimeError("Respuesta de GeoServer no es un FeatureCollection válido")

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
        features.append({
            "type": "Feature",
            "geometry": r["geom_json"],
            "properties": {
                "id_recinto": r["id_recinto"],
                "provincia": r["provincia"],
                "municipio": r["municipio"],
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

    return {
        "id": row["id_recinto"],
        "provincia": row["provincia"],
        "municipio": row["municipio"],
        "agregado": row["agregado"],
        "zona": row["zona"],
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

