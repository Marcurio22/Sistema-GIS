# webapp/api/__init__.py
from flask import Blueprint, request, jsonify
from webapp import db
import geopandas as gpd

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/recintos", methods=["GET"])
def recintos_geojson():
    """
    Devuelve recintos del schema sigpac.recintos como GeoJSON,
    filtrando por bbox (minx,miny,maxx,maxy en EPSG:4326).
    """
    bbox_str = request.args.get("bbox")
    if not bbox_str:
        return jsonify({"error": "Parámetro 'bbox' obligatorio"}), 400

    try:
        minx, miny, maxx, maxy = map(float, bbox_str.split(","))
    except ValueError:
        return jsonify({"error": "bbox inválido. Uso: minx,miny,maxx,maxy"}), 400

    sql = f"""
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
            geom   -- columna geometry en sigpac.recintos
        FROM sigpac.recintos
        WHERE geom && ST_MakeEnvelope({minx}, {miny}, {maxx}, {maxy}, 4326)
    """

    gdf = gpd.read_postgis(sql, db.engine, geom_col="geom")
    return jsonify(gdf.__geo_interface__)
