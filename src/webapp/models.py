
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db 

class User(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    
    # Columnas adaptadas a tu estructura
    id_usuario = db.Column(db.Integer, primary_key=True, index=True)
    username = db.Column(db.String, unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)
    rol = db.Column(db.String, default='user')
    fecha_registro = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    activo = db.Column(db.Boolean, default=True)

    # Métodos de seguridad 
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id_usuario)

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
        # Use field names present in this model for a clear representation
        return f'<Log {self.tipo_operacion!s} by User {self.id_usuario!r} at {self.fecha_hora!r}>'