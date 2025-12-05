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
    """
    Crear una solicitud para añadir una recinto a 'Mis recintos'.

    El frontend puede mandar:
      - { "id_recinto": 123 }
    ó
      - {
          "id_recinto": null,
          "provincia": 34,
          "municipio": 23,
          "agregado": null,
          "zona": null,
          "poligono": 1,
          "recinto": 51
        }

    Reglas:
    - Si el recinto no existe -> 404
    - Si el recinto ya tiene propietario -> 400 (ya_tiene_propietario)
    - Si el usuario ya ha solicitado esa recinto -> 400 (ya_solicitada)
    - Si todo OK -> crea Solicitudrecinto en estado 'pendiente'
    """
    data = request.get_json(silent=True) or {}

    id_recinto = data.get("id_recinto")

    recinto_obj = None

    if id_recinto:
        recinto_obj = Recinto.query.get(id_recinto)
    else:
        # Resolver por códigos SIGPAC
        provincia = data.get("provincia")
        municipio = data.get("municipio")
        poligono = data.get("poligono")
        recinto = data.get("recinto")
        agregado = data.get("agregado")
        zona = data.get("zona")

        if not all([provincia, municipio, poligono, recinto]):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Faltan datos para identificar el recinto",
                    }
                ),
                400,
            )

        q = Recinto.query.filter_by(
            provincia=provincia,
            municipio=municipio,
            poligono=poligono,
            recinto=recinto,
        )

        # agregado y zona pueden ser NULL
        if agregado is not None:
            q = q.filter(Recinto.agregado == agregado)
        if zona is not None:
            q = q.filter(Recinto.zona == zona)

        recinto_obj = q.first()

    if not recinto_obj:
        return jsonify({"ok": False, "error": "recinto no encontrada"}), 404

    id_recinto_real = recinto_obj.id_recinto

    # Si ya tiene propietario, no se puede solicitar
    if recinto_obj.id_propietario is not None:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "El recinto ya tiene propietario",
                    "code": "ya_tiene_propietario",
                }
            ),
            400,
        )

    # Evitar solicitudes duplicadas del mismo usuario para la misma recinto
    existing = Solicitudrecinto.query.filter_by(
        id_usuario=current_user.id_usuario,
        id_recinto=id_recinto_real,
    ).first()

    if existing:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Ya has solicitado esta recinto",
                    "code": "ya_solicitada",
                }
            ),
            400,
        )

    solicitud = Solicitudrecinto(
        id_usuario=current_user.id_usuario,
        id_recinto=id_recinto_real,
        estado="pendiente",
    )
    db.session.add(solicitud)
    db.session.commit()

    return jsonify({"ok": True})