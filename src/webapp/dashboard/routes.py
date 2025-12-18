from sqlalchemy import text
from webapp import db
from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from . import dashboard_bp
from datetime import datetime
import logging
from .utils_dashboard import obtener_datos_aemet, MunicipiosCodigosFinder
import requests
from ..models import Recinto
import os


logger = logging.getLogger('app.dashboard')
logger.setLevel(logging.INFO)


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    logger.info(
        f'Usuario {current_user.username} accedió al dashboard',
        extra={'tipo_operacion': 'ACCESO', 'modulo': 'DASHBOARD'}
    )
    # Obtener datos meteorológicos de AEMET
    weather = obtener_datos_aemet("34023")

    # URL widget AEMET
    municipios_codigos_finder = MunicipiosCodigosFinder()
    url_widget = municipios_codigos_finder.obtener_url_municipio_usuario(current_user.id_usuario)


    return render_template('dashboard.html', username=current_user.username, weather=weather, url_widget=url_widget)


@dashboard_bp.route("/visor")
@login_required
def visor():
    """
    Vista del visor SIG. Calcula la bbox de la ROI a partir de sigpac.recintos
    y la pasa al template como roi_bbox = [minx, miny, maxx, maxy].
    
    Si se recibe recinto_id como parámetro, también envía los datos de ese recinto específico.
    """
    from flask import request
    
    # Obtener el ID del recinto si viene como parámetro
    recinto_id = request.args.get('recinto_id', type=int)
    recinto_data = None
    
    # Si hay un recinto específico, obtener sus datos y geometría
    if recinto_id:
        
        
        # Obtener el recinto del ORM
        recinto = Recinto.query.get(recinto_id)
        
        if recinto:
            # Construir la consulta SQL usando los campos SIGPAC como filtro
            # La tabla sigpac.recintos probablemente usa provincia, municipio, poligono, parcela, recinto como identificadores
            sql_recinto = text("""
                SELECT
                    ST_XMin(geometry) AS minx,
                    ST_YMin(geometry) AS miny,
                    ST_XMax(geometry) AS maxx,
                    ST_YMax(geometry) AS maxy,
                    ST_AsGeoJSON(geometry) AS geojson
                FROM sigpac.recintos
                WHERE provincia = :provincia
                  AND municipio = :municipio
                  AND poligono = :poligono
                  AND parcela = :parcela
                  AND recinto = :recinto
            """)
            
            geom_row = db.session.execute(sql_recinto, {
                'provincia': recinto.provincia,
                'municipio': recinto.municipio,
                'poligono': recinto.poligono,
                'parcela': recinto.parcela,
                'recinto': recinto.recinto
            }).fetchone()
            
            if geom_row:
                # Obtener el propietario del ORM
                propietario = 'N/A'
                if hasattr(recinto, 'id_propietario') and recinto.id_propietario:
                    if recinto.propietario:
                        propietario = recinto.propietario.username
                
                recinto_data = {
                    'id': recinto_id,  # Usamos el id del modelo ORM
                    'provincia': recinto.provincia,
                    'municipio': recinto.municipio,
                    'poligono': recinto.poligono,
                    'parcela': recinto.parcela,
                    'recinto': recinto.recinto,
                    'nombre': recinto.nombre if recinto.nombre else f'Recinto {recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}-{recinto.recinto}',
                    'superficie_ha': float(recinto.superficie_ha) if recinto.superficie_ha else 0,
                    'propietario': propietario,
                    'bbox': [geom_row.minx, geom_row.miny, geom_row.maxx, geom_row.maxy],
                    'geojson': geom_row.geojson
                }
    
    # Calcular bbox general (para vista inicial si no hay recinto específico)
    sql = text("""
        SELECT
            ST_XMin(extent) AS minx,
            ST_YMin(extent) AS miny,
            ST_XMax(extent) AS maxx,
            ST_YMax(extent) AS maxy
        FROM (
            SELECT ST_Extent(geometry) AS extent
            FROM sigpac.recintos
        ) sub;
    """)

    row = db.session.execute(sql).fetchone()

    if row and all(v is not None for v in row):
        roi_bbox = [row.minx, row.miny, row.maxx, row.maxy]
    else:
        # Fallback por si la consulta no devuelve nada
        roi_bbox = [-4.6718708208, 41.7248613835,
                    -3.8314839480, 42.1274665349]

    # Para saber el codigo del municipio
    municipios_codigos_finder = MunicipiosCodigosFinder()
    codigo_municipio = municipios_codigos_finder.codigo_recintos(current_user.id_usuario)

    weather = obtener_datos_aemet(codigo_municipio)

    # --- Sentinel-2 RGB (mosaico reciente) ---
    s2_path = os.path.join(current_app.root_path, "static", "sentinel2", "s2_rgb_latest.png")
    sentinel2_version = int(os.path.getmtime(s2_path)) if os.path.exists(s2_path) else 0
    
    # --- NDVI (mosaico reciente) ---
    ndvi_path = os.path.join(current_app.root_path, "static", "ndvi", "ndvi_latest.png")
    ndvi_version = int(os.path.getmtime(ndvi_path)) if os.path.exists(ndvi_path) else 0
    
    # Pasar recinto_data al template
    return render_template("visor.html", 
                         roi_bbox=roi_bbox, 
                         weather=weather,
                         recinto_data=recinto_data,
                         sentinel2_version=sentinel2_version,
                         ndvi_version=ndvi_version)



@dashboard_bp.route('/recinto/<int:id_recinto>')
@login_required
def detalle_recinto(id_recinto):
    recinto = Recinto.query.get_or_404(id_recinto)
    return render_template('detalle_recinto.html', recinto=recinto)