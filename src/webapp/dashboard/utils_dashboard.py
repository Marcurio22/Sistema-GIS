from flask import Blueprint, render_template, redirect, url_for, flash, current_app
import requests
from datetime import datetime

# Mapeo de descripción de AEMET a datos de visualización
estados_clima = {
    # Despejado
    'Despejado': {
        'icono_dia': 'sun-fill',
        'icono_noche': 'moon-stars-fill',
        'color_dia': 'text-warning',
        'color_noche': 'text-white'
    },
    
    # Nubosidad sin precipitación
    'Poco nuboso': {
        'icono_dia': 'cloud-sun-fill',
        'icono_noche': 'cloud-moon-fill',
        'color_dia': 'text-warning',
        'color_noche': 'text-white'
    },
    'Intervalos nubosos': {
        'icono_dia': 'clouds-fill',
        'icono_noche': 'clouds-fill',
        'color_dia': 'text-secondary',
        'color_noche': 'text-secondary'
    },
    'Nuboso': {
        'icono_dia': 'cloud-fill',
        'icono_noche': 'cloud-fill',
        'color_dia': 'text-secondary',
        'color_noche': 'text-secondary'
    },
    'Muy nuboso': {
        'icono_dia': 'cloud-fill',
        'icono_noche': 'cloud-fill',
        'color_dia': 'text-secondary',
        'color_noche': 'text-secondary'
    },
    'Cubierto': {
        'icono_dia': 'cloud-fill',
        'icono_noche': 'cloud-fill',
        'color_dia': 'text-secondary',
        'color_noche': 'text-secondary'
    },
    'Nubes altas': {
        'icono_dia': 'clouds',
        'icono_noche': 'clouds',
        'color_dia': 'text-secondary',
        'color_noche': 'text-secondary'
    },
    
    # Con lluvia escasa
    'Intervalos nubosos con lluvia escasa': {
        'icono_dia': 'cloud-drizzle-fill',
        'icono_noche': 'cloud-drizzle-fill',
        'color_dia': 'text-info',
        'color_noche': 'text-info'
    },
    'Nuboso con lluvia escasa': {
        'icono_dia': 'cloud-drizzle-fill',
        'icono_noche': 'cloud-drizzle-fill',
        'color_dia': 'text-info',
        'color_noche': 'text-info'
    },
    'Muy nuboso con lluvia escasa': {
        'icono_dia': 'cloud-drizzle-fill',
        'icono_noche': 'cloud-drizzle-fill',
        'color_dia': 'text-info',
        'color_noche': 'text-info'
    },
    'Cubierto con lluvia escasa': {
        'icono_dia': 'cloud-drizzle-fill',
        'icono_noche': 'cloud-drizzle-fill',
        'color_dia': 'text-info',
        'color_noche': 'text-info'
    },
    
    # Con lluvia
    'Intervalos nubosos con lluvia': {
        'icono_dia': 'cloud-rain-fill',
        'icono_noche': 'cloud-rain-fill',
        'color_dia': 'text-primary',
        'color_noche': 'text-primary'
    },
    'Nuboso con lluvia': {
        'icono_dia': 'cloud-rain-heavy-fill',
        'icono_noche': 'cloud-rain-heavy-fill',
        'color_dia': 'text-primary',
        'color_noche': 'text-primary'
    },
    'Muy nuboso con lluvia': {
        'icono_dia': 'cloud-rain-heavy-fill',
        'icono_noche': 'cloud-rain-heavy-fill',
        'color_dia': 'text-primary',
        'color_noche': 'text-primary'
    },
    'Cubierto con lluvia': {
        'icono_dia': 'cloud-rain-heavy-fill',
        'icono_noche': 'cloud-rain-heavy-fill',
        'color_dia': 'text-primary',
        'color_noche': 'text-primary'
    },
    'Chubascos': {
        'icono_dia': 'cloud-rain-heavy-fill',
        'icono_noche': 'cloud-rain-heavy-fill',
        'color_dia': 'text-primary',
        'color_noche': 'text-primary'
    },
    
    # Con nieve escasa
    'Intervalos nubosos con nieve escasa': {
        'icono_dia': 'cloud-snow',
        'icono_noche': 'cloud-snow',
        'color_dia': 'text-info',
        'color_noche': 'text-info'
    },
    'Nuboso con nieve escasa': {
        'icono_dia': 'cloud-snow',
        'icono_noche': 'cloud-snow',
        'color_dia': 'text-info',
        'color_noche': 'text-info'
    },
    'Muy nuboso con nieve escasa': {
        'icono_dia': 'cloud-snow',
        'icono_noche': 'cloud-snow',
        'color_dia': 'text-info',
        'color_noche': 'text-info'
    },
    'Cubierto con nieve escasa': {
        'icono_dia': 'cloud-snow',
        'icono_noche': 'cloud-snow',
        'color_dia': 'text-info',
        'color_noche': 'text-info'
    },
    
    # Con nieve
    'Intervalos nubosos con nieve': {
        'icono_dia': 'cloud-snow-fill',
        'icono_noche': 'cloud-snow-fill',
        'color_dia': 'text-light',
        'color_noche': 'text-light'
    },
    'Nuboso con nieve': {
        'icono_dia': 'cloud-snow-fill',
        'icono_noche': 'cloud-snow-fill',
        'color_dia': 'text-light',
        'color_noche': 'text-light'
    },
    'Muy nuboso con nieve': {
        'icono_dia': 'cloud-snow-fill',
        'icono_noche': 'cloud-snow-fill',
        'color_dia': 'text-light',
        'color_noche': 'text-light'
    },
    'Cubierto con nieve': {
        'icono_dia': 'cloud-snow-fill',
        'icono_noche': 'cloud-snow-fill',
        'color_dia': 'text-light',
        'color_noche': 'text-light'
    },
    'Chubascos de nieve': {
        'icono_dia': 'cloud-snow-fill',
        'icono_noche': 'cloud-snow-fill',
        'color_dia': 'text-light',
        'color_noche': 'text-light'
    },
    
    # Con tormenta
    'Intervalos nubosos con tormenta': {
        'icono_dia': 'cloud-lightning-rain-fill',
        'icono_noche': 'cloud-lightning-rain-fill',
        'color_dia': 'text-danger',
        'color_noche': 'text-danger'
    },
    'Nuboso con tormenta': {
        'icono_dia': 'cloud-lightning-rain-fill',
        'icono_noche': 'cloud-lightning-rain-fill',
        'color_dia': 'text-danger',
        'color_noche': 'text-danger'
    },
    'Muy nuboso con tormenta': {
        'icono_dia': 'cloud-lightning-rain-fill',
        'icono_noche': 'cloud-lightning-rain-fill',
        'color_dia': 'text-danger',
        'color_noche': 'text-danger'
    },
    'Cubierto con tormenta': {
        'icono_dia': 'cloud-lightning-rain-fill',
        'icono_noche': 'cloud-lightning-rain-fill',
        'color_dia': 'text-danger',
        'color_noche': 'text-danger'
    },
    
    # Con tormenta y lluvia escasa
    'Intervalos nubosos con tormenta y lluvia escasa': {
        'icono_dia': 'cloud-lightning-fill',
        'icono_noche': 'cloud-lightning-fill',
        'color_dia': 'text-warning',
        'color_noche': 'text-warning'
    },
    'Nuboso con tormenta y lluvia escasa': {
        'icono_dia': 'cloud-lightning-fill',
        'icono_noche': 'cloud-lightning-fill',
        'color_dia': 'text-warning',
        'color_noche': 'text-warning'
    },
    'Muy nuboso con tormenta y lluvia escasa': {
        'icono_dia': 'cloud-lightning-fill',
        'icono_noche': 'cloud-lightning-fill',
        'color_dia': 'text-warning',
        'color_noche': 'text-warning'
    },
    'Cubierto con tormenta y lluvia escasa': {
        'icono_dia': 'cloud-lightning-fill',
        'icono_noche': 'cloud-lightning-fill',
        'color_dia': 'text-warning',
        'color_noche': 'text-warning'
    },
    
    # Niebla, bruma y calima
    'Niebla': {
        'icono_dia': 'cloud-fog-fill',
        'icono_noche': 'cloud-fog-fill',
        'color_dia': 'text-secondary',
        'color_noche': 'text-secondary'
    },
    'Bruma': {
        'icono_dia': 'cloud-haze-fill',
        'icono_noche': 'cloud-haze-fill',
        'color_dia': 'text-secondary',
        'color_noche': 'text-secondary'
    },
    'Calima': {
        'icono_dia': 'cloud-haze-fill',
        'icono_noche': 'cloud-haze-fill',
        'color_dia': 'text-secondary',
        'color_noche': 'text-secondary'
    },
}

def obtener_info_clima(descripcion, es_noche=False):
    """
    Obtiene el icono y color según la descripción del clima
    
    Args:
        descripcion: Descripción del estado del cielo desde AEMET
        es_noche: Boolean que indica si es de noche
    
    Returns:
        dict con 'icono' y 'color'
    """
    # Limpiar la descripción (quitar espacios extra)
    descripcion_limpia = descripcion.strip() if descripcion else 'Desconocido'
    
    # Buscar en el diccionario
    info = estados_clima.get(descripcion_limpia)
    
    if info:
        icono = info['icono_noche'] if es_noche else info['icono_dia']
        color = info['color_noche'] if es_noche else info['color_dia']
        return {'icono': icono, 'color': color}
    else:
        # Valores por defecto si no se encuentra
        return {'icono': 'cloud', 'color': 'text-primary'}
    

def obtener_datos_aemet(CODIGO_MUNICIPIO):
    """Obtiene los datos meteorológicos de AEMET para Burgos"""
    try:
        AEMET_API_KEY = current_app.config.get('AEMET_API_KEY', 'tu_api_key_aqui')
        
        
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

        def obtener_periodo_precipitacion(hora, lista_periodos):
            """
            Determina el período de precipitación según la hora actual.
            Busca en qué rango cae la hora entre los períodos disponibles.
            """
            if not lista_periodos:
                return None
            
            for periodo_obj in lista_periodos:
                periodo = periodo_obj.get('periodo', '')
                if len(periodo) == 4:
                    hora_inicio = int(periodo[:2])
                    hora_fin = int(periodo[2:])
                    

                    if hora_fin == 0 or hora_fin < hora_inicio:
                        if hora >= hora_inicio or hora < 24:
                            return periodo
                    # Caso normal: período dentro del mismo día
                    elif hora_inicio <= hora < hora_fin:
                        return periodo
            
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

        # Obtener velocidad y dirección del viento
        viento_velocidad = None
        viento_direccion = None
        viento_grados = None
        if prediccion.get('vientoAndRachaMax'):
            for v in prediccion['vientoAndRachaMax']:
                if int(v['periodo']) == hora_actual:
                    viento_velocidad = v['velocidad'][0] if v.get('velocidad') else None
                    viento_direccion = v['direccion'][0] if v.get('direccion') else None
                    # Convertir dirección a grados para rotar la flecha
                    # La flecha indica HACIA DÓNDE VA el viento (convención AEMET)
                    if viento_direccion:
                        direcciones = {
                            'N': 0,    # Norte: flecha hacia abajo
                            'NE': 45,  # Noreste: flecha hacia abajo-derecha
                            'E': 90,   # Este: flecha hacia la derecha
                            'SE': 135, # Sureste: flecha hacia arriba-derecha
                            'S': 180,  # Sur: flecha hacia arriba
                            'SO': 225, # Suroeste: flecha hacia arriba-izquierda
                            'O': 270,  # Oeste: flecha hacia la izquierda
                            'NO': 315  # Noroeste: flecha hacia abajo-izquierda
                        }
                        viento_grados = direcciones.get(viento_direccion, 0)
                    break

        # Obtener probabilidad de precipitación
        prob_precipitacion = None
        if prediccion.get('probPrecipitacion'):
            periodo_actual = obtener_periodo_precipitacion(hora_actual, prediccion['probPrecipitacion'])
            if periodo_actual:
                for prob in prediccion['probPrecipitacion']:
                    if prob.get('periodo') == periodo_actual:
                        prob_precipitacion = prob.get('value')
                        break

        resultado = {
            'provincia': provincia,
            'municipio': municipio,
            'temperatura': temp_valor,
            'descripcion': descripcion,
            'icono': info_clima['icono'],
            'color_icono': info_clima['color'],
            'humedad': humedad,
            'viento_velocidad': viento_velocidad,
            'viento_direccion': viento_direccion,
            'viento_grados': viento_grados,
            'prob_precipitacion': prob_precipitacion,
        }
        return resultado    

    except requests.exceptions.Timeout:
        return None
    except Exception as e:
        return None

def obtener_municipio_codigo():
    """
    Función de ejemplo para obtener el código del municipio.
    En la implementación real, esto debería extraerse de las parcelas del usuario.
    """
    # Código de municipio de ejemplo (Venta de Baños, Palencia)
    return '34023'