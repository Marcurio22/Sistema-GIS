import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")

    DB_USER = os.getenv("POSTGRES_USER")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
    DB_HOST = os.getenv("POSTGRES_HOST")
    DB_PORT = os.getenv("POSTGRES_PORT")
    DB_NAME = os.getenv("POSTGRES_DB")

    SQLALCHEMY_DATABASE_URI = (
        os.getenv("DATABASE_URL")
        or f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }

    SESSION_TYPE = "sqlalchemy"
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = 2629800
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "session:"

    AEMET_API_KEY = os.getenv("AEMET_API_KEY")

    # cambiar por lo del server
    GEOSERVER_WMS_URL = os.getenv("GEOSERVER_WMS_URL")
    GEOSERVER_WFS_URL = os.getenv("GEOSERVER_WFS_URL")
    GEOSERVER_USER = os.getenv("GEOSERVER_USER")
    GEOSERVER_PASSWORD = os.getenv("GEOSERVER_PASSWORD")
    GEOSERVER_RECINTOS_TYPENAME = os.getenv("GEOSERVER_RECINTOS_TYPENAME", "gis_project:recintos_con_propietario")


    # Configuración de correo electrónico
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "25"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True") == "True"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "False") == "True"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")

    INFORIEGO_API_KEY = os.getenv("INFORIEGO_API_KEY")
    