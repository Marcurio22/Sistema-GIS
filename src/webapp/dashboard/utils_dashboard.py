from flask import current_app
import requests
import pandas as pd
from pathlib import Path
from ..models import Recinto
from datetime import datetime, timedelta

import rasterio
from rasterio.warp import transform_bounds

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
    

_weather_cache = {}

def obtener_datos_aemet(CODIGO_MUNICIPIO):
    """Obtiene los datos meteorológicos de AEMET con sistema de caché"""
    
    # 1. Verificar si tenemos datos guardados y son recientes (menos de 1 hora)
    cache_key = f"weather_{CODIGO_MUNICIPIO}"
    now = datetime.now()
    
    if cache_key in _weather_cache:
        cached_data = _weather_cache[cache_key]
        tiempo_cache = cached_data.get('timestamp')
        
        # Si el caché tiene menos de 1 hora, devolver datos guardados
        if tiempo_cache and (now - tiempo_cache) < timedelta(hours=1):
            print(f"✅ Usando caché para municipio {CODIGO_MUNICIPIO}")
            return cached_data.get('data')
    
    # 2. Si no hay caché válido, pedir datos nuevos a AEMET
    try:
        AEMET_API_KEY = current_app.config.get('AEMET_API_KEY', 'tu_api_key_aqui')
        
        url_solicitud = f'https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/horaria/{CODIGO_MUNICIPIO}?api_key={AEMET_API_KEY}'
        response1 = requests.get(url_solicitud, timeout=5)
        data1 = response1.json()
        
        # Si hay error de rate limit (429), usar último dato guardado
        if data1.get('estado') == 429:
            print(f"⚠️ Límite de peticiones alcanzado. Usando último caché.")
            if cache_key in _weather_cache:
                return _weather_cache[cache_key].get('data')
            return None
        
        if data1.get('estado') != 200:
            print(f"❌ Error API AEMET: {data1.get('descripcion', 'Error desconocido')}")
            if cache_key in _weather_cache:
                return _weather_cache[cache_key].get('data')
            return None
        
        response2 = requests.get(data1['datos'], timeout=5)
        datos = response2.json()
        
        provincia = datos[0].get('provincia', '')
        municipio = datos[0].get('nombre', '')
        
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        hora_actual = datetime.now().hour
        
        prediccion = None
        for dia in datos[0]['prediccion']['dia']:
            fecha_dia = dia.get('fecha', '')[:10]
            if fecha_dia == fecha_hoy:
                prediccion = dia
                break
        
        if prediccion is None:
            prediccion = datos[0]['prediccion']['dia'][0]

        def obtener_valor_periodo(lista, hora):
            for item in lista:
                if int(item['periodo']) == hora:
                    return item
            return None

        def obtener_periodo_precipitacion(hora, lista_periodos):
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
                    elif hora_inicio <= hora < hora_fin:
                        return periodo
            
            return None

        temp_actual = obtener_valor_periodo(prediccion.get('temperatura', []), hora_actual)
        temp_valor = temp_actual['value'] if temp_actual else None
        
        estado_cielo = obtener_valor_periodo(prediccion.get('estadoCielo', []), hora_actual)
        
        if estado_cielo:
            codigo = estado_cielo.get('value', '')
            descripcion = estado_cielo.get('descripcion', 'Desconocido').strip()
            es_noche = 'n' in codigo
            info_clima = obtener_info_clima(descripcion, es_noche)
        else:
            descripcion = 'Desconocido'
            info_clima = {'icono': 'cloud', 'color': 'text-primary'}
        
        humedad_obj = obtener_valor_periodo(prediccion.get('humedadRelativa', []), hora_actual)
        humedad = humedad_obj['value'] if humedad_obj else None

        viento_velocidad = None
        viento_direccion = None
        viento_grados = None
        if prediccion.get('vientoAndRachaMax'):
            for v in prediccion['vientoAndRachaMax']:
                if int(v['periodo']) == hora_actual:
                    viento_velocidad = v['velocidad'][0] if v.get('velocidad') else None
                    viento_direccion = v['direccion'][0] if v.get('direccion') else None
                    if viento_direccion:
                        direcciones = {
                            'N': 0, 'NE': 45, 'E': 90, 'SE': 135,
                            'S': 180, 'SO': 225, 'O': 270, 'NO': 315
                        }
                        viento_grados = direcciones.get(viento_direccion, 0)
                    break

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
        
        # 3. GUARDAR los datos nuevos en caché
        _weather_cache[cache_key] = {
            'data': resultado,
            'timestamp': now
        }
        
        print(f"🆕 Datos frescos obtenidos y guardados para {CODIGO_MUNICIPIO}")
        return resultado
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        # Si hay error, devolver caché antiguo si existe
        if cache_key in _weather_cache:
            return _weather_cache[cache_key].get('data')
        return None

class MunicipiosCodigosFinder:
    """Buscador de nombres de municipios por código de provincia y municipio."""
    
    def __init__(self):
        # Ruta base
        base_dir = Path(__file__).parent.parent
        csv_dir = base_dir / 'static' / 'csv'
        
        # Cargar el CSV unificado
        self.df = pd.read_csv(
            csv_dir / 'RELACION_MUNICIPIOS_RUSECTOR_AGREGADO_ZONA_C2026(RELACION MUNCIPIOS SIGPAC).csv',  # o el nombre que tenga tu archivo
            sep=';',
            dtype=str
        )
        
        # Limpiar espacios
        self.df['Provincia'] = self.df['Provincia'].str.strip()
        self.df['Municipio'] = self.df['Municipio'].str.strip()  # Cambiado a 'Municipio'
        self.df['Municipio INE'] = self.df['Municipio INE'].str.strip()
        self.df['Nombre Municipio'] = self.df['Nombre Municipio'].str.strip()
        self.df['Nombre Provincia'] = self.df['Nombre Provincia'].str.strip()
        
        # Crear código completo (provincia + municipio)
        self.df['CODIGO'] = self.df['Provincia'].str.zfill(2) + self.df['Municipio'].str.zfill(3)

        self.df['CODIGO_INE'] = (
        self.df['Provincia'].str.zfill(2) +
        self.df['Municipio INE'].str.zfill(3)
    )
        
        # Eliminar duplicados quedándonos con el primero de cada código
        self.df_municipios = self.df.drop_duplicates(subset='CODIGO', keep='first').set_index('CODIGO')
        
        # Crear índice por provincia (eliminando duplicados)
        self.df_provincias = self.df[['Provincia', 'Nombre Provincia']].drop_duplicates().set_index('Provincia')
    
    def obtener_nombre_municipio(self, cod_provincia, cod_municipio):
        """
        Obtiene el nombre del municipio.
        
        Args:
            cod_provincia: Código provincia (16 o '16')
            cod_municipio: Código municipio (51 o '051')
        
        Returns:
            Nombre del municipio o None si no existe
        """
        cpro = str(cod_provincia).zfill(2)
        cmun = str(cod_municipio).zfill(3)
        codigo = f"{cpro}{cmun}"
        
        try:
            # Ahora devuelve un string, no una Serie
            return self.df_municipios.loc[codigo, 'Nombre Municipio']
        except KeyError:
            return None
        
    def obtener_nombre_provincia(self, cod_provincia):
        """Obtiene el nombre de la provincia."""
        cpro = str(cod_provincia).zfill(2)
        
        try:
            return self.df_provincias.loc[cpro, 'Nombre Provincia']
        except KeyError:
            return None
    
    def construir_url_aemet(self, cod_provincia, cod_municipio):
        """
        Construye la URL a la página de AEMET para el municipio dado.
        """
        cpro = str(cod_provincia).zfill(2)
        cmun = str(cod_municipio).zfill(3)

        codigo_normal = f"{cpro}{cmun}"

        try:
            fila = self.df_municipios.loc[codigo_normal]
        except KeyError:
            return None

        codigo_ine = (
            cpro +
            fila['Municipio INE'].zfill(3)
        )

        nombre_municipio = fila['Nombre Municipio']

        nombre_municipio_url = (
            nombre_municipio
            .lower()
            .replace(' ', '-')
            .replace('á', 'a')
            .replace('é', 'e')
            .replace('í', 'i')
            .replace('ó', 'o')
            .replace('ú', 'u')
            .replace('ñ', 'n')
        )

        url = (
            f'https://www.aemet.es/es/eltiempo/prediccion/municipios/mostrarwidget/'
            f'{nombre_municipio_url}-id{codigo_ine}'
            f'?w=g4p111111111ohmffffffx4f86d9t95b6e9r1s8n2'
        )

        print(f"URL AEMET construida: {url}")
        return url

    
    def codigo_recintos(self, user_id):
        """
        Obtiene el código del municipio donde el usuario tiene más recintos.
        SIEMPRE devuelve el código con formato: 2 dígitos provincia + 3 dígitos municipio
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Código del municipio (formato: "01005" o "28079") o None si no hay recintos
        
        Ejemplo:
            provincia=1, municipio=5 → devuelve "01005"
            provincia=28, municipio=79 → devuelve "28079"
        """
        recintos = Recinto.query.filter_by(id_propietario=user_id).all()
        
        if not recintos:
            MUNICIPIO_POR_DEFECTO = "34120"
            return MUNICIPIO_POR_DEFECTO
        
        # Contar recintos por municipio (asegurando formato correcto)
        contador = {}
        for recinto in recintos:
            # IMPORTANTE: zfill(2) para provincia, zfill(3) para municipio
            cpro = str(recinto.provincia).zfill(2)
            cmun = str(recinto.municipio).zfill(3)
            codigo = f"{cpro}{cmun}"
            contador[codigo] = contador.get(codigo, 0) + 1
        
        # Encontrar el municipio con más recintos
        municipio_mas_recintos = max(contador, key=contador.get)
        
        return municipio_mas_recintos
    
    def codigo_recintos_ine(self, user_id):
        """
        Obtiene el código INE del municipio donde el usuario tiene más recintos.
        SIEMPRE devuelve el código con formato: 2 dígitos provincia + 3 dígitos municipio INE
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Código INE del municipio (formato: "01005" o "28079") o None si no hay recintos
        
        Ejemplo:
            provincia=1, municipio=5 → busca en el CSV y devuelve código INE "01XXX"
            provincia=28, municipio=79 → busca en el CSV y devuelve código INE "28XXX"
        """
        # Primero obtener el código normal del municipio con más recintos
        codigo_normal = self.codigo_recintos(user_id)
        
        if codigo_normal is None:
            MUNICIPIO_INE_POR_DEFECTO = "34120"  
            return MUNICIPIO_INE_POR_DEFECTO
        
        try:
            fila = self.df_municipios.loc[codigo_normal]
            cpro = codigo_normal[:2]
            cmun_ine = fila['Municipio INE'].zfill(3)
            codigo_ine = f"{cpro}{cmun_ine}"
            return codigo_ine
        except KeyError:
            return None
    


    def obtener_url_municipio_usuario(self, user_id):
        """
        Obtiene la URL de AEMET del municipio donde el usuario tiene más recintos.
        
        Args:
            user_id: ID del usuario
        
        Returns:
            URL completa a la página de AEMET o None si no hay recintos o no existe el municipio
        
        Ejemplo:
            Si el usuario tiene recintos en provincia=1, municipio=5
            → devuelve URL con código "01005"
        """
        # Obtener el código del municipio con más recintos (ya viene con formato correcto)
        codigo_municipio = self.codigo_recintos(user_id)
        
        if codigo_municipio is None:
            return None
        
        # El código ya tiene 5 dígitos: 2 de provincia + 3 de municipio
        # Ejemplo: "01005" → cpro="01", cmun="005"
        cpro = codigo_municipio[:2]
        cmun = codigo_municipio[2:]
        
        # Construir y devolver la URL
        return self.construir_url_aemet(cpro, cmun)
    
    
municipios_finder = MunicipiosCodigosFinder()


def leaflet_bounds_from_tif(tif_path: str):
    with rasterio.open(tif_path) as src:
        b = src.bounds
        epsg = src.crs.to_epsg() if src.crs else None
        if epsg and epsg != 4326:
            b = transform_bounds(src.crs, "EPSG:4326", b.left, b.bottom, b.right, b.top, densify_pts=21)
            return [[b[1], b[0]], [b[3], b[2]]]

        return [[b.bottom, b.left], [b.top, b.right]]