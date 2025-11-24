from flask import render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from . import dashboard_bp
from datetime import datetime
import logging
import requests


logger = logging.getLogger('app.dashboard')
logger.setLevel(logging.INFO)

def obtener_datos_aemet():
    """Obtiene los datos meteorológicos de AEMET para Burgos"""
    try:
        # Configuración
        AEMET_API_KEY = current_app.config.get('AEMET_API_KEY', 'tu_api_key_aqui')
        CODIGO_MUNICIPIO = '09059'
        
        url_solicitud = f'https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/horaria/{CODIGO_MUNICIPIO}?api_key={AEMET_API_KEY}'

        response1 = requests.get(url_solicitud, timeout=5)
        data1 = response1.json()
        
        if data1.get('estado') == 200:
            url_datos = data1['datos']
            response2 = requests.get(url_datos, timeout=5)
            datos = response2.json()
            
            provincia = datos[0].get('provincia', '')
            municipio = datos[0].get('nombre', '')
            prediccion = datos[0]['prediccion']['dia'][0]
            
            hora_actual = datetime.now().hour

            # Función para obtener valor según periodo
            def obtener_valor_periodo(lista, hora):
                for item in lista:
                    if int(item['periodo']) == hora:
                        return item['value']
                return None

            temp_actual = obtener_valor_periodo(prediccion.get('temperatura', []), hora_actual)
            estado_cielo_cod = obtener_valor_periodo(prediccion.get('estadoCielo', []), hora_actual)
            humedad = obtener_valor_periodo(prediccion.get('humedadRelativa', []), hora_actual)


            # Probabilidad de precipitacion?
            # prob_prec = obtener_valor_periodo(prediccion.get('probPrecipitacion', []), hora_actual)


            
            viento = None
            if prediccion.get('vientoAndRachaMax'):
                for v in prediccion['vientoAndRachaMax']:
                    if int(v['periodo']) == hora_actual:
                        viento = v['velocidad'][0] if v.get('velocidad') else None
                        break
            
            estados_cielo = {
                '11': 'Despejado', '11n': 'Despejado',
                '12': 'Poco nuboso', '12n': 'Poco nuboso',
                '13': 'Intervalos nubosos', '13n': 'Intervalos nubosos',
                '14': 'Nuboso', '14n': 'Nuboso',
                '15': 'Muy nuboso', '15n': 'Muy nuboso',
                '16': 'Cubierto', '16n': 'Cubierto',
                '17': 'Nubes altas', '17n': 'Nubes altas',
                '23': 'Intervalos nubosos con lluvia', '23n': 'Intervalos nubosos con lluvia',
                '24': 'Nuboso con lluvia', '24n': 'Nuboso con lluvia',
                '25': 'Muy nuboso con lluvia', '25n': 'Muy nuboso con lluvia',
                '26': 'Cubierto con lluvia', '26n': 'Cubierto con lluvia',
                '43': 'Intervalos nubosos con nieve', '43n': 'Intervalos nubosos con nieve',
                '51': 'Intervalos nubosos con tormenta', '51n': 'Intervalos nubosos con tormenta',
            }
            
            iconos_bootstrap = {
                '11': 'sun-fill', '11n': 'moon-stars-fill',
                '12': 'cloud-sun-fill', '12n': 'cloud-moon-fill',
                '13': 'clouds-fill', '13n': 'clouds-fill',
                '14': 'cloud-fill', '14n': 'cloud-fill',
                '15': 'cloud-fill', '15n': 'cloud-fill',
                '16': 'cloud-fill', '16n': 'cloud-fill',
                '17': 'clouds', '17n': 'clouds',
                '23': 'cloud-rain-fill', '23n': 'cloud-rain-fill',
                '24': 'cloud-rain-heavy-fill', '24n': 'cloud-rain-heavy-fill',
                '25': 'cloud-rain-heavy-fill', '25n': 'cloud-rain-heavy-fill',
                '26': 'cloud-rain-heavy-fill', '26n': 'cloud-rain-heavy-fill',
                '43': 'cloud-snow-fill', '43n': 'cloud-snow-fill',
                '51': 'cloud-lightning-rain-fill', '51n': 'cloud-lightning-rain-fill',
            }
            
            return {
                'provincia': provincia,
                'municipio': municipio,
                'temperatura': temp_actual,
                'descripcion': estados_cielo.get(estado_cielo_cod, 'Variable'),
                'icono': iconos_bootstrap.get(estado_cielo_cod, 'cloud'),
                'humedad': humedad,
                'viento': viento,
            }
        else:
            logger.warning(f"AEMET API devolvió estado {data1.get('estado')}: {data1.get('descripcion')}")
            return None
            
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