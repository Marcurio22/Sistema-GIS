from datetime import datetime, timezone
from flask_login import UserMixin
from geoalchemy2 import Geometry
from werkzeug.security import generate_password_hash, check_password_hash
from . import db 

try:
    from geoalchemy2 import Geometry as GA2Geometry
except ImportError:
    GA2Geometry = None 

class User(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    
    id_usuario = db.Column(db.Integer, primary_key=True, index=True)
    username = db.Column(db.String, unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)
    rol = db.Column(db.String, default='user')
    fecha_registro = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    activo = db.Column(db.Boolean, default=False)
    telefono = db.Column(db.String, nullable=True)

    parcelas = db.relationship('Parcela', back_populates='propietario', lazy=True)
    solicitudes_parcelas = db.relationship(
        "SolicitudParcela",
        back_populates="usuario",
        lazy="dynamic"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id_usuario)
    
    def is_active(self):
        return self.activo

    def __repr__(self):
        return f'<User {self.username}>'
    

class LogsSistema(db.Model):
    __tablename__ = 'logs_sistema'
    
    id_log = db.Column(db.Integer, primary_key=True, index=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    fecha_hora = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    tipo_operacion = db.Column(db.String, nullable=False)
    modulo = db.Column(db.String, nullable=False)
    nivel = db.Column(db.String, nullable=False)
    mensaje = db.Column(db.String, nullable=False)
    datos_adicionales = db.Column(db.String)

    def __repr__(self):
        return f'<Log {self.tipo_operacion} by User {self.id_usuario} at {self.fecha_hora}>'
    

class Parcela(db.Model):
    __tablename__ = "parcelas"
    
    id_parcela = db.Column(db.Integer, primary_key=True, index=True)
    nombre = db.Column(db.String)
    superficie_ha = db.Column(db.Numeric(12, 4))
    
    if GA2Geometry:
        geom = db.Column(GA2Geometry("MULTIPOLYGON", srid=4326))
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

    # Relación con usuarios
    id_propietario = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id_usuario"),
        nullable=True
    )

    propietario = db.relationship("User", back_populates="parcelas")
    solicitudes = db.relationship(
        "SolicitudParcela",
        back_populates="parcela",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Parcela SIGPAC {self.provincia}-{self.municipio}-{self.poligono}-{self.parcela}>"

    @property
    def nombre_municipio(self):
        from webapp.dashboard.utils_dashboard import municipios_finder
        return municipios_finder.obtener_nombre_municipio(self.provincia, self.municipio) 
    @property
    def nombre_provincia(self):
        from webapp.dashboard.utils_dashboard import municipios_finder
        return municipios_finder.obtener_nombre_provincia(self.provincia)



class SolicitudParcela(db.Model):
    __tablename__ = "solicitudes_parcelas"
    
    id_solicitud = db.Column(db.Integer, primary_key=True, index=True)
    id_usuario = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id_usuario"),
        nullable=False
    )
    id_parcela = db.Column(
        db.Integer,
        db.ForeignKey("parcelas.id_parcela"),
        nullable=False
    )
    estado = db.Column(db.String(20), nullable=False, default="pendiente")
    fecha_solicitud = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    fecha_resolucion = db.Column(db.DateTime(timezone=True), nullable=True)
    motivo_rechazo = db.Column(db.String, nullable=True)

    usuario = db.relationship("User", back_populates="solicitudes_parcelas")
    parcela = db.relationship("Parcela", back_populates="solicitudes")