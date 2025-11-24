"""
routes.py
---------
Rutas REST para exponer capas SIGPAC como GeoJSON.

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
    """
    GET /api/recintos?bbox=minx,miny,maxx,maxy&limit=5000&simplify=0.0005

    - bbox: obligatorio para cargas grandes
    - limit: opcional (default 5000)
    - simplify: opcional (en grados)
    """
    bbox = request.args.get("bbox")
    limit = int(request.args.get("limit", 5000))
    simplify = request.args.get("simplify")
    simplify = float(simplify) if simplify else None

    try:
        data = recintos_geojson(bbox, limit=limit, simplify_tolerance=simplify)
        return jsonify(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400