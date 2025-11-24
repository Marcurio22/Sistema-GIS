from flask import request, jsonify
from . import api_bp
from .services import recintos_geojson

@api_bp.get("/recintos")
def recintos():
    bbox = request.args.get("bbox")
    if not bbox:
        return jsonify({"error": "Falta parámetro bbox=minx,miny,maxx,maxy"}), 400
    return jsonify(recintos_geojson(bbox))