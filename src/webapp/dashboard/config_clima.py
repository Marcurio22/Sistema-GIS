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