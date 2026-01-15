from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from ..models import db, Galeria  # tu modelo Galeria

galeria_bp = Blueprint('galeria', __name__, url_prefix='/api/galeria')

UPLOAD_FOLDER = "./webapp/static/uploads/images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --------------------------
# Subir nueva imagen
# --------------------------

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



@galeria_bp.route('/subir', methods=['POST'])
def subir_imagen():
    archivo = request.files.get('imagen')
    titulo = request.form.get('titulo')
    descripcion = request.form.get('descripcion', '')
    recinto_id = request.form.get('recinto_id')

    if not archivo or not titulo or not recinto_id:
        return jsonify({"error": "Faltan datos (imagen, título o recinto)"}), 400

    # Validar que es una imagen
    if not allowed_file(archivo.filename):
        return jsonify({"error": "Solo se permiten imágenes (JPG, PNG, GIF, WEBP)"}), 400

    # Validar tamaño
    archivo.seek(0, os.SEEK_END)
    file_size = archivo.tell()
    archivo.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": "La imagen no puede superar los 5MB"}), 400

    try:
        filename = secure_filename(archivo.filename)
        ruta_guardada = os.path.join(UPLOAD_FOLDER, filename)
        archivo.save(ruta_guardada)

        nueva_imagen = Galeria(
            recinto_id=int(recinto_id),
            nombre=titulo,
            descripcion=descripcion or None,
            url=f"/static/uploads/images/{filename}",
            fecha_subida=datetime.now(timezone.utc)
        )
        
        db.session.add(nueva_imagen)
        db.session.commit()

        return jsonify({
            "id": nueva_imagen.id_imagen,
            "thumb": nueva_imagen.url,
            "titulo": nueva_imagen.nombre,
            "descripcion": nueva_imagen.descripcion
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"Error completo: {str(e)}")
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
                "fecha_subida": img.fecha_subida.isoformat() if img.fecha_subida else None
            })
        
        return jsonify(resultado), 200
        
    except Exception as e:
        print(f"Error al listar imágenes: {str(e)}")
        return jsonify({"error": str(e)}), 500