from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timezone
from ..models import db, Galeria  # tu modelo Galeria

galeria_bp = Blueprint('galeria', __name__, url_prefix='/api/galeria')

UPLOAD_FOLDER = "./webapp/static/uploads/images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --------------------------
# Subir nueva imagen
# --------------------------

@galeria_bp.route('/subir', methods=['POST'])
def subir_imagen():
    archivo = request.files.get('imagen')
    titulo = request.form.get('titulo')
    descripcion = request.form.get('descripcion', '')
    recinto_id = request.form.get('recinto_id')  # ← CAMBIAR A recinto_id

    if not archivo or not titulo or not recinto_id:
        return jsonify({"error": "Faltan datos (imagen, título o recinto)"}), 400

    try:
        filename = secure_filename(archivo.filename)
        ruta_guardada = os.path.join(UPLOAD_FOLDER, filename)
        archivo.save(ruta_guardada)

        nueva_imagen = Galeria(
            recinto_id=int(recinto_id),  # ← CAMBIAR A recinto_id
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
        return jsonify({"error": f"Error en la base de datos: {str(e)}"}), 500