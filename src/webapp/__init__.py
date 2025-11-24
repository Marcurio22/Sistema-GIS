from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from .config import Config
from .filters import formato_tel_es


# Instanciar extensiones
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message = None 
    login_manager.needs_refresh_message = None  

    from .auth import auth_bp
    from .admin import admin_bp 
    from .dashboard import dashboard_bp
    from .api import api_bp


    app.jinja_env.filters['tel_es'] = formato_tel_es
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    

    return app
