"""
routes.py
---------
Rutas REST para exponer capas SIGPAC como GeoJSON y gestionar
solicitudes de recintos.
"""

from __future__ import annotations
from fileinput import filename

from flask import jsonify, request, send_from_directory
from pathlib import Path
from flask_login import login_required, current_user
import requests
from sqlalchemy import text
import matplotlib
matplotlib.use('Agg') # Vital para que no intente abrir ventanas en el servidor


from datetime import date, datetime, timezone
from shapely.geometry import shape, mapping
from rasterio.mask import mask as rio_mask
from decimal import Decimal
from geoalchemy2.shape import from_shape
import os

import numpy as np
import rasterio
from rasterio.warp import transform_geom

from .. import db
from ..models import ImagenDibujada, IndicesRaster, Recinto, Solicitudrecinto, Variedad
from webapp.dashboard.utils_dashboard import municipios_finder

from . import api_bp
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

    # Normaliza (por si llega "true"/"false")
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
    """Devuelve la vista inicial recomendada del visor para el usuario actual.

    - Solo para usuarios normales.
    - Para admins/superadmins devuelve nulls (no altera el comportamiento actual).
    """
    if getattr(current_user, "rol", None) in {"admin", "superadmin"}:
        return jsonify({"municipio_top": None, "center": None, "bbox": None})

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

"""
CORRECCIÓN PARA EL ENDPOINT /api/popup/suelos

Reemplaza el endpoint popup_suelos() en tu archivo routes.py (líneas 408-537)
con esta versión corregida.
"""

@api_bp.route('/popup/suelos')
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
        
        # URL de GeoServer
        geoserver_url = "http://100.102.237.86:8080/geoserver/wms"
        
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
        response = requests.get(geoserver_url, params=params, timeout=10)
        
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
        
        # 🔧 Log para ver qué campos vienen realmente de GeoServer
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
        
        # 🎯 MAPEO EXACTO según los nombres de columnas de tu base de datos
        field_mapping = {
            # Campos principales
            'id_muestra': get_value('ID_MUESTRA', 'ID_Muestra', 'id_muestra'),
            'origen': get_value('Origen', 'origen'),
            
            # ✅ CORRECCIÓN CRÍTICA: 'Campaña' con tilde (nombre exacto de la columna)
            'campana': get_value('Campaña', 'Campanya', 'campana'),
            
            'laboratori': get_value('Laboratori', 'laboratori'),
            
            # pH y CE
            'ph': get_value('pH', 'ph', 'PH'),
            
            # ✅ CORRECCIÓN: 'AcidezBasi' sin guión bajo
            'acidez_basi': get_value('AcidezBasi', 'Acidez_Basi', 'acidez_basi'),
            
            'conductivi': get_value('Conductivi', 'conductividad', 'CE'),
            
            # Materia orgánica
            'mo_porc': get_value('MO_Porc', 'mo_porc', 'MO_%'),
            'materia_org': get_value('MateriaOrg', 'Materia_Org', 'materia_org'),
            
            # Textura
            'arena_porc': get_value('Arena_Porc', 'arena_porc', 'Arena_%'),
            'limo_porc': get_value('Limo_Porc', 'limo_porc', 'Limo_%'),
            
            # ✅ CORRECCIÓN: 'Arcilla_Po' (truncado, no 'Arcilla_Porc')
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
            
            # Coordenadas - ✅ CORRECCIÓN: 'COOR_X_ETR' todo en mayúsculas
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

# ---------------------------
# Catálogos para el frontend
# ---------------------------

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

# ---------------------------
# Catálogos Operaciones (SIEX)
# ---------------------------

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


# ---------------------------
# Cultivos por recinto
# ---------------------------

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

# ---------------------------
# Operaciones por recinto
# ---------------------------

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
            return jsonify({'error': 'No se recibieron dibujos'}), 400
        
        # Límite de dibujos por usuario
        MAX_DIBUJOS = 10
        dibujos_existentes = ImagenDibujada.query.filter_by(id_usuario=current_user.id_usuario).count()
        
        if dibujos_existentes >= MAX_DIBUJOS:
            return jsonify({'error': f'Has alcanzado el límite de {MAX_DIBUJOS} dibujos permitidos'}), 400
        
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
            'message': f'Se guardaron {guardados} dibujos correctamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error al guardar dibujos: {str(e)}")
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

NDVI_DIR = Path(
    os.getenv(
        "NDVI_DIR",
        str(BASE_DIR / "data" / "raw" / "ndvi_composite")
    )
)
@api_bp.route("/ndvi/<path:filename>")
def serve_ndvi(filename):
    return send_from_directory(NDVI_DIR, filename)