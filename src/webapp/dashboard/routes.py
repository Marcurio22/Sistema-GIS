from sqlalchemy import text
from webapp import db
from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from . import dashboard_bp
from datetime import datetime
import logging
from .utils_dashboard import obtener_datos_aemet, MunicipiosCodigosFinder
import requests


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
    """
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

    # Para saber el codigo del municipio hay que ver el numero de parcelas que tiene el usuario en cada municipio y sacar el codigo del que mas parcelas tiene

    municipios_codigos_finder = MunicipiosCodigosFinder()
    codigo_municipio = municipios_codigos_finder.codigo_parcelas(current_user.id_usuario)


    # Sacar codigo municipio de las parcelas del usuario?



    weather = obtener_datos_aemet(codigo_municipio)
    # OJO: ahora pasamos roi_bbox (no roi_bounds)
    return render_template("visor.html", roi_bbox=roi_bbox,    weather=weather)

