from __future__ import annotations

from flask import current_app
import requests


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
