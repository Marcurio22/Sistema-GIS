from flask import current_app
from sqlalchemy import text
from geopandas import GeoDataFrame
from shapely.geometry import shape
import geopandas as gpd
from webapp import db


def recintos_geojson(bbox_str: str | None) -> dict:
    """
    Devuelve un FeatureCollection GeoJSON con los recintos del esquema sigpac.recintos
    filtrados por un bounding box en WGS84.

    Parámetro bbox_str: "minx,miny,maxx,maxy" en lon/lat (EPSG:4326).
    """

    if not bbox_str:
        # Si no viene bbox, devolvemos un FC vacío
        return {"type": "FeatureCollection", "features": []}

    try:
        minx, miny, maxx, maxy = map(float, bbox_str.split(","))
    except ValueError:
        raise ValueError(f"Formato de bbox no válido: {bbox_str!r}")

    sql = text(
        """
        SELECT
            provincia,
            altitud,
            municipio,
            agregado,
            zona,
            pendiente_media,
            poligono,
            parcela,
            recinto,
            geometry
        FROM sigpac.recintos
        WHERE geometry && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
        """
    )

    params = {
        "minx": minx,
        "miny": miny,
        "maxx": maxx,
        "maxy": maxy,
    }

    # Usa el engine de SQLAlchemy configurado en Config.SQLALCHEMY_DATABASE_URI
    gdf = gpd.read_postgis(sql, db.engine, geom_col="geometry", params=params)

    if gdf.empty:
        return {"type": "FeatureCollection", "features": []}

    # Convertir el GeoDataFrame a FeatureCollection
    features = []
    for _, row in gdf.iterrows():
        geom = row["geometry"].__geo_interface__
        props = row.drop(labels=["geometry"]).to_dict()
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": props,
            }
        )

    return {"type": "FeatureCollection", "features": features}