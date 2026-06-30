"""
routes.py
---------
Rutas REST para exponer capas SIGPAC como GeoJSON y gestionar
solicitudes de recintos.
"""

from __future__ import annotations
from fileinput import filename

from flask import Response, jsonify, request, send_from_directory, current_app
from xml.etree import ElementTree as ET
from pathlib import Path
from flask_login import login_required, current_user
import requests
import re as _re_api

from sqlalchemy import text, and_, func
import matplotlib
matplotlib.use('Agg') # que no intente abrir ventanas en el servidor


from datetime import date, datetime, timedelta, timezone
from shapely.geometry import shape, mapping
from rasterio.mask import mask as rio_mask
from decimal import Decimal
from geoalchemy2.shape import from_shape, to_shape
import os
import uuid

from PIL import Image
import numpy as np
import rasterio
from rasterio.warp import transform_geom

from .. import db
from ..models import ImagenDibujada, IndicesRaster, Recinto, Solicitudrecinto, Variedad, Estacion, DatosDiarios, Recinto, Contador
from ..dashboard.utils_dashboard import municipios_finder
from ..utils.legend_loader import load_legend_from_csv

from . import api_bp, legend_bp
from .services import (
    recintos_geojson,
    mis_recintos_geojson,
    mis_recinto_detalle,
    catalogo_usos_sigpac,
    catalogo_productos_fega,
    catalogo_operaciones_list,
    catalogo_operaciones_item,
    get_cultivo_recinto,
    create_cultivo_recinto,
    patch_cultivo_recinto,
    delete_cultivo_recinto,
    create_cultivo_historico_recinto,
    patch_cultivo_by_id, 
    delete_cultivo_by_id,
    list_operaciones_recinto,
    create_operacion_recinto,
    patch_operacion_by_id,
    delete_operacion_by_id,
    _sistema_cultivo_obj,
    visor_start_view_usuario
)

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

@api_bp.get("/mis-recintos")
@login_required
def mis_recintos():
    bbox = request.args.get("bbox")
    try:
        fc = mis_recintos_geojson(bbox, current_user.id_usuario)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Error interno en /api/mis-recintos"}), 500

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
        tipo_solicitud="aceptacion",
    ).first()

    if existing:
        return jsonify({
            "ok": False,
            "error": "Ya has solicitado este recinto",
            "code": "ya_solicitada",
        }), 400

    # Evitar que otro usuario solicite el mismo recinto si ya hay una solicitud pendiente
    existing_any_pending = Solicitudrecinto.query.filter_by(id_recinto=recinto_obj.id_recinto,estado="pendiente", tipo_solicitud="aceptacion").first()

    if existing_any_pending:
            return jsonify({
            "ok": False,
            "error": "Este recinto ya está solicitado por otro usuario",
            "code": "ya_solicitado_por_otro",
        }), 400

    solicitud = Solicitudrecinto(
        id_usuario=current_user.id_usuario,
        id_recinto=recinto_obj.id_recinto,
        estado="pendiente",
        tipo_solicitud="aceptacion"
    )
    db.session.add(solicitud)
    db.session.commit()

    return jsonify({"ok": True})

@api_bp.get("/mis-recinto/<int:recinto_id>")
@login_required
def mi_recinto_detalle(recinto_id: int):
    try:
        data = mis_recinto_detalle(recinto_id, current_user.id_usuario)
        if not data:
            return jsonify({"error": "Recinto no encontrado"}), 404
        return jsonify(data)
    except Exception:
        return jsonify({"error": "Error interno en /api/mis-recinto"}), 500
    
@api_bp.patch("/mis-recinto/<int:recinto_id>/activa")
@login_required
def actualizar_activa(recinto_id: int):
    data = request.get_json(silent=True) or {}
    activa = data.get("activa", None)

    if activa is None:
        return jsonify({"ok": False, "error": "Campo 'activa' requerido"}), 400

    if isinstance(activa, str):
        activa = activa.strip().lower() in ("1", "true", "t", "yes", "y", "si", "sí")

    if not isinstance(activa, bool):
        return jsonify({"ok": False, "error": "Campo 'activa' debe ser boolean"}), 400

    recinto = Recinto.query.filter_by(
        id_recinto=recinto_id,
        id_propietario=current_user.id_usuario
    ).first()

    if not recinto:
        return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404

    recinto.activa = activa
    db.session.commit()

    return jsonify({"ok": True, "activa": recinto.activa})

@api_bp.post("/mis-recinto/<int:recinto_id>/nombre")
@login_required
def editar_nombre_recinto(recinto_id):
    data = request.get_json(silent=True) or {}
    nombre = data.get("nombre", "").strip()

    if not nombre:
        return jsonify({"error": "Nombre inválido"}), 400

    recinto = Recinto.query.get_or_404(recinto_id)

    if recinto.id_propietario != current_user.id_usuario:
        return jsonify({"error": "Sin permiso"}), 403

    recinto.nombre = nombre
    db.session.commit()

    return jsonify({"ok": True, "nombre": nombre})

@api_bp.get("/visor-start-view")
@login_required
def visor_start_view():
    """Devuelve la vista inicial recomendada del visor para el usuario actual."""
    data = visor_start_view_usuario(current_user.id_usuario)
    if not data:
        return jsonify({"municipio_top": None, "center": None, "bbox": None})

    return jsonify(data)

@api_bp.route('/solicitud-eliminar-recinto/<int:id_recinto>/borrar', methods=['POST'])
@login_required
def solicitar_eliminar_recinto(id_recinto):
    try:
        data = request.get_json(silent=True) or {}
        motivo = (data.get("motivo") or "").strip()

        if not motivo:
            return jsonify({"error": "Debes indicar un motivo"}), 400

        # Verificar que el recinto existe
        recinto = Recinto.query.get(id_recinto)
        if not recinto:
            return jsonify({"error": "Recinto no encontrado"}), 404

        # Verificar que el usuario es el propietario del recinto
        if recinto.id_propietario != current_user.id_usuario:
            return jsonify({"error": "No tienes permiso para solicitar eliminar este recinto"}), 403

        # Verificar si ya existe una solicitud pendiente para este recinto
        solicitud_existente = Solicitudrecinto.query.filter_by(
            id_recinto=id_recinto,
            tipo_solicitud="eliminacion",
            estado="pendiente"
        ).first()

        if solicitud_existente:
            return jsonify({"error": "Ya existe una solicitud de eliminación pendiente para este recinto"}), 400

        # Crear la nueva solicitud (GUARDANDO el motivo)
        nueva_solicitud = Solicitudrecinto(
            id_usuario=current_user.id_usuario,
            id_recinto=id_recinto,
            tipo_solicitud="eliminacion",
            estado="pendiente",
            motivo_solicitud=motivo
        )

        db.session.add(nueva_solicitud)
        db.session.commit()

        return jsonify({
            "mensaje": "Solicitud de eliminación creada exitosamente",
            "id_solicitud": nueva_solicitud.id_solicitud
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"Error al crear solicitud: {str(e)}")
        return jsonify({"error": "Error interno del servidor"}), 500
    
@api_bp.get("/popup/cultivo-sigpac")
@login_required
def popup_cultivo_sigpac():
    """
    Devuelve info de cultivos SIGPAC en el punto (lat,lng) WGS84.
    Usa la view sigpac.v_cultivo_declarado_popup para mostrar campos 'bonitos' para popup.
    """
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    if lat is None or lng is None:
        return jsonify({"ok": False, "error": "Faltan lat/lng"}), 400

    sql = text("""
        SELECT
            provincia,
            municipio,
            poligono,
            parcela,
            recinto,
            parc_producto,
            parc_producto_nombre, 
            parc_sistexp,
            cultsecun_producto,
            cultsecun_ayudasol,
            parc_ayudasol,
            cultivo_actual_nombre,
            ST_AsGeoJSON(geometry)::json AS geojson
        FROM sigpac.v_cultivo_declarado_popup
        WHERE ST_Intersects(
            geometry,
            ST_SetSRID(ST_Point(:lng, :lat), 4326)
        )
        ORDER BY ST_Area(geometry) ASC
        LIMIT 1
    """)

    row = db.session.execute(sql, {"lat": lat, "lng": lng}).mappings().first()
    if not row:
        return jsonify({"ok": True, "found": False})

    # Nombres (si falla, devolvemos vacío, pero mantenemos el código)
    nombre_provincia = ""
    nombre_municipio = ""
    try:
        if row["provincia"] is not None:
            nombre_provincia = municipios_finder.obtener_nombre_provincia(int(row["provincia"])) or ""
        if row["provincia"] is not None and row["municipio"] is not None:
            nombre_municipio = municipios_finder.obtener_nombre_municipio(int(row["provincia"]), int(row["municipio"])) or ""
    except Exception:
        pass

    data = dict(row)
    data["nombre_provincia"] = nombre_provincia
    data["nombre_municipio"] = nombre_municipio

    return jsonify({"ok": True, "found": True, "data": data})


@api_bp.get("/popup/catastro")
@login_required
def popup_catastro():
    """
    Devuelve info de catastro.parcelas en el punto (lat,lng) WGS84.
    """
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    if lat is None or lng is None:
        return jsonify({"ok": False, "error": "Faltan lat/lng"}), 400

    sql = text("""
        SELECT
            id,
            refcat,
            area_m2,
            ST_AsGeoJSON(geometry)::json AS geojson
        FROM catastro.parcelas
        WHERE ST_Intersects(
            geometry,
            ST_SetSRID(ST_Point(:lng, :lat), 4326)
        )
        ORDER BY ST_Area(geometry) ASC
        LIMIT 1
    """)

    row = db.session.execute(sql, {"lat": lat, "lng": lng}).mappings().first()
    if not row:
        return jsonify({"ok": True, "found": False})

    return jsonify({"ok": True, "found": True, "data": dict(row)})



@legend_bp.get("/api/geoserver/legend")
def geoserver_legend():
    layer = request.args.get("layer")
    style = request.args.get("style", "")

    if not layer:
        return {"error": "Missing layer"}, 400


    GEOSERVER_WMS = current_app.config["GEOSERVER_WMS_URL"]

    params = {
        "SERVICE": "WMS",
        "REQUEST": "GetLegendGraphic",
        "VERSION": "1.1.1",
        "FORMAT": "image/png",
        "LAYER": layer,
        "TRANSPARENT": "true",
    }
    if style:
        params["STYLE"] = style

    r = requests.get(GEOSERVER_WMS, params=params, timeout=20)
    return Response(
        r.content,
        status=r.status_code,
        content_type=r.headers.get("Content-Type", "image/png"),
    )

@legend_bp.get("/api/legend/mcsncyl/<int:year>")
def legend_mcsncyl(year: int):
    """
    Devuelve la leyenda del MCSNCyL desde un CSV (no depende de GeoServer).
    """
    base_webapp = Path(__file__).resolve().parents[1]
    csv_path = base_webapp / "static" / "csv" / "legends" / f"mcsncyl_{year}.csv"

    try:
        payload = load_legend_from_csv(csv_path)
        payload["year"] = year
        return jsonify(payload)
    except FileNotFoundError:
        return jsonify({
            "error": "legend_not_found",
            "message": f"No existe {csv_path.name} en static/data/legends/"
        }), 404
    except Exception as e:
        return jsonify({
            "error": "legend_load_error",
            "message": str(e)
        }), 500

@api_bp.route('/popup/suelos')
@login_required
def popup_suelos():
    """
    Endpoint para obtener información de un punto de suelo al hacer click.
    Devuelve datos con nombres de campos normalizados.
    """
    try:
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        
        if lat is None or lng is None:
            return jsonify({'ok': False, 'found': False, 'error': 'Coordenadas inválidas'})
        
        # URL de GeoServer, .env supongo
        GEOSERVER_WMS = current_app.config["GEOSERVER_WMS_URL"]
        
        # Parámetros para GetFeatureInfo
        params = {
            'SERVICE': 'WMS',
            'VERSION': '1.1.1',
            'REQUEST': 'GetFeatureInfo',
            'LAYERS': 'ne:PtosMuestrasSuelosCyL_Etrs89_H30',
            'QUERY_LAYERS': 'ne:PtosMuestrasSuelosCyL_Etrs89_H30',
            'INFO_FORMAT': 'application/json',
            'FEATURE_COUNT': 1,
            'X': 50,
            'Y': 50,
            'SRS': 'EPSG:4326',
            'WIDTH': 101,
            'HEIGHT': 101,
            'BBOX': f'{lng-0.001},{lat-0.001},{lng+0.001},{lat+0.001}'
        }
        
        # Hacer la petición a GeoServer
        response = requests.get(GEOSERVER_WMS, params=params, timeout=10)
        
        if response.status_code != 200:
            return jsonify({'ok': False, 'found': False, 'error': 'Error en GeoServer'})
        
        data = response.json()
        features = data.get('features', [])
        
        if not features:
            return jsonify({'ok': True, 'found': False})
        
        # Obtener el primer feature
        feature = features[0]
        properties = feature.get('properties', {})
        geometry = feature.get('geometry', {})
        
        # Log para ver qué campos vienen realmente de GeoServer
        print("📋 Campos disponibles en GeoServer:", list(properties.keys()))
        print("📊 Valores de campos clave:")
        print(f"   - Campaña: {properties.get('Campaña')}")
        print(f"   - pH: {properties.get('pH')}")
        print(f"   - ID_MUESTRA: {properties.get('ID_MUESTRA')}")
        
        # Función auxiliar mejorada
        def get_value(*keys):
            """Busca el valor en diferentes variantes de nombres de campo"""
            for key in keys:
                value = properties.get(key)
                # Importante: considerar "" (string vacío) como None
                if value is not None and value != "":
                    return value
            return None
        
        # MAPEO DE CAMPOS CON VARIANTES (incluye correcciones críticas detectadas)
        field_mapping = {
            # Campos principales
            'id_muestra': get_value('ID_MUESTRA', 'ID_Muestra', 'id_muestra'),
            'origen': get_value('Origen', 'origen'),
            'campana': get_value('Campaña', 'Campanya', 'campana'),
            'laboratori': get_value('Laboratori', 'laboratori'),
            
            'ph': get_value('pH', 'ph', 'PH'),
            
            'acidez_basi': get_value('AcidezBasi', 'Acidez_Basi', 'acidez_basi'),
            
            'conductivi': get_value('Conductivi', 'conductividad', 'CE'),
            
            # Materia orgánica
            'mo_porc': get_value('MO_Porc', 'mo_porc', 'MO_%'),
            'materia_org': get_value('MateriaOrg', 'Materia_Org', 'materia_org'),
            
            # Textura
            'arena_porc': get_value('Arena_Porc', 'arena_porc', 'Arena_%'),
            'limo_porc': get_value('Limo_Porc', 'limo_porc', 'Limo_%'),
            'arcilla_po': get_value('Arcilla_Po', 'Arcilla_Porc', 'arcilla_porc', 'Arcilla_%'),
            
            'textura': get_value('Textura', 'textura'),
            'text_calcu': get_value('TextCalcu', 'Text_Calcu', 'text_calcu'),
            'grupo_textu': get_value('GrupoTextu', 'Grupo_Textu', 'grupo_textu'),
            'valoracion': get_value('Valoracion', 'valoracion'),
            
            # Nutrientes
            'p_olsen_pp': get_value('P_Olsen_pp', 'P_Olsen_ppm', 'p_olsen_ppm', 'P_ppm'),
            'p_olsen': get_value('P_Olsen', 'p_olsen', 'POlsen'),
            'potasio_pp': get_value('Potasio_pp', 'Potasio_ppm', 'potasio_ppm', 'K_ppm'),
            'potasio': get_value('Potasio', 'potasio'),
            'nitrogeno_': get_value('Nitrogeno_', 'nitrogeno', 'N', 'Nitrogeno'),
            'calcio_ppm': get_value('Calcio_ppm', 'calcio_ppm', 'Ca_ppm'),
            'calcio': get_value('Calcio', 'calcio'),
            'magnesio_p': get_value('Magnesio_p', 'Magnesio_ppm', 'magnesio_ppm', 'Mg_ppm'),
            'magnesio': get_value('Magnesio', 'magnesio'),
            
            # Coordenadas
            'coor_x_etr': get_value('COOR_X_ETR', 'Coor_X_Etr', 'coor_x', 'X_ETRS89'),
            'coor_y_etr': get_value('COOR_Y_ETR', 'Coor_Y_Etr', 'coor_y', 'Y_ETRS89'),
        }
        
        # Construir la respuesta con campos mapeados
        resultado = {
            'ok': True,
            'found': True,
            'data': {
                **field_mapping,  # Campos mapeados
                
                # Geometría para el highlight
                'geojson': {
                    'type': 'FeatureCollection',
                    'features': [{
                        'type': 'Feature',
                        'properties': field_mapping,
                        'geometry': geometry
                    }]
                }
            }
        }
        
        # Log detallado para debugging
        print(f"✅ Suelo encontrado en ({lat}, {lng})")
        print(f"   📍 ID Muestra: {field_mapping.get('id_muestra')}")
        print(f"   📅 Campaña: {field_mapping.get('campana')}")
        print(f"   🧪 pH: {field_mapping.get('ph')}")
        print(f"   🏢 Origen: {field_mapping.get('origen')}")
        print(f"   🔬 Laboratorio: {field_mapping.get('laboratori')}")
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Error en popup_suelos: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'found': False, 'error': str(e)})


def _parse_geoserver_features_response(response: requests.Response) -> list[dict]:
    try:
        if response.status_code != 200:
            return []
        text = (response.text or "").strip()
        if not text or text.startswith("<?xml") or text.startswith("<"):
            return []
        data = response.json()
        if isinstance(data, dict):
            return data.get("features") or []
        return []
    except Exception:
        return []


def _pick_best_feature(features: list[dict], lat: float, lng: float) -> dict | None:
    if not features:
        return None
    if len(features) == 1:
        return features[0]

    from shapely.geometry import Point

    pt = Point(lng, lat)
    best = None
    best_dist = float("inf")

    for feature in features:
        geom_data = feature.get("geometry")
        if not geom_data:
            continue
        try:
            geom = shape(geom_data)
            if geom.contains(pt) or geom.touches(pt) or geom.intersects(pt.buffer(0.00005)):
                return feature
            dist = geom.distance(pt)
            if dist < best_dist:
                best_dist = dist
                best = feature
        except Exception:
            continue

    return best or features[0]


def _mirame_layer_name(local_layer: str) -> str:
    """Capa publicada localmente gis_project:X → origen remoto mirame:X."""
    if ":" in local_layer:
        return "mirame:" + local_layer.split(":", 1)[1]
    return "mirame:" + local_layer


def _sanitize_chduero_gfi_html(html: str) -> str:
    """
    El HTML de GetFeatureInfo suele traer enlaces al GeoServer local (store en cascada).
    Quitamos los <a> del contenido y dejamos un enlace único al visor oficial de Mírame.
    """
    import re

    out = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", html, flags=re.IGNORECASE | re.DOTALL)
    out = re.sub(r"<a\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"</a>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+onclick\s*=\s*([\"']).*?\1", "", out, flags=re.IGNORECASE)
    return out


def _parse_gfi_response(response: requests.Response, lat: float, lng: float) -> dict | None:
    if response.status_code != 200:
        return None
    text = (response.text or "").strip()
    if not text:
        return None

    head = text[:400].lower()
    if text.startswith("<?xml") or "serviceexception" in head:
        return None

    content_type = (response.headers.get("Content-Type") or "").lower()

    if text.startswith("{"):
        features = _parse_geoserver_features_response(response)
        picked = _pick_best_feature(features, lat, lng)
        if picked:
            return picked
        return None

    no_feat_markers = (
        "no features were found",
        "search returned no results",
        "sin información",
        "no information",
    )
    if any(m in head for m in no_feat_markers):
        return None

    if (
        "html" in content_type
        or "<table" in head
        or "<tr" in head
        or "<body" in head
        or "<!doctype" in head
    ):
        return {"properties": {"_gfi_html": _sanitize_chduero_gfi_html(text)}, "geometry": None}

    return None


def _wms_getfeatureinfo(
    wms_url: str,
    layer: str,
    lat: float,
    lng: float,
    auth: tuple[str, str] | None,
    *,
    width: int = 101,
    height: int = 101,
    x: int = 50,
    y: int = 50,
    bbox: str | None = None,
    info_format: str = "application/json",
    srs: str = "EPSG:4326",
) -> requests.Response:
    if bbox is None:
        delta = 0.002
        bbox = f"{lng - delta},{lat - delta},{lng + delta},{lat + delta}"
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": layer,
        "QUERY_LAYERS": layer,
        "INFO_FORMAT": info_format,
        "FEATURE_COUNT": 10,
        "SRS": srs,
        "WIDTH": width,
        "HEIGHT": height,
        "X": x,
        "Y": y,
        "BBOX": bbox,
    }
    return requests.get(wms_url, params=params, timeout=12, auth=auth)


def _chduero_feature_at_point(
    local_wms: str,
    mirame_wms: str,
    layer: str,
    lat: float,
    lng: float,
    auth: tuple[str, str] | None,
    *,
    width: int | None = None,
    height: int | None = None,
    x: int | None = None,
    y: int | None = None,
    bbox: str | None = None,
) -> dict | None:
    """
    Capas CH Duero vía store WMS en cascada (Mírame).
    GetFeatureInfo text/html — primero Mírame directo (sin auth local).
    """
    mirame_layer = _mirame_layer_name(layer)
    attempts: list[tuple] = []

    if width and height and x is not None and y is not None and bbox:
        attempts.append((mirame_wms, mirame_layer, None, width, height, x, y, bbox))
        attempts.append((local_wms, layer, auth, width, height, x, y, bbox))

    for delta in (0.003, 0.015, 0.05):
        pt_bbox = f"{lng - delta},{lat - delta},{lng + delta},{lat + delta}"
        attempts.append((mirame_wms, mirame_layer, None, 101, 101, 50, 50, pt_bbox))
        attempts.append((local_wms, layer, auth, 101, 101, 50, 50, pt_bbox))

    for wms_url, lyr, req_auth, w, h, xi, yi, bb in attempts:
        try:
            resp = _wms_getfeatureinfo(
                wms_url, lyr, lat, lng, req_auth,
                width=w, height=h, x=xi, y=yi, bbox=bb,
                info_format="text/html",
            )
            feat = _parse_gfi_response(resp, lat, lng)
            if feat:
                return feat
        except Exception as exc:
            print(f"[CH-DUERO] GFI error {lyr}: {exc}")

    return None


@api_bp.route('/popup/chduero')
@login_required
def popup_chduero():
    """GetFeatureInfo WMS para capas CH Duero (store en cascada Mírame)."""
    try:
        layer = (request.args.get('layer') or '').strip()
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        bbox = (request.args.get('bbox') or '').strip() or None
        width = request.args.get('width', type=int)
        height = request.args.get('height', type=int)
        x = request.args.get('x', type=int)
        y = request.args.get('y', type=int)

        if not layer or lat is None or lng is None:
            return jsonify({'ok': False, 'found': False, 'error': 'Parámetros incompletos'})

        cfg = current_app.config
        auth = None
        if cfg.get("GEOSERVER_USER") and cfg.get("GEOSERVER_PASSWORD"):
            auth = (cfg["GEOSERVER_USER"], cfg["GEOSERVER_PASSWORD"])

        feature = _chduero_feature_at_point(
            cfg["GEOSERVER_WMS_URL"],
            cfg.get("CHDUERO_MIRAME_WMS_URL", "https://mirame.chduero.es/geoserver/mirame/wms"),
            layer,
            lat,
            lng,
            auth,
            width=width,
            height=height,
            x=x,
            y=y,
            bbox=bbox,
        )

        if not feature:
            print(f"[CH-DUERO] Sin GetFeatureInfo para {layer} en ({lat}, {lng})")
            return jsonify({'ok': True, 'found': False})

        return jsonify({
            'ok': True,
            'found': True,
            'feature': {
                'properties': feature.get('properties', {}),
                'geometry': feature.get('geometry'),
            },
        })

    except Exception as e:
        print(f"❌ Error en popup_chduero: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'found': False, 'error': str(e)})

# Catálogos para el frontend

@api_bp.get("/catalogos/usos-sigpac")
@login_required
def api_catalogo_usos_sigpac():
    try:
        return jsonify(catalogo_usos_sigpac())
    except Exception:
        return jsonify({"error": "Error interno en /api/catalogos/usos-sigpac"}), 500


@api_bp.get("/catalogos/productos-fega")
@login_required
def api_catalogo_productos_fega():
    try:
        return jsonify(catalogo_productos_fega())
    except Exception:
        return jsonify({"error": "Error interno en /api/catalogos/productos-fega"}), 500
    

@api_bp.get("/catalogos/productos-fega/<string:uso_sigpac>")
@login_required
def api_catalogo_productos_fega_filtrado(uso_sigpac):
    sql = text("""
        SELECT DISTINCT pf.codigo, pf.descripcion
        FROM public.cultivos c
        JOIN public.productos_fega pf ON pf.codigo = c.cod_producto
        WHERE c.uso_sigpac = :uso
          AND c.cod_producto IS NOT NULL
        ORDER BY pf.descripcion
    """)
    rows = db.session.execute(sql, {"uso": uso_sigpac}).mappings().all()
    return jsonify([{"codigo": int(r["codigo"]), "descripcion": r["descripcion"]} for r in rows])



# Catálogos Operaciones (SIEX)

@api_bp.get("/catalogos/operaciones/<string:catalogo>")
@login_required
def api_catalogo_operaciones(catalogo):
    parent = request.args.get("parent")
    q = request.args.get("q")
    limit = request.args.get("limit", type=int) or 200

    try:
        return jsonify(catalogo_operaciones_list(catalogo, parent, q, limit))
    except Exception:
        return jsonify({"error": "Error interno en /api/catalogos/operaciones"}), 500


@api_bp.get("/catalogos/operaciones/<string:catalogo>/<string:codigo>")
@login_required
def api_catalogo_operaciones_item(catalogo, codigo):
    parent = request.args.get("parent")
    try:
        row = catalogo_operaciones_item(catalogo, codigo, parent)
        if not row:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify(row)
    except Exception:
        return jsonify({"error": "Error interno en /api/catalogos/operaciones/<catalogo>/<codigo>"}), 500


# Cultivos por recinto

@api_bp.get("/mis-recinto/<int:recinto_id>/cultivo")
@login_required
def api_get_cultivo(recinto_id: int):
    try:
        recinto = Recinto.query.filter_by(
            id_recinto=recinto_id,
            id_propietario=current_user.id_usuario
        ).first()

        if not recinto:
            return jsonify({"error": "Recinto no encontrado"}), 404

        cultivo = get_cultivo_recinto(recinto_id)
        if not cultivo:
            return jsonify({"error": "Cultivo no encontrado"}), 404

        return jsonify(cultivo)
    except Exception:
        return jsonify({"error": "Error interno en GET /api/mis-recinto/<id>/cultivo"}), 500


@api_bp.post("/mis-recinto/<int:recinto_id>/cultivo")
@login_required
def api_create_cultivo(recinto_id: int):
    data = request.get_json(silent=True) or {}
    try:
        recinto = Recinto.query.filter_by(
            id_recinto=recinto_id,
            id_propietario=current_user.id_usuario
        ).first()

        if not recinto:
            return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404

        cultivo = create_cultivo_recinto(recinto_id, data)
        print ("Cultivo creado:", cultivo)
        return jsonify({"ok": True, "cultivo": cultivo}), 201

    except Exception:
        return jsonify({"ok": False, "error": "Error interno en POST /api/mis-recinto/<id>/cultivo"}), 500


@api_bp.patch("/mis-recinto/<int:recinto_id>/cultivo")
@login_required
def api_patch_cultivo(recinto_id: int):
    data = request.get_json(silent=True) or {}
    try:
        recinto = Recinto.query.filter_by(
            id_recinto=recinto_id,
            id_propietario=current_user.id_usuario
        ).first()

        if not recinto:
            return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404

        cultivo = patch_cultivo_recinto(recinto_id, data)
        return jsonify({"ok": True, "cultivo": cultivo})

    except ValueError as e:
        if str(e) == "no_existe":
            return jsonify({"ok": False, "error": "Cultivo no encontrado"}), 404
        return jsonify({"ok": False, "error": "Datos inválidos"}), 400

    except Exception:
        return jsonify({"ok": False, "error": "Error interno en PATCH /api/mis-recinto/<id>/cultivo"}), 500


@api_bp.delete("/mis-recinto/<int:recinto_id>/cultivo")
@login_required
def api_delete_cultivo(recinto_id: int):
    try:
        recinto = Recinto.query.filter_by(
            id_recinto=recinto_id,
            id_propietario=current_user.id_usuario
        ).first()

        if not recinto:
            return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404

        ok = delete_cultivo_recinto(recinto_id)
        if not ok:
            return jsonify({"ok": False, "error": "Cultivo no encontrado"}), 404

        return jsonify({"ok": True})

    except Exception:
        return jsonify({"ok": False, "error": "Error interno en DELETE /api/mis-recinto/<id>/cultivo"}), 500
    
def _jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v

@api_bp.get("/mis-recinto/<int:recinto_id>/cultivos-historico")
@login_required
def api_get_cultivos_historico(recinto_id: int):
    sql = text("""
        SELECT *
        FROM public.cultivos
        WHERE id_recinto = :rid
        ORDER BY COALESCE(fecha_siembra, fecha_implantacion) DESC, id_cultivo DESC
    """)
    rows = db.session.execute(sql, {"rid": recinto_id}).mappings().all()

    out = []
    for r in rows:
        d = dict(r)
        cultivo_dict = {k: _jsonable(v) for k, v in d.items()}
        
        cultivo_dict["sistema_cultivo"] = _sistema_cultivo_obj(r["sistema_cultivo_codigo"])
        
        out.append(cultivo_dict)

    return jsonify(out)

@api_bp.get("/mis-recinto/<int:recinto_id>/cultivos-sigpac")
@login_required
def api_get_cultivos_sigpac(recinto_id: int):
    """Declaraciones SIGPAC vinculadas al recinto (campaña actual y tablas históricas si existen)."""
    recinto = Recinto.query.filter_by(
        id_recinto=recinto_id,
        id_propietario=current_user.id_usuario,
    ).first()
    if not recinto:
        return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404

    # NOTA: "cultivo_declarado2" era una tabla alternativa/duplicada creada por scripts de descarga.
    # Para evitar confusión en UI, no la listamos aquí.
    fuentes = [
        ("sigpac.cultivo_declarado", "Campaña en curso"),
        ("sigpac.cultivo_declarado_anterior", "Campaña anterior"),
    ]

    params = {
        "prov": recinto.provincia,
        "mun": recinto.municipio,
        "agr": recinto.agregado or 0,
        "zon": recinto.zona or 0,
        "pol": recinto.poligono,
        "par": recinto.parcela,
        "rec": recinto.recinto,
    }

    out = []
    for tabla, campana_label in fuentes:
        schema, name = tabla.split(".", 1)
        existe = db.session.execute(
            text("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = :schema AND table_name = :name
            """),
            {"schema": schema, "name": name},
        ).scalar()
        if not existe:
            continue

        sql = text(f"""
            SELECT
                c.parc_producto,
                COALESCE(pf.descripcion, c.parc_producto::text) AS cultivo,
                c.parc_sistexp,
                ROUND((c.parc_supcult / 10000.0)::numeric, 4) AS superficie_ha,
                c.parc_ayudasol,
                c.tipo_aprovecha,
                c.cultsecun_producto,
                c.pdr_rec
            FROM {schema}.{name} c
            LEFT JOIN public.productos_fega pf ON pf.codigo = c.parc_producto
            WHERE c.provincia = :prov
              AND c.municipio = :mun
              AND COALESCE(c.agregado, 0) = COALESCE(:agr, 0)
              AND COALESCE(c.zona, 0) = COALESCE(:zon, 0)
              AND c.poligono = :pol
              AND c.parcela = :par
              AND c.recinto = :rec
        """)
        rows = db.session.execute(sql, params).mappings().all()
        for row in rows:
            item = {k: _jsonable(v) for k, v in dict(row).items()}
            item["campana"] = campana_label
            item["sistexp"] = (
                "Regadío" if str(item.get("parc_sistexp") or "").strip() == "R" else "Secano"
            )
            out.append(item)

    # ── Historial ITACYL (cultivo_historico_itacyl) ───────────────────────────
    tiene_itacyl = db.session.execute(text("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'cultivo_historico_itacyl'
    """)).scalar()

    if tiene_itacyl:
        _leyendas_mcsn: dict[int, dict[str, str]] = {}

        def _label_mcsncyl(anio: int, codigo) -> str | None:
            if codigo is None or str(codigo).strip() == "":
                return None
            if anio not in _leyendas_mcsn:
                try:
                    base = Path(__file__).resolve().parents[1]
                    csv_path = base / "static" / "csv" / "legends" / f"mcsncyl_{anio}.csv"
                    payload = load_legend_from_csv(str(csv_path))
                    _leyendas_mcsn[anio] = {
                        str(it["code"]): it["label"] for it in payload.get("items", [])
                    }
                except Exception:
                    _leyendas_mcsn[anio] = {}
            return _leyendas_mcsn[anio].get(str(codigo).strip())

        itacyl_rows = db.session.execute(text("""
            SELECT h.año, h.uso_codigo, h.uso_descripcion
            FROM public.cultivo_historico_itacyl h
            WHERE h.id_recinto = :rid
            ORDER BY h.año DESC
        """), {"rid": recinto_id}).mappings().all()

        def _itacyl_desc(s):
            if not s:
                return s
            try:
                s = s.encode("latin-1").decode("utf-8")
            except Exception:
                pass
            s = _re_api.sub(r'\s*[\(\[]\s*(Regad[íio]|Secano|Riego|Irrigado)\s*[\)\]]', '', s, flags=_re_api.IGNORECASE)
            s = _re_api.sub(r'\s+(regad[íio]|secano)\s*$', '', s.strip(), flags=_re_api.IGNORECASE)
            return s.strip()

        for row in itacyl_rows:
            anio = int(row["año"])
            desc = _itacyl_desc(row["uso_descripcion"])
            if not desc:
                desc = _label_mcsncyl(anio, row["uso_codigo"])
            if not desc:
                continue
            out.append({
                "cultivo":       desc,
                "uso_codigo":    row["uso_codigo"],
                "campana":       str(anio),
                "fuente":        "ITACYL",
                "sistexp":       None,
                "superficie_ha": None,
            })

    return jsonify({"ok": True, "items": out})

@api_bp.post("/mis-recinto/<int:recinto_id>/cultivo-historico")
@login_required
def api_create_cultivo_historico(recinto_id: int):
    data = request.get_json(silent=True) or {}

    recinto = Recinto.query.filter_by(
        id_recinto=recinto_id,
        id_propietario=current_user.id_usuario
    ).first()
    if not recinto:
        return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404

    try:
        cultivo = create_cultivo_historico_recinto(recinto_id, data)
        return jsonify({"ok": True, "cultivo": cultivo}), 201
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Error interno"}), 500
    
    
    
@api_bp.patch("/cultivos/<int:id_cultivo>")
@login_required
def api_patch_cultivo_by_id(id_cultivo: int):
    data = request.get_json(silent=True) or {}
    try:
        cultivo = patch_cultivo_by_id(id_cultivo, current_user.id_usuario, data)
        if not cultivo:
            return jsonify({"ok": False, "error": "Cultivo no encontrado"}), 404
        return jsonify({"ok": True, "cultivo": cultivo})
    except ValueError as e:
        if str(e) == "no_existe":
            return jsonify({"ok": False, "error": "Cultivo no encontrado"}), 404
        return jsonify({"ok": False, "error": "Datos inválidos"}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Error interno"}), 500
    
@api_bp.delete("/cultivos/<int:id_cultivo>")
@login_required
def api_delete_cultivo_by_id(id_cultivo: int):
    try:
        ok = delete_cultivo_by_id(id_cultivo, current_user.id_usuario)
        if not ok:
            return jsonify({"ok": False, "error": "Cultivo no encontrado"}), 404
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Error interno"}), 500
    
@api_bp.route('/variedades/buscar', methods=['GET'])
@login_required
def buscar_variedades():
    try:
        query = request.args.get('q', '').strip()
        producto_id = request.args.get('producto_id', type=int)  # Opcional: filtrar por cultivo
        
        if not query or len(query) < 1:  # Busca desde el primer carácter
            return jsonify([])
        
        # Query base
        variedades_query = Variedad.query
        
        # Filtrar por producto si se proporciona
        if producto_id:
            variedades_query = variedades_query.filter(
                Variedad.producto_fega_id == producto_id
            )
        
        # Buscar variedades que contengan el texto (no solo al inicio)
        variedades = variedades_query.filter(
            Variedad.nombre.ilike(f'%{query}%')
        ).order_by(Variedad.nombre).limit(50).all()
        
        resultados = [{'nombre': v.nombre} for v in variedades]
        
        return jsonify(resultados)
    
    except Exception as e:
        print(f"Error buscando variedades: {str(e)}")
        return jsonify([]), 500

# Operaciones por recinto

@api_bp.get("/mis-recinto/<int:recinto_id>/operaciones")
@login_required
def api_get_operaciones(recinto_id: int):
    try:
        # all=1 => devuelve todo
        all_flag = request.args.get("all", "").strip().lower() in ("1", "true", "t", "yes", "si", "sí")
        limit = request.args.get("limit", type=int)

        if all_flag:
            limit = None
        elif limit is None:
            limit = 50

        ops = list_operaciones_recinto(recinto_id, current_user.id_usuario, limit=limit)
        return jsonify(ops)

    except ValueError as e:
        msg = str(e)
        if msg == "recinto_no_encontrado_o_sin_permiso":
            return jsonify({"error": "Recinto no encontrado"}), 404
        return jsonify({"error": msg}), 400

    except Exception:
        return jsonify({"error": "Error interno en GET /api/mis-recinto/<id>/operaciones"}), 500


@api_bp.post("/mis-recinto/<int:recinto_id>/operaciones")
@login_required
def api_create_operacion(recinto_id: int):
    data = request.get_json(silent=True) or {}
    try:
        op = create_operacion_recinto(recinto_id, current_user.id_usuario, data)
        return jsonify({"ok": True, "operacion": op}), 201

    except ValueError as e:
        msg = str(e)
        if msg == "recinto_no_encontrado_o_sin_permiso":
            return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404
        if msg.startswith("tipo_no_valido:"):
            return jsonify({"ok": False, "error": "Tipo de operación no válido"}), 400
        if msg == "tipo_requerido":
            return jsonify({"ok": False, "error": "Campo 'tipo' requerido"}), 400
        if msg == "fecha_requerida":
            return jsonify({"ok": False, "error": "Campo 'fecha' requerido"}), 400
        return jsonify({"ok": False, "error": msg}), 400

    except Exception:
        return jsonify({"ok": False, "error": "Error interno en POST /api/mis-recinto/<id>/operaciones"}), 500


@api_bp.patch("/operaciones/<int:id_operacion>")
@login_required
def api_patch_operacion(id_operacion: int):
    data = request.get_json(silent=True) or {}
    try:
        op = patch_operacion_by_id(id_operacion, current_user.id_usuario, data)
        return jsonify({"ok": True, "operacion": op})

    except ValueError as e:
        msg = str(e)
        if msg == "operacion_no_encontrada_o_sin_permiso":
            return jsonify({"ok": False, "error": "Operación no encontrada"}), 404
        if msg.startswith("tipo_no_valido:"):
            return jsonify({"ok": False, "error": "Tipo de operación no válido"}), 400
        if msg == "tipo_requerido":
            return jsonify({"ok": False, "error": "Campo 'tipo' requerido"}), 400
        if msg == "fecha_requerida":
            return jsonify({"ok": False, "error": "Campo 'fecha' requerido"}), 400
        return jsonify({"ok": False, "error": msg}), 400

    except Exception:
        return jsonify({"ok": False, "error": "Error interno en PATCH /api/operaciones/<id>"}), 500


@api_bp.delete("/operaciones/<int:id_operacion>")
@login_required
def api_delete_operacion(id_operacion: int):
    try:
        ok = delete_operacion_by_id(id_operacion, current_user.id_usuario)
        if not ok:
            return jsonify({"ok": False, "error": "Operación no encontrada"}), 404
        return jsonify({"ok": True})

    except Exception:
        return jsonify({"ok": False, "error": "Error interno en DELETE /api/operaciones/<id>"}), 500
    


@api_bp.route('/indices-raster', methods=['GET'])
@login_required
def get_indices_raster():
    """
    Obtiene los índices raster filtrados por id_recinto y tipo_indice
    Query params: id_recinto (requerido), tipo_indice (opcional, default='NDVI')
    """
    try:
        id_recinto = request.args.get('id_recinto', type=int)
        tipo_indice = request.args.get('tipo_indice', default='NDVI', type=str)
        
        if not id_recinto:
            return jsonify({'error': 'id_recinto es requerido'}), 400
        
        # Query a la base de datos usando la relación
        indices = IndicesRaster.query.filter_by(
            id_recinto=id_recinto,
            tipo_indice=tipo_indice
        ).order_by(IndicesRaster.fecha_ndvi.desc()).all()
        
        # Meses abreviados
        meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 
                'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
        
        # Convertir a lista de diccionarios y añadir fecha formateada
        results = []
        for indice in indices:
            data = indice.to_dict()
            # Añadir fecha formateada
            if indice.fecha_ndvi:
                fecha_obj = indice.fecha_ndvi
                data['fecha_ndvi_formateada'] = f"{fecha_obj.day:02d} {meses[fecha_obj.month-1]}. {fecha_obj.year}"
            else:
                data['fecha_ndvi_formateada'] = None
            results.append(data)
        
        return jsonify(results), 200
        
    except Exception as e:
        print(f"Error en get_indices_raster: {str(e)}")
        return jsonify({'error': 'Error al obtener los índices'}), 500


@api_bp.route('/indices-raster/<int:id_indice>', methods=['GET'])
@login_required
def get_indice_by_id(id_indice):
    """
    Obtiene un índice raster específico por su ID
    """
    try:
        indice = IndicesRaster.query.get(id_indice)
        
        if not indice:
            return jsonify({'error': 'Índice no encontrado'}), 404
        
        return jsonify(indice.to_dict()), 200
        
    except Exception as e:
        print(f"Error en get_indice_by_id: {str(e)}")
        return jsonify({'error': 'Error al obtener el índice'}), 500
    


@api_bp.route('/grafica-ndvi/<int:recinto_id>', methods=['GET'])
@login_required
def grafica_ndvi(recinto_id):
    try:
        indices = IndicesRaster.query.filter_by(
            id_recinto=recinto_id,
            tipo_indice='NDVI'
        ).order_by(IndicesRaster.fecha_ndvi.desc()).all()

        if not indices:
            return jsonify({"error": "No hay datos NDVI disponibles"}), 404
        
        # Preparar datos
        fechas = []
        valores = []
        
        for indice in indices:
            if indice.fecha_ndvi:
                fecha_obj = indice.fecha_ndvi
                meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 
                        'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
                fecha_formateada = f"{fecha_obj.day:02d} {meses[fecha_obj.month-1]}. {fecha_obj.year}"
                fechas.append(fecha_formateada)
                valores.append(round(indice.valor_medio, 2))

        return jsonify({
            "fechas": fechas,
            "valores": valores
        }), 200
        
    except Exception as e:
        print(f"Error en grafica_ndvi: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    

@api_bp.route('/guardar-dibujos', methods=['POST'])
@login_required
def guardar_dibujos():
    try:
        data = request.get_json()
        dibujos = data.get('dibujos', [])
        
        if not dibujos:
            return jsonify({'error': 'No se recibieron consultas'}), 400
        
        # Límite de dibujos por usuario
        MAX_DIBUJOS = 10
        dibujos_existentes = ImagenDibujada.query.filter_by(id_usuario=current_user.id_usuario).count()
        
        if dibujos_existentes >= MAX_DIBUJOS:
            return jsonify({'error': f'Has alcanzado el límite de {MAX_DIBUJOS} consultas permitidos'}), 400
        
        # Solo guardar hasta llegar al límite
        espacio_disponible = MAX_DIBUJOS - dibujos_existentes
        dibujos_a_guardar = dibujos[:espacio_disponible]
        
        guardados = 0
        
        for dibujo in dibujos_a_guardar:
            geojson = dibujo.get('geojson')
            tipo = dibujo.get('tipo')
            
            if not geojson:
                continue
            
            geometry = shape(geojson['geometry'])
            area_m2 = geometry.area * 111320 * 111320
            ndvi_max, ndvi_min, ndvi_medio = calcular_ndvi(geometry)
            
            nueva_imagen = ImagenDibujada(
                id_usuario=current_user.id_usuario,
                ndvi_max=ndvi_max,
                ndvi_min=ndvi_min,
                ndvi_medio=ndvi_medio,
                geom=from_shape(geometry, srid=4326),
                tipo_geometria=tipo,
                area_m2=area_m2,
                fecha_creacion=datetime.now(timezone.utc)
            )
            
            db.session.add(nueva_imagen)
            guardados += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'guardados': guardados,
            'message': f'Se guardaron {guardados} consultas correctamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error al guardar consultas: {str(e)}")
        return jsonify({'error': str(e)}), 500




def calcular_ndvi(geometry, tiff_path=None):
    """
    Calcula NDVI desde GeoTIFF georreferenciado
    """

    BASE_DIR = Path(__file__).resolve().parents[3]
    if tiff_path is None:
        tiff_path = BASE_DIR / "data" / "raw" / "ndvi_composite" / "ndvi_latest_3857.tif"
    else:
        tiff_path = Path(tiff_path) 


    """
    Calcula NDVI desde GeoTIFF georreferenciado
    
    Args:
        geometry: Geometría Shapely en EPSG:4326 (WGS84)
        tiff_path: Ruta al archivo GeoTIFF
    
    Returns:
        tuple: (ndvi_max, ndvi_min, ndvi_medio) o (None, None, None) si falla
    """

    try:
        # 1. Verificar que el archivo existe
        
        if not os.path.exists(tiff_path):
            print(f"❌ ERROR: Archivo no encontrado: {tiff_path}")
            return None, None, None
        
        
        # 2. Abrir el GeoTIFF
        with rasterio.open(tiff_path) as src:
            
            # 3. Convertir geometría de entrada a GeoJSON
            geom_geojson = mapping(geometry)
            
            # 4. Transformar geometría al CRS del raster
            geom_transformed = transform_geom(
                'EPSG:4326',
                src.crs,
                geom_geojson
            )
            from shapely.geometry import box, shape
            raster_bbox = box(*src.bounds)
            geom_shape = shape(geom_transformed)
            
            if not raster_bbox.intersects(geom_shape):
                return None, None, None
            
            
            
            # 6. Recortar el raster con la geometría
            try:
                out_image, out_transform = rio_mask(
                    src,
                    [geom_transformed],
                    crop=True,
                    nodata=src.nodata if src.nodata is not None else -9999,
                    all_touched=True  # Incluir píxeles que toquen el polígono
                )
            except ValueError as e:
                return None, None, None
            
            # 7. Extraer datos NDVI
            ndvi_data = out_image[0]  # Primera (y única) banda
            
            # 8. Filtrar valores válidos
            # Considerar válidos los valores entre -1 y 1 (rango típico de NDVI)
            nodata_value = src.nodata if src.nodata is not None else -9999
            
            # Crear máscara de valores válidos
            mascara_validos = (
                (ndvi_data >= -1) & 
                (ndvi_data <= 1) & 
                (ndvi_data != nodata_value) &
                ~np.isnan(ndvi_data)
            )
            
            ndvi_validos = ndvi_data[mascara_validos]
            
            # 9. Verificar que hay suficientes píxeles válidos
            if len(ndvi_validos) < 10:
                
                if len(ndvi_validos) == 0:
                   
                    return None, None, None
            
            # 10. Calcular estadísticas
            ndvi_max = float(np.max(ndvi_validos))
            ndvi_min = float(np.min(ndvi_validos))
            ndvi_medio = float(np.mean(ndvi_validos))
            
            
            return ndvi_max, ndvi_min, ndvi_medio
            
    except rasterio.errors.RasterioIOError as e:
        print(f"❌ ERROR de I/O al leer el GeoTIFF:")
        print(f"   {str(e)}")
        return None, None, None
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, None, None
    



@api_bp.route('/obtener-dibujos', methods=['GET'])
@login_required
def obtener_dibujos():
    try:
        from geoalchemy2.functions import ST_AsGeoJSON
        
        imagenes = ImagenDibujada.query.filter_by(
            id_usuario=current_user.id_usuario
        ).order_by(ImagenDibujada.fecha_creacion.desc()).all()
        
        dibujos = []
        for img in imagenes:
            geom_geojson = db.session.scalar(ST_AsGeoJSON(img.geom))
            
            dibujos.append({
                'id': img.id,
                'geojson': geom_geojson,
                'tipo': img.tipo_geometria,
                'ndvi_max': float(img.ndvi_max) if img.ndvi_max else None,
                'ndvi_min': float(img.ndvi_min) if img.ndvi_min else None,
                'ndvi_medio': float(img.ndvi_medio) if img.ndvi_medio else None,
                'area_m2': float(img.area_m2) if img.area_m2 else None,
                'fecha': img.fecha_creacion.isoformat()
            })
        
        return jsonify({'dibujos': dibujos}), 200
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/eliminar-dibujo/<int:dibujo_id>', methods=['DELETE'])
@login_required
def eliminar_dibujo(dibujo_id):
    try:
        dibujo = ImagenDibujada.query.filter_by(
            id=dibujo_id,
            id_usuario=current_user.id_usuario
        ).first()

        
        if not dibujo:
            return jsonify({'error': 'No encontrado'}), 404
        
        db.session.delete(dibujo)
        db.session.commit()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    




BASE_DIR = Path(__file__).resolve().parents[3]
# *** esto del env solo, quitar lo de x defecto supongo
NDVI_DIR = Path(
    os.getenv(
        "NDVI_DIR",
        str(BASE_DIR / "data" / "raw" / "ndvi_composite")
    )
)
@api_bp.route("/ndvi/<path:filename>")
def serve_ndvi(filename):
    return send_from_directory(NDVI_DIR, filename)




# COMPARAR
@api_bp.route('/comparar-ndvi', methods=['POST'])
@login_required
def comparar_ndvi():
    """
    Endpoint para obtener datos de NDVI de múltiples recintos para comparación
    """
    try:
        data = request.get_json()
        recintos_ids = data.get('recintos', [])
        
        if not recintos_ids:
            return jsonify({
                'success': False,
                'mensaje': 'No se proporcionaron recintos para comparar'
            }), 400
        
        if len(recintos_ids) > 10:
            return jsonify({
                'success': False,
                'mensaje': 'No se pueden comparar más de 10 recintos'
            }), 400

        
        # Verificar que el usuario tiene acceso a todos los recintos
        recintos = Recinto.query.filter(
            Recinto.id_recinto.in_(recintos_ids),
            Recinto.id_propietario == current_user.id_usuario
        ).all()
        
        if len(recintos) != len(recintos_ids):
            return jsonify({
                'success': False,
                'mensaje': 'Uno o más recintos no existen o no tienes acceso a ellos'
            }), 403
        
        # Obtener datos de NDVI para cada recinto
        resultado = {}

        for recinto_id in recintos_ids:
            # Consultar los índices NDVI del recinto ordenados por fecha
            indices = IndicesRaster.query.filter(
                IndicesRaster.id_recinto == recinto_id,
                IndicesRaster.tipo_indice == 'NDVI',
                IndicesRaster.fecha_ndvi.isnot(None)
            ).order_by(IndicesRaster.fecha_ndvi.asc()).all()
            
            if indices:
                mediciones = []
                for indice in indices:
                    # Extraer valores y convertir a float
                    valor_medio = float(indice.valor_medio) if indice.valor_medio else 0
                    valor_min = float(indice.valor_min) if indice.valor_min else 0
                    valor_max = float(indice.valor_max) if indice.valor_max else 0
                    
                    # VALIDACIÓN: Corregir datos inconsistentes
                    # Si el máximo es menor que el medio o el mínimo, hay error en BD
                    if valor_max < valor_medio:
                        print(f"⚠️ WARNING: Recinto {recinto_id}, fecha {indice.fecha_ndvi}: "
                            f"valor_max ({valor_max}) < valor_medio ({valor_medio})")
                        valor_max = valor_medio  # Corregir usando el medio como máximo
                    
                    if valor_min > valor_medio:
                        print(f"⚠️ WARNING: Recinto {recinto_id}, fecha {indice.fecha_ndvi}: "
                            f"valor_min ({valor_min}) > valor_medio ({valor_medio})")
                        valor_min = valor_medio  # Corregir usando el medio como mínimo
                    
                    # Asegurar orden lógico: min <= medio <= max
                    if valor_min > valor_max:
                        valor_min, valor_max = valor_max, valor_min
                    
                    mediciones.append({
                        'fecha_ndvi': indice.fecha_ndvi.strftime('%Y-%m-%d') if indice.fecha_ndvi else None,
                        'valor_medio': valor_medio,
                        'valor_min': valor_min,
                        'valor_max': valor_max,
                        'desviacion_std': float(indice.desviacion_std) if indice.desviacion_std else 0
                    })
                
                resultado[str(recinto_id)] = {'mediciones': mediciones}
            else:
                resultado[str(recinto_id)] = {'mediciones': []}
        return jsonify({
            'success': True,
            'datos': resultado
        }), 200
        
    except Exception as e:
        import traceback
        print(f"Error en comparar_ndvi: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'mensaje': f'Error al obtener los datos: {str(e)}'
        }), 500
    


@api_bp.route('/comparativa-campanias/<int:id_recinto>', methods=['GET'])
@login_required
def comparativa_campanias(id_recinto):
    """
    Obtiene datos NDVI de 3 campañas para un recinto específico
    Campañas van de septiembre a septiembre
    """
    try:
        # Año actual
        current_year = datetime.now().year
        
        # Definir rangos de campañas (septiembre a septiembre)
        campanias = [
            {
                'nombre': f'{current_year - 1}/{current_year}',  # 2025/2026
                'inicio': datetime(current_year - 1, 9, 1),
                'fin': datetime(current_year, 8, 31, 23, 59, 59),
                'year': current_year
            },
            {
                'nombre': f'{current_year - 2}/{current_year - 1}',  # 2024/2025
                'inicio': datetime(current_year - 2, 9, 1),
                'fin': datetime(current_year - 1, 8, 31, 23, 59, 59),
                'year': current_year - 1
            },
            {
                'nombre': f'{current_year - 3}/{current_year - 2}',  # 2023/2024
                'inicio': datetime(current_year - 3, 9, 1),
                'fin': datetime(current_year - 2, 8, 31, 23, 59, 59),
                'year': current_year - 2
            }
        ]
        
        resultado = []
        
        for campania in campanias:
            # Consultar datos NDVI para este recinto en el rango de fechas
            indices = IndicesRaster.query.filter(
                and_(
                    IndicesRaster.id_recinto == id_recinto,
                    IndicesRaster.tipo_indice == 'NDVI',
                    IndicesRaster.fecha_ndvi >= campania['inicio'],
                    IndicesRaster.fecha_ndvi <= campania['fin']
                )
            ).order_by(IndicesRaster.fecha_ndvi.asc()).all()
            
            # Formatear datos para la gráfica
            datos_campania = {
                'nombre': campania['nombre'],
                'year': campania['year'],
                'datos': [
                    {
                        'fecha': indice.fecha_ndvi.strftime('%Y-%m-%d'),
                        'valor_medio': float(indice.valor_medio) if indice.valor_medio else 0,
                        'valor_min': float(indice.valor_min) if indice.valor_min else 0,
                        'valor_max': float(indice.valor_max) if indice.valor_max else 0
                    }
                    for indice in indices
                ]
            }
            
            resultado.append(datos_campania)
        
        return jsonify({
            'success': True,
            'campanias': resultado
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    


@api_bp.route('/buscar-imagen-ndvi/<int:recinto_id>', methods=['GET'])
@login_required
def buscar_imagen_ndvi(recinto_id):
    """
    Busca la imagen NDVI más cercana a una fecha objetivo dentro de un rango de campaña
    """
    try:
        fecha_str = request.args.get('fecha')
        margen = 10  # Días antes y después de la fecha objetivo
        campania_inicio_str = request.args.get('campania_inicio')
        campania_fin_str = request.args.get('campania_fin')
        
        if not fecha_str:
            return jsonify({
                'success': False,
                'error': 'Falta el parámetro fecha'
            }), 400
        
        # Convertir fecha objetivo a datetime para PostgreSQL
        fecha_objetivo = datetime.strptime(fecha_str, '%Y-%m-%d')
        
        # Calcular rango de búsqueda
        fecha_min = fecha_objetivo - timedelta(days=margen)
        fecha_max = fecha_objetivo + timedelta(days=margen)
        
        # Si se proporcionan fechas de campaña, restringir a ese rango
        if campania_inicio_str and campania_fin_str:
            campania_inicio = datetime.strptime(campania_inicio_str, '%Y-%m-%d')
            campania_fin = datetime.strptime(campania_fin_str, '%Y-%m-%d')
            
            # El rango de búsqueda debe estar dentro de la campaña
            fecha_min = max(fecha_min, campania_inicio)
            fecha_max = min(fecha_max, campania_fin)
        
        # Buscar la imagen más cercana - CORREGIDO para PostgreSQL
        # Usamos cast y la diferencia de fechas directamente
        imagen = IndicesRaster.query.filter(
            and_(
                IndicesRaster.id_recinto == recinto_id,
                IndicesRaster.tipo_indice == 'NDVI',
                IndicesRaster.fecha_ndvi >= fecha_min.date(),
                IndicesRaster.fecha_ndvi <= fecha_max.date(),
                IndicesRaster.ruta_ndvi.isnot(None)
            )
        ).order_by(
            func.abs(
                func.cast(IndicesRaster.fecha_ndvi, db.Date) - func.cast(fecha_objetivo.date(), db.Date)
            )
        ).first()
        
        if not imagen:
            return jsonify({
                'success': False,
                'error': f'No se encontró imagen NDVI en el rango especificado'
            }), 404
        
        return jsonify({
            'success': True,
            'imagen': {
                'id': imagen.id_indice,
                'fecha_ndvi': imagen.fecha_ndvi.strftime('%Y-%m-%d'),
                'ruta_ndvi': imagen.ruta_ndvi,
                'valor_medio': float(imagen.valor_medio) if imagen.valor_medio else 0.0,
                'valor_min': float(imagen.valor_min) if imagen.valor_min else 0.0,
                'valor_max': float(imagen.valor_max) if imagen.valor_max else 0.0
            }
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}'
        }), 400
    except Exception as e:
        print(f"Error en buscar_imagen_ndvi: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    

@api_bp.route('/estaciones')
@login_required
def api_estaciones():
    estaciones = Estacion.query.all()
    features = []
    for e in estaciones:
        if e.geom:
            punto = to_shape(e.geom)
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [punto.x, punto.y]
                },
                "properties": {
                    "id": e.id,              # ← PK interna, nueva
                    "idestacion": e.idestacion,
                    "nombre": e.nombre,
                    "codigo": e.codigo,
                    "altitud": e.altitud,
                    "idprovincia": e.idprovincia
                }
            })
    return jsonify({"type": "FeatureCollection", "features": features})


@api_bp.route('/estaciones/<int:estacion_id>/fechas')
@login_required
def api_estacion_fechas(estacion_id):
    fechas = db.session.query(DatosDiarios.fecha)\
        .filter(
            DatosDiarios.estacion_id == estacion_id,
            DatosDiarios.fecha < date.today()
        )\
        .order_by(DatosDiarios.fecha.desc())\
        .all()
    return jsonify([f[0].isoformat() for f in fechas])


@api_bp.route('/estaciones/<int:estacion_id>/datos/<fecha>')
@login_required
def api_estacion_datos(estacion_id, fecha):
    try:
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Fecha inválida"}), 400

    d = DatosDiarios.query.filter_by(estacion_id=estacion_id, fecha=fecha_dt).first()
    if not d:
        return jsonify({"error": "Sin datos"}), 404

    return jsonify({
        "fecha":           d.fecha.isoformat(),
        "tempmax":         d.tempmax,
        "tempmin":         d.tempmin,
        "tempmedia":       d.tempmedia,
        "tempd":           d.tempd,
        "hormintempmax":   d.hormintempmax,
        "hormintempmin":   d.hormintempmin,
        "humedadmax":      d.humedadmax,
        "humedadmin":      d.humedadmin,
        "humedadmedia":    d.humedadmedia,
        "humedadd":        d.humedadd,
        "horminhummax":    d.horminhummax,
        "horminhummin":    d.horminhummin,
        "velviento":       d.velviento,
        "velvientomax":    d.velvientomax,
        "dirviento":       d.dirviento,
        "dirvientovelmax": d.dirvientovelmax,
        "recorrido":       d.recorrido,
        "horminvelmax":    d.horminvelmax,
        "vd":              d.vd,
        "vn":              d.vn,
        "precipitacion":   d.precipitacion,
        "radiacion":       d.radiacion,
        "rmax":            d.rmax,
        "rn":              d.rn,
        "n":               d.n,
        "etbc":            d.etbc,
        "etharg":          d.etharg,
        "etpmon":          d.etpmon,
        "etrad":           d.etrad,
        "pebc":            d.pebc,
        "peharg":          d.peharg,
        "pepmon":          d.pepmon,
        "perad":           d.perad,
    })




@api_bp.route('/etp/fechas')
@login_required
def etp_fechas():
    geoserver_url = current_app.config["GEOSERVER_WMS_URL"]
    try:
        r = requests.get(geoserver_url, params={
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetCapabilities"
        }, timeout=10)
        root = ET.fromstring(r.content)

        fechas = []
        for layer in root.iter("Layer"):
            name = layer.find("Name")
            if name is not None and "mapascontinuos" in name.text:
                for extent in layer.iter("Extent"):
                    if extent.get("name") == "time" and extent.text:  # ← añadir "and extent.text"
                        fechas = [
                            f.strip()[:10]
                            for f in extent.text.strip().split(",")
                            if f.strip()
                        ]
                        break
                for dim in layer.iter("Dimension"):
                    if dim.get("name") == "time" and dim.text and not fechas:  # ← igual aquí
                        fechas = [
                            f.strip()[:10]
                            for f in dim.text.strip().split(",")
                            if f.strip()
                        ]
                        break

        return jsonify({"ok": True, "fechas": sorted(set(fechas))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    


import json as _json


def _recinto_propio_o_404(recinto_id: int):
    """Devuelve el Recinto si pertenece al usuario actual, o None."""
    return Recinto.query.filter_by(
        id_recinto=recinto_id,
        id_propietario=current_user.id_usuario
    ).first()


@api_bp.get("/mis-recinto/<int:recinto_id>/subparcelas")
@login_required
def api_listar_subparcelas(recinto_id: int):
    try:
        recinto = _recinto_propio_o_404(recinto_id)
        if not recinto:
            return jsonify({"error": "Recinto no encontrado"}), 404

        rows = db.session.execute(
            text("""
                SELECT
                    s.id_subparcela,
                    s.id_recinto,
                    s.nombre,
                    s.superficie_ha,
                    s.cod_producto,
                    pf.descripcion  AS cultivo_descripcion,
                    ST_AsGeoJSON(s.geom) AS geom_json
                FROM public.subparcelas s
                LEFT JOIN public.productos_fega pf ON pf.codigo = s.cod_producto
                WHERE s.id_recinto = :rid
                ORDER BY s.id_subparcela
            """),
            {"rid": recinto_id}
        ).mappings().all()

        out = []
        for r in rows:
            d = {k: _jsonable(v) for k, v in dict(r).items()}
            d["geom"] = _json.loads(d.pop("geom_json"))
            out.append(d)

        return jsonify(out)
    except Exception:
        current_app.logger.exception("Error en GET /api/mis-recinto/<id>/subparcelas")
        return jsonify({"error": "Error interno en /api/mis-recinto/<id>/subparcelas"}), 500


@api_bp.post("/mis-recinto/<int:recinto_id>/subparcelas")
@login_required
def api_crear_subparcelas(recinto_id: int):
    """
    Recibe un FeatureCollection con los polígonos dibujados por el usuario
    y REEMPLAZA todas las subparcelas existentes del recinto por las nuevas
    (operación atómica: borra todo y reinserda).

    Body esperado:
    {
      "features": [
        { "type": "Feature",
          "geometry": { "type": "Polygon", "coordinates": [...] },
          "properties": { "nombre": "Subparcela 1" } },
        ...
      ]
    }
    """
    data = request.get_json(silent=True) or {}
    features = data.get("features") or []

    if not isinstance(features, list) or len(features) == 0:
        return jsonify({"ok": False, "error": "No se han recibido subparcelas"}), 400

    try:
        recinto = _recinto_propio_o_404(recinto_id)
        if not recinto:
            return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404

        validadas = []

        for i, feat in enumerate(features, start=1):
            geometry = feat.get("geometry") if isinstance(feat, dict) else None
            if not geometry:
                return jsonify({"ok": False, "error": f"Subparcela {i}: geometría ausente"}), 400

            try:
                geom_shapely = shape(geometry)
            except Exception:
                return jsonify({"ok": False, "error": f"Subparcela {i}: geometría inválida"}), 400

            if geom_shapely.is_empty or not geom_shapely.is_valid:
                # Intentar reparar geometría inválida (artefactos de turf.js)
                geom_shapely = geom_shapely.buffer(0)
                if geom_shapely.is_empty or not geom_shapely.is_valid:
                    return jsonify({"ok": False, "error": f"Subparcela {i}: polígono inválido"}), 400

            # Si llegó un MultiPolygon (turf edge-case), usar la parte más grande
            if geom_shapely.geom_type == "MultiPolygon":
                from shapely.geometry import mapping as _shp_mapping
                geom_shapely = max(geom_shapely.geoms, key=lambda g: g.area)
                geometry = _shp_mapping(geom_shapely)

            if geom_shapely.geom_type != "Polygon":
                return jsonify({"ok": False, "error": f"Subparcela {i}: debe ser un polígono simple"}), 400

            # Verificar que está dentro del recinto.
            # Tolerancia ~10 m para absorber artefactos de corte turf.js.
            # Se expande el RECINTO (no la subparcela) para que bordes compartidos pasen.
            row = db.session.execute(
                text("""
                    SELECT
                        ST_CoveredBy(
                            ST_GeomFromGeoJSON(:geom),
                            ST_Buffer(r.geom, 0.0001)
                        ) AS dentro,
                        ST_Area(geography(ST_GeomFromGeoJSON(:geom))) / 10000.0 AS ha
                    FROM public.recintos r
                    WHERE r.id_recinto = :rid
                """),
                {"geom": _json.dumps(geometry), "rid": recinto_id}
            ).mappings().first()

            if not row or not row["dentro"]:
                return jsonify({"ok": False, "error": f"Subparcela {i} se sale de los límites del recinto"}), 400

            # Verificar que no se solapa con las ya validadas en esta petición
            for otra in validadas:
                if geom_shapely.intersection(otra["geom_shapely"]).area > 1e-10:
                    return jsonify({"ok": False, "error": "Hay subparcelas que se solapan entre sí"}), 400

            nombre = None
            if isinstance(feat.get("properties"), dict):
                nombre = (feat["properties"].get("nombre") or "").strip() or None

            validadas.append({
                "geom_shapely": geom_shapely,
                "nombre": nombre or f"Subparcela {i}",
                "superficie_ha": round(float(row["ha"]), 2),
            })

        # Operación atómica: borrar las existentes e insertar las nuevas
        db.session.execute(
            text("DELETE FROM public.subparcelas WHERE id_recinto = :rid"),
            {"rid": recinto_id}
        )

        creadas = []
        for v in validadas:
            row = db.session.execute(
                text("""
                    INSERT INTO public.subparcelas (id_recinto, nombre, geom, superficie_ha)
                    VALUES (:rid, :nombre, ST_SetSRID(ST_GeomFromText(:wkt), 4326), :ha)
                    RETURNING id_subparcela, id_recinto, nombre, superficie_ha
                """),
                {
                    "rid": recinto_id,
                    "nombre": v["nombre"],
                    "wkt": v["geom_shapely"].wkt,
                    "ha": v["superficie_ha"],
                }
            ).mappings().first()
            creadas.append({k: _jsonable(val) for k, val in dict(row).items()})

        db.session.commit()
        return jsonify({"ok": True, "subparcelas": creadas}), 201

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error en POST /api/mis-recinto/<id>/subparcelas")
        return jsonify({"ok": False, "error": "Error interno al guardar la división"}), 500


@api_bp.delete("/mis-recinto/<int:recinto_id>/subparcelas")
@login_required
def api_borrar_subparcelas(recinto_id: int):
    """Deshace la división: elimina todas las subparcelas del recinto."""
    try:
        recinto = _recinto_propio_o_404(recinto_id)
        if not recinto:
            return jsonify({"ok": False, "error": "Recinto no encontrado"}), 404

        db.session.execute(
            text("DELETE FROM public.subparcelas WHERE id_recinto = :rid"),
            {"rid": recinto_id}
        )
        db.session.commit()
        return jsonify({"ok": True})
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error en DELETE /api/mis-recinto/<id>/subparcelas")
        return jsonify({"ok": False, "error": "Error interno al deshacer la división"}), 500


@api_bp.patch("/subparcelas/<int:id_subparcela>/cultivo")
@login_required
def api_patch_cultivo_subparcela(id_subparcela: int):
    """Asigna (o quita con null) el cultivo de una subparcela."""
    data = request.get_json(silent=True) or {}
    cod_producto = data.get("cod_producto", None)

    try:
        # Verificar propiedad vía join con recintos
        row = db.session.execute(
            text("""
                SELECT s.id_subparcela
                FROM public.subparcelas s
                JOIN public.recintos r ON r.id_recinto = s.id_recinto
                WHERE s.id_subparcela = :sid AND r.id_propietario = :uid
            """),
            {"sid": id_subparcela, "uid": current_user.id_usuario}
        ).first()

        if not row:
            return jsonify({"ok": False, "error": "Subparcela no encontrada"}), 404

        if cod_producto is not None:
            existe = db.session.execute(
                text("SELECT 1 FROM public.productos_fega WHERE codigo = :cp"),
                {"cp": cod_producto}
            ).first()
            if not existe:
                return jsonify({"ok": False, "error": "Código de producto no válido"}), 400

        db.session.execute(
            text("UPDATE public.subparcelas SET cod_producto = :cp WHERE id_subparcela = :sid"),
            {"cp": cod_producto, "sid": id_subparcela}
        )
        db.session.commit()
        return jsonify({"ok": True, "cod_producto": cod_producto})

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error en PATCH /api/subparcelas/<id>/cultivo")
        return jsonify({"ok": False, "error": "Error interno al asignar el cultivo"}), 500
    




EXTENSIONES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'webp'}
THUMB_SIZE = (400, 300)
 
 
def _ext_ok(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in EXTENSIONES_PERMITIDAS
 
 
def _slug(valor):
    """Segmento de ruta seguro a partir de un valor numérico o texto."""
    texto = str(valor or 'sin-dato').strip().lower().replace(' ', '-')
    return ''.join(c for c in texto if c.isalnum() or c in ('-', '_')) or 'sin-dato'
 
 
@api_bp.route('/contadores/recinto-por-gps', methods=['GET'])
@login_required
def contador_recinto_por_gps():
    """Devuelve el recinto del usuario que contiene el punto GPS."""
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    if lat is None or lon is None:
        return jsonify({'ok': False, 'error': 'Faltan coordenadas GPS'}), 400

    try:
        row = db.session.execute(
            text("""
                SELECT
                    r.id_recinto,
                    r.nombre,
                    r.poligono,
                    r.parcela,
                    r.provincia,
                    r.municipio
                FROM public.recintos r
                WHERE r.id_propietario = :uid
                  AND r.geom IS NOT NULL
                  AND ST_Intersects(
                        r.geom,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
                      )
                ORDER BY ST_Area(r.geom::geography) ASC
                LIMIT 1
            """),
            {'uid': current_user.id_usuario, 'lon': lon, 'lat': lat},
        ).mappings().first()
    except Exception:
        current_app.logger.exception('Error en /api/contadores/recinto-por-gps')
        return jsonify({'ok': False, 'error': 'Error al buscar recinto'}), 500

    if not row:
        return jsonify({'ok': True, 'found': False})

    return jsonify({
        'ok': True,
        'found': True,
        'recinto': {
            'id_recinto': row['id_recinto'],
            'nombre': row['nombre'],
            'poligono': row['poligono'],
            'parcela': row['parcela'],
        },
    })


@api_bp.route('/contadores/subir', methods=['POST'])
@login_required
def subir_contador():
    try:
        if 'imagen' not in request.files:
            return jsonify({'error': 'No se ha enviado ninguna imagen'}), 400
 
        archivo = request.files['imagen']
        if not archivo.filename or not _ext_ok(archivo.filename):
            return jsonify({'error': 'Formato de imagen no válido'}), 400
 
        recinto_id  = request.form.get('recinto_id')
        titulo      = (request.form.get('titulo')      or '').strip()
        lectura     = (request.form.get('lectura')     or '').strip()
        descripcion = (request.form.get('descripcion') or '').strip()
        lat         = request.form.get('lat')
        lon         = request.form.get('lon')
 
        if not recinto_id or not titulo:
            return jsonify({'error': 'Faltan campos obligatorios'}), 400
 
        geom_wkt = f"POINT({lon} {lat})" if lat and lon else None

        recinto = Recinto.query.filter_by(
            id_recinto=recinto_id,
            id_propietario=current_user.id_usuario
        ).first()
 
        if not recinto:
            return jsonify({'error': 'Recinto no encontrado o sin permisos'}), 404
 
        # ── Ruta de carpeta: uploads/contadores/<usuario>/<poligono>/<parcela> ──
        carpeta_rel = os.path.join(
            'contadores',
            _slug(current_user.username),
            _slug(recinto.poligono),
            _slug(recinto.parcela),
        )
        carpeta_abs = os.path.join(current_app.static_folder, 'uploads', carpeta_rel)
        os.makedirs(carpeta_abs, exist_ok=True)
 
        # ── Guardar imagen + thumbnail ───────────────────────────────
        ext         = archivo.filename.rsplit('.', 1)[1].lower()
        lectura_slug = _slug(lectura) if lectura else 'sin-lectura'
        nombre_base  = f"{lectura_slug}_{uuid.uuid4().hex[:6]}"
        nom_orig    = f"{nombre_base}.{ext}"
        nom_thumb   = f"{nombre_base}_thumb.{ext}"
        ruta_orig   = os.path.join(carpeta_abs, nom_orig)
        ruta_thumb  = os.path.join(carpeta_abs, nom_thumb)
 
        archivo.save(ruta_orig)
 
        try:
            with Image.open(ruta_orig) as img:
                img = img.convert('RGB')
                img.thumbnail(THUMB_SIZE)
                img.save(ruta_thumb, quality=85, optimize=True)
        except Exception as e:
            current_app.logger.warning(f'Thumbnail fallido: {e}')
            ruta_thumb = ruta_orig
            nom_thumb  = nom_orig
 
        url_orig  = f"/static/uploads/{carpeta_rel}/{nom_orig}".replace('\\', '/')
        url_thumb = f"/static/uploads/{carpeta_rel}/{nom_thumb}".replace('\\', '/')
 
        # ── Registro en BD ───────────────────────────────────────────
        nuevo = Contador(
            id_recinto     = recinto.id_recinto,
            id_usuario     = current_user.id_usuario,
            titulo         = titulo,
            lectura        = lectura,
            descripcion    = descripcion,
            ruta_imagen    = url_orig,
            ruta_thumb     = url_thumb,
            geom           = geom_wkt or "POINT(0 0)",
            poligono       = recinto.poligono,
            parcela        = recinto.parcela,
            fecha_creacion = datetime.now(timezone.utc),
        )
        db.session.add(nuevo)
        db.session.commit()
 
        return jsonify({
            'id':              nuevo.id,
            'titulo':          nuevo.titulo,
            'lectura':         nuevo.lectura,
            'thumb':           url_thumb,
            'imagen':          url_orig,
            'tiene_ubicacion': True,
        }), 201
 
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error /api/contadores/subir: {e}')
        return jsonify({'error': 'Error interno al guardar la lectura'}), 500