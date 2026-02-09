from flask import Blueprint


api_bp = Blueprint("api", __name__, url_prefix="/api")
galeria_bp = Blueprint('galeria', __name__, url_prefix='/api/galeria')
legend_bp = Blueprint("geoserver_proxy", __name__)


# Al importar routes se registran las rutas sobre api_bp
from . import routes  # noqa: F401,E402