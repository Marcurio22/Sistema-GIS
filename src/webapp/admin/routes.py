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
    usuarios = User.query.order_by(
        User.rol.asc(),       # Admins primero (asumiendo que 'admin' > 'user')
        User.activo.desc(),    # Activos antes que inactivos
        User.id_usuario        # Por último por ID ascendente
    ).all()
    logger.info(
        f'Admin {current_user.username} accedió a gestión de usuarios',
        extra={'tipo_operacion': 'ACCESO', 'modulo': 'ADMIN'}
    )
    
    return render_template('admin/gestion_usuario.html', usuarios=usuarios)





@admin_bp.route('/usuarios/<int:id>/activar')
@login_required
@admin_required
def activar_usuario(id):
    usuario = User.query.get_or_404(id)
    usuario.activo = True
    db.session.commit()
    
    logger.info(
        f'Admin {current_user.username} activó al usuario {usuario.username}',
        extra={'tipo_operacion': 'ACTIVAR_USUARIO', 'modulo': 'ADMIN'}
    )
    
    flash(f'Usuario {usuario.username} activado correctamente.', 'success')
    return redirect(url_for('admin.gestion_usuarios'))


@admin_bp.route('/usuarios/<int:id>/desactivar')
@login_required
@admin_required
def desactivar_usuario(id):

    usuario = User.query.get_or_404(id)
    usuario.activo = False
    db.session.commit()
    
    logger.info(
        f'Admin {current_user.username} desactivó al usuario {usuario.username}',
        extra={'tipo_operacion': 'DESACTIVAR_USUARIO', 'modulo': 'ADMIN'}
    )
    
    flash(f'Usuario {usuario.username} desactivado correctamente.', 'warning')
    return redirect(url_for('admin.gestion_usuarios'))

@admin_bp.route('/usuarios/<int:id>/hacer_admin')
@login_required
@admin_required
def hacer_admin(id):
    usuario = User.query.get_or_404(id)

    usuario.rol = 'admin'
    db.session.commit()
    flash(f"{usuario.username} ahora es administrador.", "success")
    return redirect(url_for('admin.gestion_usuarios'))
