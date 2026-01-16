from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from . import admin_bp
from .. import db
from ..models import ProductoFega, User, Recinto, Solicitudrecinto, LogsSistema, Variedad
from datetime import datetime, timezone
import logging
from ..utils.utils import normalizar_telefono_es
from ..utils.logging_handler import SQLAlchemyHandler
from ..utils.email_service import enviar_notificacion_aceptacion, enviar_notificacion_rechazo, enviar_notificacion_eliminacion_aceptada
from flask import request, jsonify, render_template
from sqlalchemy import or_, cast, String

logger = logging.getLogger('app.admin')
logger.setLevel(logging.INFO)

db_handler = SQLAlchemyHandler()
formatter = logging.Formatter('%(levelname)s - %(message)s')
db_handler.setFormatter(formatter)
logger.addHandler(db_handler)

# Decorador para verificar que el usuario es admin o superadmin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ['admin', 'superadmin']:
            logger.warning(
                f'Intento de acceso no autorizado al panel admin por: {current_user.username if current_user.is_authenticated else "anónimo"}',
                extra={'tipo_operacion': 'ACCESO_DENEGADO', 'modulo': 'ADMIN'}
            )
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Decorador para verificar que el usuario es superadmin
def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'superadmin':
            logger.warning(
                f'Intento de acceso no autorizado a función de superadmin por: {current_user.username if current_user.is_authenticated else "anónimo"}',
                extra={'tipo_operacion': 'ACCESO_DENEGADO', 'modulo': 'SUPERADMIN'}
            )
            flash('Esta acción solo está disponible para superadministradores.', 'danger')
            return redirect(url_for('admin.gestion_usuarios'))
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
@superadmin_required
def hacer_admin(id):
    usuario = User.query.get_or_404(id)

    usuario.rol = 'admin'
    db.session.commit()
    flash(f"{usuario.username} ahora es administrador.", "success")

    logger.info(
        f'Superadmin {current_user.username} promovió a {usuario.username} a administrador',
        extra={'tipo_operacion': 'HACER_ADMIN', 'modulo': 'SUPERADMIN'}
    )

    return redirect(url_for('admin.gestion_usuarios'))



@admin_bp.route('/usuarios/<int:id>/quitar_admin')
@login_required
@superadmin_required
def quitar_admin(id):
    usuario = User.query.get_or_404(id)

    usuario.rol = 'user'
    db.session.commit()
    flash(f"{usuario.username} ahora es usuario normal.", "success")

    logger.info(
        f'Superadmin {current_user.username} degradó a {usuario.username} a usuario normal',
        extra={'tipo_operacion': 'QUITAR_ADMIN', 'modulo': 'SUPERADMIN'}
    )

    return redirect(url_for('admin.gestion_usuarios'))



@admin_bp.route('/usuarios/<int:id>/hacer_superadmin')
@login_required
@superadmin_required
def hacer_superadmin(id):
    usuario = User.query.get_or_404(id)
    
    if usuario.rol == 'superadmin':
        flash('Este usuario ya es superadministrador.', 'info')
        return redirect(url_for('admin.gestion_usuarios'))

    # Promover al usuario a superadmin
    usuario.rol = 'superadmin'
    
    # El superadmin que hace la promoción pasa a ser admin
    current_user.rol = 'admin'
    
    db.session.commit()
    
    logger.info(
        f'Superadmin {current_user.username} promovió a {usuario.username} a superadministrador y pasó a ser admin',
        extra={'tipo_operacion': 'HACER_SUPERADMIN', 'modulo': 'SUPERADMIN'}
    )
    
    flash(f"{usuario.username} ahora es superadministrador. Tú has pasado a ser administrador.", "success")
    return redirect(url_for('admin.gestion_usuarios'))


@admin_bp.route('/gestion_recintos')
@login_required
@admin_required
def gestion_recintos():

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

    # Determinar el tipo de solicitud
    tipo_solicitud = solicitud.tipo_solicitud

    if tipo_solicitud == "eliminacion":
        # SOLICITUD DE ELIMINACIÓN
        # Verificar que el usuario sea el propietario actual
       
        # Eliminar propietario (liberar recinto)
        recinto.id_propietario = None
        solicitud.estado = "aprobada"
        solicitud.fecha_resolucion = datetime.now(timezone.utc)
        
        # Eliminar la solicitud de aceptación anterior (si existe y está aprobada)
        solicitud_aceptacion = Solicitudrecinto.query.filter_by(
            id_usuario=solicitud.id_usuario,
            id_recinto=recinto.id_recinto,
            tipo_solicitud="aceptacion",
            estado="aprobada"
        ).first()
        
        print(solicitud_aceptacion)
        
        if solicitud_aceptacion:
            db.session.delete(solicitud_aceptacion)
            logger.info(
                f'Se eliminó la solicitud de aceptación {solicitud_aceptacion.id_solicitud} al aprobar la eliminación {id_solicitud}',
                extra={'tipo_operacion': 'ELIMINAR_SOLICITUD_ACEPTACION', 'modulo': 'SOLICITUDES'}
            )
        
        db.session.commit()

        # Enviar notificación de eliminación aprobada
        if usuario_solicitante and usuario_solicitante.email:
            numero_recinto = f"{recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}"
            direccion_recinto = f"Provincia: {recinto.provincia}, Municipio: {recinto.municipio}, Polígono: {recinto.poligono}, Parcela: {recinto.parcela}"
            

            if usuario_solicitante.notificaciones_activas == True:
                enviar_notificacion_eliminacion_aceptada(
                    destinatario=usuario_solicitante.email,
                    nombre_usuario=usuario_solicitante.username,
                    numero_recinto=numero_recinto,
                    direccion_recinto=direccion_recinto
                )
            
            
        logger.info(
            f'Admin {current_user.username} aprobó solicitud de eliminación {id_solicitud} del usuario {usuario_solicitante.username if usuario_solicitante else "desconocido"} para recinto {recinto.id_recinto} (Prov: {recinto.provincia}, Mun: {recinto.municipio}, Pol: {recinto.poligono}, Par: {recinto.parcela})',
            extra={'tipo_operacion': 'APROBAR_SOLICITUD_ELIMINACION', 'modulo': 'SOLICITUDES'}
        )
        
        flash("Recinto liberado correctamente. El propietario ha sido eliminado.", "success")
        
    else:  # tipo_solicitud == "aceptacion" o valor por defecto
        # SOLICITUD DE ACEPTACIÓN
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
        solicitud.estado = "aprobada"
        solicitud.fecha_resolucion = datetime.now(timezone.utc)

        db.session.commit()

        # Enviar notificación de aceptación
        if usuario_solicitante and usuario_solicitante.email:
            numero_recinto = f"{recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}"
            direccion_recinto = f"Provincia: {recinto.provincia}, Municipio: {recinto.municipio}, Polígono: {recinto.poligono}, Parcela: {recinto.parcela}"
            
            if usuario_solicitante.notificaciones_activas == True:
                enviar_notificacion_aceptacion(
                    destinatario=usuario_solicitante.email,
                    nombre_usuario=usuario_solicitante.username,
                    numero_recinto=numero_recinto,
                    direccion_recinto=direccion_recinto
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
            numero_recinto = f"{recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}"

            if usuario_solicitante.notificaciones_activas == True:
                enviar_notificacion_rechazo(
                    destinatario=usuario_solicitante.email,
                    nombre_usuario=usuario_solicitante.username,
                    numero_recinto=numero_recinto,
                    tipo_solicitud=solicitud.tipo_solicitud,
                    motivo_rechazo=motivo
                )

    
    flash("Solicitud rechazada.", "info")
    return redirect(url_for("admin.gestion_recintos"))


@admin_bp.route('/editar_usuario', methods=['POST'])
@login_required
@admin_required
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




@admin_bp.route('/solicitudes/ajax')
@login_required
# @admin_required
def obtener_solicitudes_ajax():
    try:
        solicitudes = Solicitudrecinto.query.order_by(
            Solicitudrecinto.fecha_solicitud.desc()
        ).all()
        
        # Contar solicitudes pendientes
        solicitudes_pendientes = sum(1 for s in solicitudes if s.estado == 'pendiente')
        
        # Renderizar el HTML de la tabla
        html = render_template('admin/partials/solicitudes_tabla.html', 
                             solicitudes=solicitudes)
        
        # Devolver JSON con el HTML y el contador
        return jsonify({
            'html': html,
            'solicitudes_pendientes': solicitudes_pendientes
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    

@admin_bp.route('/gestion_variedades')
@login_required
@admin_required
def gestion_variedades():

    return render_template('admin/gestion_variedades.html' )



@admin_bp.route('/variedades/ajax', methods=['POST'])
@login_required
@admin_required
def obtener_variedades_ajax():
    try:
        # Parámetros de DataTables
        draw = request.form.get('draw', type=int)
        start = request.form.get('start', type=int, default=0)
        length = request.form.get('length', type=int, default=25)
        search_value = request.form.get('search[value]', '')
        
        # Ordenamiento
        order_column_index = request.form.get('order[0][column]', type=int, default=2)
        order_dir = request.form.get('order[0][dir]', default='asc')
        
        # Mapeo de columnas
        columns = ['id_variedad', 'nombre', 'producto_fega_id']
        order_column = columns[order_column_index] if order_column_index < len(columns) else 'producto_fega_id'
        
        # Query base con join
        query = db.session.query(Variedad).outerjoin(
            ProductoFega, 
            Variedad.producto_fega_id == ProductoFega.codigo
        )
        
        # Filtro de búsqueda
        if search_value:
            query = query.filter(
                or_(
                    Variedad.nombre.ilike(f'%{search_value}%'),
                    ProductoFega.descripcion.ilike(f'%{search_value}%'),
                    cast(Variedad.id_variedad, String).ilike(f'%{search_value}%')
                )
            )
        
        # Total de registros filtrados
        records_filtered = query.count()
        
        # Ordenamiento
        if order_column == 'producto_fega_id':
            # Ordenamiento numérico correcto para cultivo
            if order_dir == 'asc':
                query = query.order_by(Variedad.producto_fega_id.asc().nullslast())
            else:
                query = query.order_by(Variedad.producto_fega_id.desc().nullslast())
        elif order_column == 'nombre':
            if order_dir == 'asc':
                query = query.order_by(Variedad.nombre.asc())
            else:
                query = query.order_by(Variedad.nombre.desc())
        else:
            if order_dir == 'asc':
                query = query.order_by(Variedad.id_variedad.asc())
            else:
                query = query.order_by(Variedad.id_variedad.desc())
        
        # Paginación
        variedades = query.offset(start).limit(length).all()
        
        # Total de registros sin filtrar
        records_total = Variedad.query.count()
        
        # Formatear datos
        data = []
        for variedad in variedades:
            data.append({
                'id_variedad': variedad.id_variedad,
                'nombre': variedad.nombre,
                'producto_fega_id': variedad.producto_fega_id if variedad.producto_fega_id else 0,
                'producto_fega_descripcion': variedad.producto_fega.descripcion if variedad.producto_fega else 'Sin cultivo',
                'cultivo': f"{variedad.producto_fega_id} - {variedad.producto_fega.descripcion}" if variedad.producto_fega else 'Sin cultivo'
            })
        
        return jsonify({
            'draw': draw,
            'recordsTotal': records_total,
            'recordsFiltered': records_filtered,
            'data': data
        })
    
    except Exception as e:
        # Log del error para debugging
        print(f"Error en AJAX: {str(e)}")
        return jsonify({
            'error': str(e)
        }), 500