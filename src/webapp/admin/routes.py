from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from . import admin_bp
from .. import db
from ..models import User, Recinto, Solicitudrecinto
from datetime import datetime, timezone
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
            return redirect(url_for('dashboard.dashboard'))
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



@admin_bp.route('/gestion_recintos')
@login_required
@admin_required
def gestion_recintos():
    logger.info(
        f'Admin {current_user.username} accedió a gestión de recintos',
        extra={'tipo_operacion': 'ACCESO', 'modulo': 'ADMIN'}
    )

    # recintos que ya tienen propietario asignado
    recintos = (
        Recinto.query
        .filter(Recinto.id_propietario.isnot(None))
        .order_by(
            Recinto.provincia,
            Recinto.municipio,
            Recinto.poligono,
            Recinto.recinto
        )
        .all()
    )

    # Todas las solicitudes (pendientes / aprobadas / rechazadas)
    solicitudes = (
        Solicitudrecinto.query
        .order_by(Solicitudrecinto.fecha_solicitud.desc())
        .all()
    )

    return render_template(
        'admin/gestion_recintos.html',
        recintos=recintos,
        solicitudes=solicitudes,
    )

@admin_bp.post("/gestion_recintos/<int:id_solicitud>/aprobar")
@login_required
@admin_required
def aprobar_solicitud_recinto(id_solicitud):
    solicitud = Solicitudrecinto.query.get_or_404(id_solicitud)

    if solicitud.estado != "pendiente":
        flash("La solicitud ya está procesada.", "warning")
        return redirect(url_for("admin.gestion_recintos"))

    recinto = Recinto.query.get_or_404(solicitud.id_recinto)

    # Si ya tiene propietario y es otro usuario → rechazamos automáticamente
    if recinto.id_propietario is not None and recinto.id_propietario != solicitud.id_usuario:
        solicitud.estado = "rechazada"
        solicitud.fecha_resolucion = datetime.now(timezone.utc)
        solicitud.motivo_rechazo = "El recinto ya tiene propietario."
        db.session.commit()
        flash("El recinto ya tenía propietario. Solicitud rechazada.", "danger")
        return redirect(url_for("admin.gestion_recintos"))

    # Asignar propietario
    recinto.id_propietario = solicitud.id_usuario
    # La relación recinto.propietario se resolverá sola a partir de id_propietario

    solicitud.estado = "aprobada"
    solicitud.fecha_resolucion = datetime.now(timezone.utc)

    db.session.commit()
    flash("recinto asignada correctamente al usuario.", "success")
    return redirect(url_for("admin.gestion_recintos"))


@admin_bp.post("/gestion_recintos/<int:id_solicitud>/rechazar")
@login_required
@admin_required
def rechazar_solicitud_recinto(id_solicitud):
    solicitud = Solicitudrecinto.query.get_or_404(id_solicitud)

    if solicitud.estado != "pendiente":
        flash("La solicitud ya está procesada.", "warning")
        return redirect(url_for("admin.gestion_recintos"))

    motivo = request.form.get("motivo_rechazo", "").strip()
    if not motivo:
        motivo = "Solicitud rechazada por el administrador."

    solicitud.estado = "rechazada"
    solicitud.fecha_resolucion = datetime.now(timezone.utc)
    solicitud.motivo_rechazo = motivo

    db.session.commit()
    flash("Solicitud rechazada.", "info")
    return redirect(url_for("admin.gestion_recintos"))
