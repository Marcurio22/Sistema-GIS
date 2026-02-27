from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timezone
from ..models import db, Galeria  

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from geoalchemy2 import functions as geo_func

galeria_bp = Blueprint('galeria', __name__, url_prefix='/api/galeria')

UPLOAD_FOLDER = "./webapp/static/uploads/images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MAX_FILE_SIZE = 12 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# FUNCIONES AUXILIARES


def allowed_file(filename):
    """Valida extensión del archivo"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convertir_a_grados(coordenada):
    """Convierte coordenadas GPS de formato DMS a decimal"""
    if not coordenada:
        return None
    
    try:
        grados = float(coordenada[0])
        minutos = float(coordenada[1])
        segundos = float(coordenada[2])
        return grados + (minutos / 60.0) + (segundos / 3600.0)
    except (TypeError, IndexError, ValueError):
        return None

def extraer_gps_y_fecha(ruta_imagen):
    """
    Extrae GPS y fecha de la foto
    dvuelve: dict con 'latitud', 'longitud', 'fecha_foto'
    """
    print(f"🔍 Iniciando extracción de metadatos de: {ruta_imagen}")
    
    metadatos = {
        'latitud': None,
        'longitud': None,
        'fecha_foto': None
    }
    
    # Verificar que el archivo existe
    if not os.path.exists(ruta_imagen):
        print(f"❌ ERROR: El archivo no existe en {ruta_imagen}")
        return metadatos
    
    try:
        with Image.open(ruta_imagen) as imagen:
            print(f"✅ Imagen abierta correctamente")
            exif_data = imagen._getexif()
            
            if not exif_data:
                print("⚠️ No hay datos EXIF en la imagen")
                return metadatos
            
            print(f"📊 Datos EXIF encontrados: {len(exif_data)} tags")
            
            for tag, value in exif_data.items():
                tag_name = TAGS.get(tag, tag)
                
                # Fecha de la foto
                if tag_name in ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']:
                    if not metadatos['fecha_foto']:
                        try:
                            metadatos['fecha_foto'] = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S')
                            print(f"📅 Fecha encontrada: {metadatos['fecha_foto']}")
                        except (ValueError, TypeError) as e:
                            print(f"⚠️ Error parseando fecha: {e}")
                            pass
                
                # GPS
                elif tag_name == 'GPSInfo':
                    print(f"🗺️ Información GPS encontrada")
                    gps_info = {}
                    for gps_tag in value:
                        gps_tag_name = GPSTAGS.get(gps_tag, gps_tag)
                        gps_info[gps_tag_name] = value[gps_tag]
                    
                    print(f"GPS Info: {gps_info.keys()}")
                    
                    # Latitud
                    if 'GPSLatitude' in gps_info and 'GPSLatitudeRef' in gps_info:
                        latitud = convertir_a_grados(gps_info['GPSLatitude'])
                        if latitud and gps_info['GPSLatitudeRef'] == 'S':
                            latitud = -latitud
                        metadatos['latitud'] = latitud
                        print(f"📍 Latitud: {latitud}")
                    
                    # Longitud
                    if 'GPSLongitude' in gps_info and 'GPSLongitudeRef' in gps_info:
                        longitud = convertir_a_grados(gps_info['GPSLongitude'])
                        if longitud and gps_info['GPSLongitudeRef'] == 'W':
                            longitud = -longitud
                        metadatos['longitud'] = longitud
                        print(f"📍 Longitud: {longitud}")
        
        print(f"✅ Extracción completada: {metadatos}")
        return metadatos
    
    except Exception as e:
        print(f"❌ ERROR extrayendo metadatos: {str(e)}")
        import traceback
        traceback.print_exc()
        return metadatos

def crear_wkt_point(longitud, latitud):
    """
    Crea un punto en formato WKT para PostGIS
    """
    if longitud is None or latitud is None:
        return None
    return f'SRID=4326;POINT({longitud} {latitud})'

# RUTAS

@galeria_bp.route('/subir', methods=['POST'])
def subir_imagen():
    print("=" * 80)
    print("📤 Nueva petición de subida de imagen")
    
    archivo = request.files.get('imagen')
    titulo = request.form.get('titulo')
    descripcion = request.form.get('descripcion', '')
    recinto_id = request.form.get('recinto_id')
    

    lat_form = request.form.get('lat')
    lon_form = request.form.get('lon')

    print(f"Título: {titulo}, Recinto: {recinto_id}")
    if lat_form and lon_form:
        print(f"📍 GPS desde formulario: Lat {lat_form}, Lon {lon_form}")

    # Validaciones
    if not archivo or not titulo or not recinto_id:
        return jsonify({"error": "Faltan datos (imagen, título o recinto)"}), 400

    if not allowed_file(archivo.filename):
        return jsonify({"error": "Solo se permiten imágenes (JPG, PNG, GIF, WEBP)"}), 400

    # Validar tamaño
    archivo.seek(0, os.SEEK_END)
    file_size = archivo.tell()
    archivo.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": "La imagen no puede superar los 12MB"}), 400

    try:
        # Guardar archivo
        filename = secure_filename(archivo.filename)
        
        # Añadir timestamp para evitar colisiones
        nombre_base, extension = os.path.splitext(filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{nombre_base}_{timestamp}{extension}"
        
        ruta_guardada = os.path.join(UPLOAD_FOLDER, filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        archivo.save(ruta_guardada)



        latitud = None
        longitud = None
        fecha_foto = None
        
        if lat_form and lon_form:
            # Usar coordenadas del formulario (del GPS del móvil)
            try:
                latitud = float(lat_form)
                longitud = float(lon_form)
                print(f"✅ Usando GPS del formulario: {latitud}, {longitud}")
            except ValueError:
                print("⚠️ Coordenadas del formulario inválidas")
        
        # Intentar extraer metadatos EXIF (siempre, para fecha y GPS de respaldo)
        try:
            metadatos = extraer_gps_y_fecha(ruta_guardada)
            
            # Si no teníamos GPS del formulario, usar el de EXIF
            if not latitud or not longitud:
                if metadatos.get('latitud') and metadatos.get('longitud'):
                    latitud = metadatos['latitud']
                    longitud = metadatos['longitud']
                    print(f"✅ GPS extraído de EXIF: {latitud}, {longitud}")
                else:
                    print("⚠️ No se encontró GPS ni en formulario ni en EXIF")
            
            # Usar fecha de EXIF si existe
            fecha_foto = metadatos.get('fecha_foto')
            
        except Exception as e:
            print(f"⚠️ Error al extraer EXIF: {str(e)}")
            # Continuar sin EXIF
        
        # Si no hay fecha, usar actual
        if not fecha_foto:
            fecha_foto = datetime.now(timezone.utc)
        
        # Crear punto geométrico si hay coordenadas
        geom = None
        if latitud and longitud:
            geom = crear_wkt_point(longitud, latitud)
            print(f"✅ Punto WKT creado: {geom}")

        # Guardar en base de datos
        nueva_imagen = Galeria(
            recinto_id=int(recinto_id),
            nombre=titulo,
            descripcion=descripcion or None,
            url=f"/static/uploads/images/{filename}",
            fecha_subida=datetime.now(timezone.utc),
            geom=geom,
            fecha_foto=fecha_foto
        )
        
        db.session.add(nueva_imagen)
        db.session.commit()
        
        print(f"✅ Imagen guardada en BD con ID: {nueva_imagen.id_imagen}")
        print("=" * 80)
        
        return jsonify({
            "id": nueva_imagen.id_imagen,
            "thumb": nueva_imagen.url,
            "titulo": nueva_imagen.nombre,
            "descripcion": nueva_imagen.descripcion,
            "latitud": latitud,
            "longitud": longitud,
            "fecha_foto": fecha_foto.isoformat() if fecha_foto else None,
            "tiene_ubicacion": geom is not None,
            "fuente_gps": "formulario" if (lat_form and lon_form) else "exif"
        }), 201

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Error al guardar la imagen en la base de datos"}), 500
    



@galeria_bp.route('/listar/<int:recinto_id>', methods=['GET'])
def listar_imagenes(recinto_id):
    try:
        imagenes = Galeria.query.filter_by(recinto_id=recinto_id).order_by(Galeria.fecha_subida.desc()).all()
        
        resultado = []
        for img in imagenes:
            resultado.append({
                "id": img.id_imagen,
                "thumb": img.url,
                "titulo": img.nombre,
                "descripcion": img.descripcion,
                "fecha_subida": img.fecha_subida.isoformat() if img.fecha_subida else None,
                "fecha_foto": img.fecha_foto.isoformat() if img.fecha_foto else None,
                "geom": db.session.scalar(geo_func.ST_AsText(img.geom)) if img.geom else None
                
            })
        
        return jsonify(resultado), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@galeria_bp.route('/editar/<int:id_imagen>', methods=['PATCH'])
def editar_imagen(id_imagen):
    try:
        
        imagen = Galeria.query.get(id_imagen)
        
        if not imagen:
            return jsonify({"error": "Imagen no encontrada"}), 404
        
        data = request.get_json()
        
        if 'titulo' in data:
            imagen.nombre = data['titulo']
        
        if 'descripcion' in data:
            imagen.descripcion = data['descripcion']
        
        db.session.commit()
        
        return jsonify({
            "ok": True,
            "id": imagen.id_imagen,
            "titulo": imagen.nombre,
            "descripcion": imagen.descripcion
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error al editar imagen: {str(e)}")
        return jsonify({"error": str(e)}), 500


@galeria_bp.route('/eliminar/<int:id_imagen>', methods=['DELETE'])
def eliminar_imagen(id_imagen):
    try:
        imagen = Galeria.query.get(id_imagen)
        
        if not imagen:
            return jsonify({"error": "Imagen no encontrada"}), 404
        
        # Eliminar archivo físico
        if imagen.url:
            ruta_archivo = imagen.url.replace('/static/', './webapp/static/')
            ruta_archivo = ruta_archivo.replace('/', os.sep)
            
            if os.path.exists(ruta_archivo):
                try:
                    os.remove(ruta_archivo)
                    print(f"✅ Archivo eliminado: {ruta_archivo}")
                except Exception as e:
                    print(f"⚠️ No se pudo eliminar el archivo: {e}")
            else:
                print(f"⚠️ Archivo no encontrado: {ruta_archivo}")
        
        # Eliminar registro de la base de datos
        db.session.delete(imagen)
        db.session.commit()
        
        return jsonify({"ok": True, "mensaje": "Imagen eliminada correctamente"}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error al eliminar imagen: {str(e)}")
        return jsonify({"error": str(e)}), 500
    


