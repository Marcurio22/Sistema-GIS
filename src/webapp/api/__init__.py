from flask import Blueprint


api_bp = Blueprint("api", __name__, url_prefix="/api")
galeria_bp = Blueprint('galeria', __name__, url_prefix='/api/galeria')
legend_bp = Blueprint("geoserver_proxy", __name__)



from . import routes  