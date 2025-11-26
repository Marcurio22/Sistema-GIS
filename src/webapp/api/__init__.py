from flask import Blueprint

# ÚNICO blueprint de la API
api_bp = Blueprint("api", __name__, url_prefix="/api")

# Al importar routes se registran las rutas sobre api_bp
from . import routes  # noqa: F401,E402