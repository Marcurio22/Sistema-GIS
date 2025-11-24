from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from . import dashboard_bp
from datetime import datetime
import logging
from .config_clima import estados_cielo, iconos_bootstrap, colores_iconos
import requests


logger = logging.getLogger('app.dashboard')
logger.setLevel(logging.INFO)

def obtener_datos_aemet():
    """Obtiene los datos meteorológicos de AEMET para Burgos"""
    try:
        AEMET_API_KEY = current_app.config.get('AEMET_API_KEY', 'tu_api_key_aqui')
        CODIGO_MUNICIPIO = '09059'
        
        url_solicitud = f'https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/horaria/{CODIGO_MUNICIPIO}?api_key={AEMET_API_KEY}'
        response1 = requests.get(url_solicitud, timeout=5)
        data1 = response1.json()
        
        if data1.get('estado') != 200:
            logger.warning(f"AEMET API devolvió estado {data1.get('estado')}: {data1.get('descripcion')}")
            return None
        
        response2 = requests.get(data1['datos'], timeout=5)
        datos = response2.json()
        
        provincia = datos[0].get('provincia', '')
        municipio = datos[0].get('nombre', '')
        prediccion = datos[0]['prediccion']['dia'][0]
        hora_actual = datetime.now().hour

        def obtener_valor_periodo(lista, hora):
            for item in lista:
                if int(item['periodo']) == hora:
                    return item['value']
            return None

        temp_actual = obtener_valor_periodo(prediccion.get('temperatura', []), hora_actual)
        estado_cielo_cod = obtener_valor_periodo(prediccion.get('estadoCielo', []), hora_actual)
        humedad = obtener_valor_periodo(prediccion.get('humedadRelativa', []), hora_actual)

        viento = None
        if prediccion.get('vientoAndRachaMax'):
            for v in prediccion['vientoAndRachaMax']:
                if int(v['periodo']) == hora_actual:
                    viento = v['velocidad'][0] if v.get('velocidad') else None
                    break

        def obtener_color_icono(codigo):
            return colores_iconos.get(codigo, 'text-primary')

        return {
            'provincia': provincia,
            'municipio': municipio,
            'temperatura': temp_actual,
            'descripcion': estados_cielo.get(estado_cielo_cod, 'Desconocido'),
            'icono': iconos_bootstrap.get(estado_cielo_cod, 'cloud'),
            'color_icono': obtener_color_icono(estado_cielo_cod),
            'humedad': humedad,
            'viento': viento,
        }

    except requests.exceptions.Timeout:
        logger.error("Timeout al conectar con AEMET API")
        return None
    except Exception as e:
        logger.error(f"Error obteniendo datos AEMET: {e}")
        return None

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    logger.info(
        f'Usuario {current_user.username} accedió al dashboard',
        extra={'tipo_operacion': 'ACCESO', 'modulo': 'DASHBOARD'}
    )
    
    # Obtener datos meteorológicos
    weather = obtener_datos_aemet()
    
    return render_template('dashboard.html', username=current_user.username, weather=weather)


@dashboard_bp.get("/visor")
@login_required
def visor():
    return render_template("visor.html")