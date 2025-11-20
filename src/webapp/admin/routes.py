from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from . import admin_bp
from .. import db
from ..models import User
import logging

logger = logging.getLogger('app.admin')
logger.setLevel(logging.INFO)

# Decorador para verificar que el usuario es admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'admin':
            flash('No tienes permisos para acceder a esta sección.', 'danger')
            logger.warning(
                f'Intento de acceso no autorizado al panel admin por: {current_user.username if current_user.is_authenticated else "anónimo"}',
                extra={'tipo_operacion': 'ACCESO_DENEGADO', 'modulo': 'ADMIN'}
            )
            return redirect(url_for('auth.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/usuarios')
@login_required
@admin_required
def gestion_usuarios():
    usuarios = User.query.all()
    logger.info(
        f'Admin {current_user.username} accedió a gestión de usuarios',
        extra={'tipo_operacion': 'ACCESO', 'modulo': 'ADMIN'}
    )
    
    return render_template('admin/gestion_usuario.html', usuarios=usuarios)
