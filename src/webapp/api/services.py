import geopandas as gpd
from sqlalchemy import text
from webapp import db

def recintos_geojson(bbox_str):
    minx, miny, maxx, maxy = map(float, bbox_str.split(","))
    sql = text("""
        SELECT * FROM sigpac.recintos
        WHERE ST_Intersects(
            geometry,
            ST_MakeEnvelope(:minx,:miny,:maxx,:maxy,4326)
        )
    """)
    gdf = gpd.read_postgis(sql, db.engine, params=dict(
        minx=minx, miny=miny, maxx=maxx, maxy=maxy
    ))
    return gdf.__geo_interface__
