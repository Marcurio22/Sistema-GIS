"""
routes.py
---------
Rutas REST para exponer capas SIGPAC como GeoJSON.
jjujjjjjj

Autor: Marcos Zamorano Lasso
Versión: 1.0.0
Fecha: 2025-11-24
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from .services import recintos_geojson

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.get("/recintos")
def recintos():
    bbox = request.args.get("bbox")
    fc = recintos_geojson(bbox)
    return jsonify(fc)