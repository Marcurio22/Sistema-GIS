"""
services.py
-----------
Servicios GIS para exponer capas como GeoJSON desde PostGIS.

Autor: Marcos Zamorano Lasso
Versión: 1.0.0
Fecha: 2025-11-24

Responsabilidad:
- Consultar la tabla sigpac.recintos en PostGIS
- Filtrar por bounding box (bbox) en EPSG:4326
- Devolver FeatureCollection GeoJSON optimizada para web

Notas:
- Para rendimiento se usa:
    * operador && (filtro por MBR usando índice GiST)
    * ST_Intersects (filtro exacto)
- Se permite simplificación geométrica opcional.
"""

from __future__ import annotations

import json
from typing import Optional

import geopandas as gpd
from sqlalchemy import text
from shapely.geometry import box

from .. import db  # SQLAlchemy instance (init en __init__.py)


def _parse_bbox(bbox_str: str) -> tuple[float, float, float, float]:
    """
    Parsea bbox "minx,miny,maxx,maxy" y devuelve floats.
    Lanza ValueError si el formato no es válido.
    """
    try:
        parts = [float(v) for v in bbox_str.split(",")]
        if len(parts) != 4:
            raise ValueError
        minx, miny, maxx, maxy = parts
        if minx >= maxx or miny >= maxy:
            raise ValueError
        return minx, miny, maxx, maxy
    except Exception as exc:
        raise ValueError(
            "bbox debe tener formato 'minx,miny,maxx,maxy' en EPSG:4326"
        ) from exc


def recintos_geojson(
    bbox_str: Optional[str] = None,
    limit: int = 5000,
    simplify_tolerance: Optional[float] = None,
) -> dict:
    """
    Devuelve recintos como GeoJSON.

    Parámetros:
    - bbox_str: str | None
        Bounding box en EPSG:4326 (minx,miny,maxx,maxy).
        Si es None, devuelve un subconjunto por seguridad.
    - limit: int
        Límite de features para proteger el backend.
    - simplify_tolerance: float | None
        Si se indica, simplifica geometrías (grados) para aligerar.

    Retorna:
    - dict GeoJSON FeatureCollection
    """
    if bbox_str:
        minx, miny, maxx, maxy = _parse_bbox(bbox_str)

        sql = text("""
            SELECT
                provincia, altitud, municipio, agregado, zona,
                pendiente_media, poligono, parcela, recinto,
                geometry
            FROM sigpac.recintos
            WHERE geometry && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
              AND ST_Intersects(
                    geometry,
                    ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
                  )
            LIMIT :limit;
        """)

        params = dict(minx=minx, miny=miny, maxx=maxx, maxy=maxy, limit=limit)

    else:
        # Fallback: si no hay bbox, NO devolvemos todo (sería enorme)
        sql = text("""
            SELECT
                provincia, altitud, municipio, agregado, zona,
                pendiente_media, poligono, parcela, recinto,
                geometry
            FROM sigpac.recintos
            LIMIT :limit;
        """)
        params = dict(limit=limit)

    gdf = gpd.read_postgis(
        sql,
        db.engine,
        params=params,
        geom_col="geometry"  # <- IMPORTANTE: tu columna se llama geometry
    )

    if simplify_tolerance:
        gdf["geometry"] = gdf.geometry.simplify(
            simplify_tolerance, preserve_topology=True
        )

    return json.loads(gdf.to_json())
