from flask import request, jsonify
from . import api_bp
from .services import recintos_geojson

@api_bp.get("/recintos")
def recintos():
    bbox = request.args.get("bbox")  # "minx,miny,maxx,maxy"
    return jsonify(recintos_geojson(bbox))