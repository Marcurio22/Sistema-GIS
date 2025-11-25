from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from . import dashboard_bp
from datetime import datetime
import logging
from .config_clima import obtener_info_clima
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
            return None
        
        response2 = requests.get(data1['datos'], timeout=5)
        datos = response2.json()
        
        provincia = datos[0].get('provincia', '')
        municipio = datos[0].get('nombre', '')
        
        # Obtener la fecha actual en formato YYYY-MM-DD
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        hora_actual = datetime.now().hour
        
        # Buscar el día correcto por fecha
        prediccion = None
        for dia in datos[0]['prediccion']['dia']:
            # Extraer solo la parte de la fecha (YYYY-MM-DD) del formato ISO
            fecha_dia = dia.get('fecha', '')[:10]
            if fecha_dia == fecha_hoy:
                prediccion = dia
                break
        
        # Si no se encuentra el día actual, usar el primero disponible 
        if prediccion is None:
            prediccion = datos[0]['prediccion']['dia'][0]

        def obtener_valor_periodo(lista, hora):
            for item in lista:
                if int(item['periodo']) == hora:
                    return item
            return None

        temp_actual = obtener_valor_periodo(prediccion.get('temperatura', []), hora_actual)
        temp_valor = temp_actual['value'] if temp_actual else None
        
        # Obtener el estado del cielo completo
        estado_cielo = obtener_valor_periodo(prediccion.get('estadoCielo', []), hora_actual)
        
        if estado_cielo:
            codigo = estado_cielo.get('value', '')
            descripcion = estado_cielo.get('descripcion', 'Desconocido').strip()
            es_noche = 'n' in codigo  # Determinar si es de noche por el código
            
            print(f"Código: {codigo}, Descripción: {descripcion}, Es noche: {es_noche}")
            
            # Obtener icono y color según la descripción
            info_clima = obtener_info_clima(descripcion, es_noche)
        else:
            descripcion = 'Desconocido'
            info_clima = {'icono': 'cloud', 'color': 'text-primary'}
        
        humedad_obj = obtener_valor_periodo(prediccion.get('humedadRelativa', []), hora_actual)
        humedad = humedad_obj['value'] if humedad_obj else None

        viento = None
        if prediccion.get('vientoAndRachaMax'):
            for v in prediccion['vientoAndRachaMax']:
                if int(v['periodo']) == hora_actual:
                    viento = v['velocidad'][0] if v.get('velocidad') else None
                    break

        resultado = {
            'provincia': provincia,
            'municipio': municipio,
            'temperatura': temp_valor,
            'descripcion': descripcion,
            'icono': info_clima['icono'],
            'color_icono': info_clima['color'],
            'humedad': humedad,
            'viento': viento,
        }
        return resultado    

    except requests.exceptions.Timeout:
        return None
    except Exception as e:
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
    """
    Muestra el visor SIG.

    roi_bbox = (minx, miny, maxx, maxy) en WGS84
    Estos valores son los que obtuviste de tu ROI (QGIS):
    (-4.6718708207, 41.7248613835, -3.8314839479, 42.1274665349)
    """
    roi_bbox = (-4.6718708208, 41.7248613835, -3.8314839479, 42.1274665349)

    return render_template("visor.html", roi_bbox=roi_bbox)