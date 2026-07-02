from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_session import Session
from .config import Config
from .filters import formato_tel_es


# Instanciar extensiones
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    app.config["SESSION_SQLALCHEMY"] = db 
    Session(app)      
    
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message = None 
    login_manager.needs_refresh_message = None
    
    # Handler para usuarios no autorizados
    @login_manager.unauthorized_handler
    def unauthorized():
        return redirect(url_for('auth.login'))

    @app.context_processor
    def inject_comunidad_branding():
        nombre = (app.config.get("COMUNIDAD_REGANTES_NOMBRE") or "").strip()
        titulo_base = "Comunidad de Regantes"
        if nombre:
            return {
                "comunidad_nombre": nombre,
                "comunidad_titulo": f"{titulo_base} {nombre}",
                "comunidad_bienvenida": f"Bienvenido a la comunidad de regantes {nombre}",
                "comunidad_titulo_corto": f"C. Regantes {nombre}",
            }
        return {
            "comunidad_nombre": "",
            "comunidad_titulo": titulo_base,
            "comunidad_bienvenida": "Bienvenido a la comunidad de regantes",
            "comunidad_titulo_corto": "C. Regantes",
        }

    from .auth import auth_bp
    from .admin import admin_bp 
    from .dashboard import dashboard_bp
    from .api import api_bp, legend_bp
    from .api.galeria import galeria_bp


    app.jinja_env.filters['tel_es'] = formato_tel_es
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(galeria_bp)
    app.register_blueprint(legend_bp)
    

    return app