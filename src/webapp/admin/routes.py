from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from . import admin_bp
from .. import db
from ..models import User, Recinto, Solicitudrecinto, LogsSistema
from datetime import datetime, timezone
import logging
from ..utils.utils import normalizar_telefono_es
from ..utils.logging_handler import SQLAlchemyHandler
from ..utils.email_service import enviar_notificacion_aceptacion, enviar_notificacion_rechazo

logger = logging.getLogger('app.admin')
logger.setLevel(logging.INFO)

db_handler = SQLAlchemyHandler()
formatter = logging.Formatter('%(levelname)s - %(message)s')
db_handler.setFormatter(formatter)
logger.addHandler(db_handler)

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
            Recinto.parcela,
        )
        .all()
    )

    # Todas las solicitudes (pendientes / aprobadas / rechazadas)
    solicitudes = (
        Solicitudrecinto.query
        .order_by(Solicitudrecinto.fecha_solicitud.desc())
        .all()
    )

    usuarios = ( User.query.all() )

    logs_solicitudes = LogsSistema.query.filter(LogsSistema.modulo == 'SOLICITUDES').all()

    return render_template(
        'admin/gestion_recintos.html',
        recintos=recintos,
        solicitudes=solicitudes,
        usuarios=usuarios,
        logs_solicitudes=logs_solicitudes,
    )

@admin_bp.post("/gestion_recintos/<int:id_solicitud>/aprobar")
@login_required
@admin_required
def aprobar_solicitud_recinto(id_solicitud):
    solicitud = Solicitudrecinto.query.get_or_404(id_solicitud)

    if solicitud.estado != "pendiente":
        flash("La solicitud ya está procesada.", "warning")
        logger.warning(
            f'Admin {current_user.username} intentó aprobar solicitud {id_solicitud} que ya estaba procesada (estado: {solicitud.estado})',
            extra={'tipo_operacion': 'APROBAR_SOLICITUD_YA_PROCESADA', 'modulo': 'SOLICITUDES'}
        )
        return redirect(url_for("admin.gestion_recintos"))

    recinto = Recinto.query.get_or_404(solicitud.id_recinto)
    usuario_solicitante = User.query.get(solicitud.id_usuario)

    print(recinto, recinto.id_propietario, solicitud.id_usuario)
    # Si ya tiene propietario y es otro usuario → rechazamos automáticamente
    if recinto.id_propietario is not None and recinto.id_propietario != solicitud.id_usuario:
        solicitud.estado = "rechazada"
        solicitud.fecha_resolucion = datetime.now(timezone.utc)
        solicitud.motivo_rechazo = "El recinto ya tiene propietario."
        db.session.commit()
        
        logger.warning(
            f'Admin {current_user.username} rechazó automáticamente solicitud {id_solicitud} del usuario {usuario_solicitante.username if usuario_solicitante else "desconocido"} para recinto {recinto.id_recinto} (ya tenía propietario)',
            extra={'tipo_operacion': 'RECHAZO_AUTOMATICO_SOLICITUD', 'modulo': 'SOLICITUDES'}
        )
        
        flash("El recinto ya tenía propietario. Solicitud rechazada.", "danger")
        return redirect(url_for("admin.gestion_recintos"))

    # Asignar propietario
    recinto.id_propietario = solicitud.id_usuario
    # La relación recinto.propietario se resolverá sola a partir de id_propietario

    solicitud.estado = "aprobada"
    solicitud.fecha_resolucion = datetime.now(timezone.utc)

    db.session.commit()

    if usuario_solicitante and usuario_solicitante.email:
        numero_parcela = f"{recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}"
        direccion_parcela = f"Provincia: {recinto.provincia}, Municipio: {recinto.municipio}, Polígono: {recinto.poligono}, Parcela: {recinto.parcela}"
        
        enviar_notificacion_aceptacion(
            destinatario=usuario_solicitante.email,
            nombre_usuario=usuario_solicitante.username,
            numero_parcela=numero_parcela,
            direccion_parcela=direccion_parcela
        )
    
    logger.info(
        f'Admin {current_user.username} aprobó solicitud {id_solicitud} del usuario {usuario_solicitante.username if usuario_solicitante else "desconocido"} para recinto {recinto.id_recinto} (Prov: {recinto.provincia}, Mun: {recinto.municipio}, Pol: {recinto.poligono}, Par: {recinto.parcela})',
        extra={'tipo_operacion': 'APROBAR_SOLICITUD', 'modulo': 'SOLICITUDES'}
    )
    
    flash("Recinto asignado correctamente al usuario.", "success")
    return redirect(url_for("admin.gestion_recintos"))


@admin_bp.post("/gestion_recintos/<int:id_solicitud>/rechazar")
@login_required
@admin_required
def rechazar_solicitud_recinto(id_solicitud):
    solicitud = Solicitudrecinto.query.get_or_404(id_solicitud)

    if solicitud.estado != "pendiente":
        flash("La solicitud ya está procesada.", "warning")
        logger.warning(
            f'Admin {current_user.username} intentó rechazar solicitud {id_solicitud} que ya estaba procesada (estado: {solicitud.estado})',
            extra={'tipo_operacion': 'RECHAZAR_SOLICITUD_YA_PROCESADA', 'modulo': 'SOLICITUDES'}
        )
        return redirect(url_for("admin.gestion_recintos"))

    motivo = request.form.get("motivo_rechazo", "").strip()
    if not motivo:
        motivo = "Solicitud rechazada por el administrador."

    recinto = Recinto.query.get(solicitud.id_recinto)
    usuario_solicitante = User.query.get(solicitud.id_usuario)

    solicitud.estado = "rechazada"
    solicitud.fecha_resolucion = datetime.now(timezone.utc)
    solicitud.motivo_rechazo = motivo

    db.session.commit()
    
    logger.info(
        f'Admin {current_user.username} rechazó solicitud {id_solicitud} del usuario {usuario_solicitante.username if usuario_solicitante else "desconocido"} para recinto {recinto.id_recinto if recinto else "desconocido"}. Motivo: {motivo}',
        extra={'tipo_operacion': 'RECHAZAR_SOLICITUD', 'modulo': 'SOLICITUDES'}
    )


    if usuario_solicitante and usuario_solicitante.email and recinto:
            numero_parcela = f"{recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}"
            
            enviar_notificacion_rechazo(
                destinatario=usuario_solicitante.email,
                nombre_usuario=usuario_solicitante.username,
                numero_parcela=numero_parcela,
                motivo_rechazo=motivo
            )

    
    flash("Solicitud rechazada.", "info")
    return redirect(url_for("admin.gestion_recintos"))


@admin_bp.route('/editar_usuario', methods=['POST'])
@login_required
def editar_usuario():
    try:
        # Obtener datos del formulario
        id_usuario = request.form.get('id_usuario')
        nuevo_username = request.form.get('username', '').strip()
        nuevo_email = request.form.get('email', '').strip()
        nuevo_telefono = request.form.get('telefono', '').strip()
        nuevo_rol = request.form.get('rol')
        nuevo_activo = 'activo' in request.form
        
        # Buscar el usuario
        usuario = User.query.get_or_404(id_usuario)
        
        # Validaciones básicas
        if not nuevo_username or not nuevo_email:
            flash('El nombre de usuario y el correo son obligatorios', 'danger')
            return redirect(url_for('admin.gestion_usuarios'))
        
        # Verificar si el username ya existe (excepto el del usuario actual)
        if nuevo_username != usuario.username:
            usuario_existente = User.query.filter_by(username=nuevo_username).first()
            if usuario_existente:
                flash('El nombre de usuario ya está en uso', 'danger')
                return redirect(url_for('admin.gestion_usuarios'))
        
        # Verificar si el email ya existe (excepto el del usuario actual)
        if nuevo_email != usuario.email:
            email_existente = User.query.filter_by(email=nuevo_email).first()
            if email_existente:
                flash('El correo electrónico ya está en uso', 'danger')
                return redirect(url_for('admin.gestion_usuarios'))
        
        # Validar y normalizar teléfono
        telefono_normalizado = None
        if nuevo_telefono:
            try:
                telefono_normalizado = normalizar_telefono_es(nuevo_telefono)
            except ValueError as e:
                flash(str(e), 'danger')
                logger.warning(
                    f'Formato de teléfono inválido en edición de usuario: {nuevo_telefono}',
                    extra={'tipo_operacion': 'EDICION_USUARIO', 'modulo': 'ADMIN'}
                )
                return redirect(url_for('admin.gestion_usuarios'))
        
        # Actualizar los datos del usuario
        usuario.username = nuevo_username
        usuario.email = nuevo_email
        usuario.telefono = telefono_normalizado
        usuario.rol = nuevo_rol
        usuario.activo = nuevo_activo
        
        # Guardar cambios en la base de datos
        db.session.commit()
        
        # Registrar el cambio en logs
        logger.info(
            f'Administrador editó el usuario {usuario.username} (ID: {id_usuario})',
            extra={'tipo_operacion': 'EDICION_USUARIO', 'modulo': 'ADMIN'}
        )
        
        flash('Usuario actualizado correctamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(
            f'Error al actualizar usuario: {str(e)}',
            extra={'tipo_operacion': 'EDICION_USUARIO', 'modulo': 'ADMIN'}
        )
        flash('Error al actualizar el usuario', 'danger')
    
    return redirect(url_for('admin.gestion_usuarios'))

@admin_bp.route('/recintos/<int:id_recinto>/editar', methods=['POST'])
@login_required
@admin_required
def editar_recinto_admin(id_recinto):
    recinto = Recinto.query.get_or_404(id_recinto)

    propietario_id = request.form.get('propietario_id')

    if propietario_id:
        recinto.id_propietario = propietario_id 
        recinto.nombre = request.form.get('nombre')
        logger.info(
            f'Administrador {current_user.username} asignó el propietario (ID: {propietario_id}) al recinto {recinto.id_recinto}',
            extra={'tipo_operacion': 'EDICION_RECINTO', 'modulo': 'SOLICITUDES'}
        )

    recinto.activa = bool(request.form.get('activa'))

    db.session.commit()
    flash('Recinto actualizado correctamente', 'success')

    return redirect(url_for('admin.gestion_recintos'))