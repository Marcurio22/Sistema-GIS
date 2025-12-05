"""
routes.py
---------
Rutas REST para exponer capas SIGPAC como GeoJSON y gestionar
solicitudes de recintos.
"""

from __future__ import annotations

from flask import jsonify, request
from flask_login import login_required, current_user

from .. import db
from ..models import Recinto, Solicitudrecinto

from . import api_bp
from .services import recintos_geojson


@api_bp.get("/recintos")
def recintos():
    """
    Endpoint /api/recintos?bbox=minx,miny,maxx,maxy
    Devuelve un FeatureCollection GeoJSON.
    """
    bbox = request.args.get("bbox")

    try:
        fc = recintos_geojson(bbox)
    except ValueError as exc:
        # bbox mal formado
        return jsonify({"error": str(exc)}), 400
    except Exception:
        # cualquier otro error interno
        return jsonify({"error": "Error interno en /api/recintos"}), 500

    return jsonify(fc)


@api_bp.route("/solicitudes-recinto", methods=["POST"])
@login_required
def crear_solicitud_recinto():
    data = request.get_json(silent=True) or {}
    id_recinto = data.get("id_recinto")
    recinto_obj = None

    if id_recinto:
        recinto_obj = Recinto.query.get(id_recinto)
    else:
        provincia = data.get("provincia")
        municipio = data.get("municipio")
        poligono = data.get("poligono")
        parcela = data.get("parcela")
        recinto = data.get("recinto")
        agregado = data.get("agregado")
        zona = data.get("zona")

        if not all([provincia, municipio, poligono, parcela, recinto]):
            return jsonify({
                "ok": False,
                "error": "Faltan datos para identificar el recinto",
            }), 400

        q = Recinto.query.filter_by(
            provincia=provincia,
            municipio=municipio,
            poligono=poligono,
            parcela=parcela,
            recinto=recinto,
        )

        

        # ✅ Corregido: manejo apropiado de NULL
        if agregado is not None:
            q = q.filter(Recinto.agregado == agregado)
        else:
            q = q.filter(Recinto.agregado.is_(None))
            
        if zona is not None:
            q = q.filter(Recinto.zona == zona)
        else:
            q = q.filter(Recinto.zona.is_(None))

        recinto_obj = q.first()

    if not recinto_obj:
        return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404

    if recinto_obj.id_propietario is not None:
        return jsonify({
            "ok": False,
            "error": "El recinto ya tiene propietario",
            "code": "ya_tiene_propietario",
        }), 400

    existing = Solicitudrecinto.query.filter_by(
        id_usuario=current_user.id_usuario,
        id_recinto=recinto_obj.id_recinto,
    ).first()

    if existing:
        return jsonify({
            "ok": False,
            "error": "Ya has solicitado este recinto",
            "code": "ya_solicitada",
        }), 400

    solicitud = Solicitudrecinto(
        id_usuario=current_user.id_usuario,
        id_recinto=recinto_obj.id_recinto,
        estado="pendiente",
    )
    db.session.add(solicitud)
    db.session.commit()

    return jsonify({"ok": True})