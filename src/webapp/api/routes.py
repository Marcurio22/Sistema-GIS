"""
routes.py
---------
Rutas REST para exponer capas SIGPAC como GeoJSON y gestionar
solicitudes de parcelas.
"""

from __future__ import annotations

from flask import jsonify, request
from flask_login import login_required, current_user

from .. import db
from ..models import Parcela, SolicitudParcela

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


@api_bp.route("/solicitudes-parcela", methods=["POST"])
@login_required
def crear_solicitud_parcela():
    """
    Crear una solicitud para añadir una parcela a 'Mis parcelas'.

    El frontend puede mandar:
      - { "id_parcela": 123 }
    ó
      - {
          "id_parcela": null,
          "provincia": 34,
          "municipio": 23,
          "agregado": null,
          "zona": null,
          "poligono": 1,
          "parcela": 51
        }

    Reglas:
    - Si la parcela no existe -> 404
    - Si la parcela ya tiene propietario -> 400 (ya_tiene_propietario)
    - Si el usuario ya ha solicitado esa parcela -> 400 (ya_solicitada)
    - Si todo OK -> crea SolicitudParcela en estado 'pendiente'
    """
    data = request.get_json(silent=True) or {}

    id_parcela = data.get("id_parcela")

    parcela_obj = None

    if id_parcela:
        parcela_obj = Parcela.query.get(id_parcela)
    else:
        # Resolver por códigos SIGPAC
        provincia = data.get("provincia")
        municipio = data.get("municipio")
        poligono = data.get("poligono")
        parcela = data.get("parcela")
        agregado = data.get("agregado")
        zona = data.get("zona")

        if not all([provincia, municipio, poligono, parcela]):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Faltan datos para identificar la parcela",
                    }
                ),
                400,
            )

        q = Parcela.query.filter_by(
            provincia=provincia,
            municipio=municipio,
            poligono=poligono,
            parcela=parcela,
        )

        # agregado y zona pueden ser NULL
        if agregado is not None:
            q = q.filter(Parcela.agregado == agregado)
        if zona is not None:
            q = q.filter(Parcela.zona == zona)

        parcela_obj = q.first()

    if not parcela_obj:
        return jsonify({"ok": False, "error": "Parcela no encontrada"}), 404

    id_parcela_real = parcela_obj.id_parcela

    # Si ya tiene propietario, no se puede solicitar
    if parcela_obj.id_propietario is not None:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "La parcela ya tiene propietario",
                    "code": "ya_tiene_propietario",
                }
            ),
            400,
        )

    # Evitar solicitudes duplicadas del mismo usuario para la misma parcela
    existing = SolicitudParcela.query.filter_by(
        id_usuario=current_user.id_usuario,
        id_parcela=id_parcela_real,
    ).first()

    if existing:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Ya has solicitado esta parcela",
                    "code": "ya_solicitada",
                }
            ),
            400,
        )

    solicitud = SolicitudParcela(
        id_usuario=current_user.id_usuario,
        id_parcela=id_parcela_real,
        estado="pendiente",
    )
    db.session.add(solicitud)
    db.session.commit()

    return jsonify({"ok": True})