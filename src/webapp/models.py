from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db 

# Importación condicional de GeoAlchemy2
try:
    from geoalchemy2 import Geometry
    GEOALCHEMY_AVAILABLE = True
except ImportError:
    Geometry = None
    GEOALCHEMY_AVAILABLE = False


class User(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    
    id_usuario = db.Column(db.Integer, primary_key=True, index=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    rol = db.Column(db.String(20), default='user')
    fecha_registro = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    activo = db.Column(db.Boolean, default=False)
    telefono = db.Column(db.String(20), nullable=True)


    notificaciones_activas = db.Column(db.Boolean, default=True)

    # Relaciones
    recintos = db.relationship('Recinto', back_populates='propietario', lazy=True)
    solicitudes_recintos = db.relationship(
        "Solicitudrecinto",
        back_populates="usuario",
        lazy="dynamic"
    )

    def set_password(self, password):
        """Genera el hash de la contraseña"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica la contraseña contra el hash"""
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        """Requerido por Flask-Login"""
        return str(self.id_usuario)
    
    def __repr__(self):
        return f'<User {self.username}>'


class LogsSistema(db.Model):
    __tablename__ = 'logs_sistema'
    
    id_log = db.Column(db.Integer, primary_key=True, index=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    fecha_hora = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    tipo_operacion = db.Column(db.String(50), nullable=False)
    modulo = db.Column(db.String(50), nullable=False)
    nivel = db.Column(db.String(20), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    datos_adicionales = db.Column(db.Text)


    usuario = db.relationship('User', backref='logs_sistema', lazy=True)

    def __repr__(self):
        return f'<Log {self.tipo_operacion} by User {self.id_usuario} at {self.fecha_hora}>'


class Recinto(db.Model):
    __tablename__ = "recintos"
    
    id_recinto = db.Column(db.Integer, primary_key=True, index=True)
    nombre = db.Column(db.String(200))
    superficie_ha = db.Column(db.Numeric(12, 4))
    
    # Geometría condicional
    if GEOALCHEMY_AVAILABLE:
        geom = db.Column(Geometry("MULTIPOLYGON", srid=4326))
    else:
        geom = db.Column(db.LargeBinary)

    fecha_creacion = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    activa = db.Column(db.Boolean, default=True)

    # Campos SIGPAC
    provincia = db.Column(db.BigInteger, nullable=False)
    municipio = db.Column(db.BigInteger, nullable=False)
    agregado = db.Column(db.BigInteger)
    zona = db.Column(db.BigInteger)
    poligono = db.Column(db.BigInteger, nullable=False)
    parcela = db.Column(db.BigInteger, nullable=False)
    recinto = db.Column(db.BigInteger)  # A veces también hay campo recinto

    # Relación con usuarios
    id_propietario = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id_usuario", ondelete="SET NULL"),
        nullable=True
    )

    # Relaciones
    propietario = db.relationship("User", back_populates="recintos")
    solicitudes = db.relationship(
        "Solicitudrecinto",
        back_populates="recinto",
        cascade="all, delete-orphan"
    )



    indices_raster = db.relationship('IndicesRaster', back_populates='recinto', lazy='dynamic')

    def __repr__(self):
        return f"<Recinto SIGPAC {self.provincia}-{self.municipio}-{self.poligono}-{self.parcela}>"

    @property
    def nombre_municipio(self):
        """Obtiene el nombre del municipio desde el código"""
        try:
            from webapp.dashboard.utils_dashboard import municipios_finder
            return municipios_finder.obtener_nombre_municipio(self.provincia, self.municipio)
        except Exception:
            return f"Municipio {self.municipio}"
    
    @property
    def nombre_provincia(self):
        """Obtiene el nombre de la provincia desde el código"""
        try:
            from webapp.dashboard.utils_dashboard import municipios_finder
            return municipios_finder.obtener_nombre_provincia(self.provincia)
        except Exception:
            return f"Provincia {self.provincia}"


class Solicitudrecinto(db.Model):
    __tablename__ = "solicitudes_recintos"
    
    id_solicitud = db.Column(db.Integer, primary_key=True, index=True)
    id_usuario = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id_usuario", ondelete="CASCADE"),
        nullable=False
    )
    id_recinto = db.Column(
        db.Integer,
        db.ForeignKey("recintos.id_recinto", ondelete="CASCADE"),
        nullable=False
    )
    estado = db.Column(db.String(20), nullable=False, default="pendiente")
    fecha_solicitud = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    fecha_resolucion = db.Column(db.DateTime(timezone=True), nullable=True)
    motivo_rechazo = db.Column(db.Text, nullable=True)
    tipo_solicitud = db.Column(db.String(100), nullable=True)

    # Relaciones
    usuario = db.relationship("User", back_populates="solicitudes_recintos")
    recinto = db.relationship("Recinto", back_populates="solicitudes")


    def __repr__(self):
        return f"<Solicitud {self.id_solicitud} - Usuario {self.id_usuario} - Recinto {self.id_recinto} - {self.estado}>"
    



class Galeria(db.Model):
    __tablename__ = "galeria"
    id_imagen = db.Column(db.Integer, primary_key=True, index=True)
    recinto_id = db.Column(
        db.Integer,
        db.ForeignKey("recintos.id_recinto", ondelete="CASCADE"),
        nullable=False
    )
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(500), nullable=False)
    fecha_subida = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ProductoFega(db.Model):
    __tablename__ = "productos_fega"
    
    codigo = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(200), nullable=False)
    
    variedades = db.relationship("Variedad", back_populates="producto_fega")

class Variedad(db.Model):
    __tablename__ = "variedades"
    id_variedad = db.Column(db.Integer, primary_key=True, index=True)
    nombre = db.Column(db.String(200), unique=True, nullable=False)
    producto_fega_id = db.Column(db.Integer, db.ForeignKey("productos_fega.codigo", ondelete="CASCADE"), nullable=True) 

    producto_fega = db.relationship("ProductoFega", back_populates="variedades")



class IndicesRaster(db.Model):
    __tablename__ = 'indices_raster'
    
    id_indice = db.Column(db.Integer, primary_key=True)
    id_imagen = db.Column(db.Integer, nullable=True)
    tipo_indice = db.Column(db.String(50), nullable=False)
    fecha_calculo = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    epsg = db.Column(db.Integer, nullable=True)
    resolucion_m = db.Column(db.Numeric(10, 2), nullable=True)
    valor_medio = db.Column(db.Numeric(10, 4), nullable=True)
    valor_min = db.Column(db.Numeric(10, 4), nullable=True)
    valor_max = db.Column(db.Numeric(10, 4), nullable=True)
    desviacion_std = db.Column(db.Numeric(10, 4), nullable=True)
    ruta_raster = db.Column(db.Text, nullable=True)
    fecha_ndvi = db.Column(db.DateTime(timezone=True), nullable=True)
    ruta_ndvi = db.Column(db.Text, nullable=True)
    
    id_recinto = db.Column(db.Integer, db.ForeignKey('recintos.id_recinto'), nullable=False)
    
    recinto = db.relationship('Recinto', back_populates='indices_raster')
    
    def __repr__(self):
        return f'<IndicesRaster {self.id_indice} - {self.tipo_indice}>'
    
    def to_dict(self):
        """Convierte el objeto a diccionario para JSON"""
        return {
            'id_indice': self.id_indice,
            'id_imagen': self.id_imagen,
            'tipo_indice': self.tipo_indice,
            'fecha_calculo': self.fecha_calculo.isoformat() if self.fecha_calculo else None,
            'epsg': self.epsg,
            'resolucion_m': float(self.resolucion_m) if self.resolucion_m else None,
            'valor_medio': float(self.valor_medio) if self.valor_medio else None,
            'valor_min': float(self.valor_min) if self.valor_min else None,
            'valor_max': float(self.valor_max) if self.valor_max else None,
            'desviacion_std': float(self.desviacion_std) if self.desviacion_std else None,
            'ruta_raster': self.ruta_raster,
            'id_recinto': self.id_recinto,
            'fecha_ndvi': self.fecha_ndvi.isoformat() if self.fecha_ndvi else None,
            'ruta_ndvi': self.ruta_ndvi,
        }