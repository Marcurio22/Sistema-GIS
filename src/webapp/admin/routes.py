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
from sqlalchemy import or_, cast, String, text as sa_text

logger = logging.getLogger('app.admin')
logger.setLevel(logging.INFO)

db_handler = SQLAlchemyHandler()
formatter = logging.Formatter('%(levelname)s - %(message)s')
db_handler.setFormatter(formatter)
logger.addHandler(db_handler)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ['admin', 'superadmin']:
            logger.warning(
                f'Intento de acceso no autorizado al panel admin por: {current_user.username if current_user.is_authenticated else "an?nimo"}',
                extra={'tipo_operacion': 'ACCESO_DENEGADO', 'modulo': 'ADMIN'}
            )
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# verificar que es superadmin
def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'superadmin':
            logger.warning(
                f'Intento de acceso no autorizado a funci?n de superadmin por: {current_user.username if current_user.is_authenticated else "an?nimo"}',
                extra={'tipo_operacion': 'ACCESO_DENEGADO', 'modulo': 'SUPERADMIN'}
            )
            flash('Esta acci?n solo est? disponible para superadministradores.', 'danger')
            return redirect(url_for('admin.gestion_usuarios'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/usuarios')
@login_required
@admin_required
def gestion_usuarios():
    
    usuarios = User.query.order_by(
        User.rol.asc(),       
        User.activo.desc(),    
        User.id_usuario        
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
        f'Admin {current_user.username} activ? al usuario {usuario.username}',
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
        f'Admin {current_user.username} desactiv? al usuario {usuario.username}',
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
        f'Superadmin {current_user.username} promovi? a {usuario.username} a administrador',
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
        f'Superadmin {current_user.username} degrad? a {usuario.username} a usuario normal',
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
    
    # El superadmin que hace la promoci?n pasa a ser admin
    current_user.rol = 'admin'
    
    db.session.commit()
    
    logger.info(
        f'Superadmin {current_user.username} promovi? a {usuario.username} a superadministrador y pas? a ser admin',
        extra={'tipo_operacion': 'HACER_SUPERADMIN', 'modulo': 'SUPERADMIN'}
    )
    
    flash(f"{usuario.username} ahora es superadministrador. T? has pasado a ser administrador.", "success")
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
        flash("La solicitud ya est? procesada.", "warning")
        logger.warning(
            f'Admin {current_user.username} intent? aprobar solicitud {id_solicitud} ya procesada (estado: {solicitud.estado})',
            extra={'tipo_operacion': 'APROBAR_SOLICITUD_YA_PROCESADA', 'modulo': 'SOLICITUDES'}
        )
        return redirect(url_for("admin.gestion_recintos"))

    recinto = Recinto.query.get_or_404(solicitud.id_recinto)
    usuario_solicitante = User.query.get(solicitud.id_usuario)
    tipo = (solicitud.tipo_solicitud or "aceptacion").strip().lower()

    # ELIMINACI��N
    if tipo == "eliminacion":
        # Motivo SOLO aplica a eliminaci?n 
        motivo = (getattr(solicitud, "motivo_solicitud", None) or "").strip()
        if not motivo:
            flash("No se puede aprobar una eliminaci?n sin motivo. Falta el motivo en la solicitud.", "danger")
            logger.warning(
                f'Admin {current_user.username} intent? aprobar eliminaci?n {id_solicitud} sin motivo',
                extra={'tipo_operacion': 'APROBAR_ELIMINACION_SIN_MOTIVO', 'modulo': 'SOLICITUDES'}
            )
            return redirect(url_for("admin.gestion_recintos"))

        # Liberar recinto
        recinto.id_propietario = None
        solicitud.estado = "aprobada"
        solicitud.fecha_resolucion = datetime.now(timezone.utc)

        # Borrar solicitud de aceptaci?n aprobada (si existe)
        solicitud_aceptacion = Solicitudrecinto.query.filter_by(
            id_usuario=solicitud.id_usuario,
            id_recinto=recinto.id_recinto,
            tipo_solicitud="aceptacion",
            estado="aprobada"
        ).first()

        if solicitud_aceptacion:
            db.session.delete(solicitud_aceptacion)
            logger.info(
                f'Se elimin? la solicitud de aceptaci?n {solicitud_aceptacion.id_solicitud} al aprobar la eliminaci?n {id_solicitud}',
                extra={'tipo_operacion': 'ELIMINAR_SOLICITUD_ACEPTACION', 'modulo': 'SOLICITUDES'}
            )

        db.session.commit()

        if usuario_solicitante and usuario_solicitante.email and usuario_solicitante.notificaciones_activas:
            numero_recinto = f"{recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}"
            direccion_recinto = f"Provincia: {recinto.provincia}, Municipio: {recinto.municipio}, Pol?gono: {recinto.poligono}, Parcela: {recinto.parcela}"
            enviar_notificacion_eliminacion_aceptada(
                destinatario=usuario_solicitante.email,
                nombre_usuario=usuario_solicitante.username,
                numero_recinto=numero_recinto,
                direccion_recinto=direccion_recinto
            )

        logger.info(
            f'Admin {current_user.username} aprob? solicitud de ELIMINACI��N {id_solicitud} '
            f'del usuario {usuario_solicitante.username if usuario_solicitante else "desconocido"} '
            f'para recinto {recinto.id_recinto} (Prov: {recinto.provincia}, Mun: {recinto.municipio}, '
            f'Pol: {recinto.poligono}, Par: {recinto.parcela}). Motivo: {motivo}',
            extra={'tipo_operacion': 'APROBAR_SOLICITUD_ELIMINACION', 'modulo': 'SOLICITUDES'}
        )

        flash("Recinto liberado correctamente. El propietario ha sido eliminado.", "success")
        return redirect(url_for("admin.gestion_recintos"))

    # Si ya tiene propietario distinto, rechazo autom?tico
    if recinto.id_propietario is not None and recinto.id_propietario != solicitud.id_usuario:
        solicitud.estado = "rechazada"
        solicitud.fecha_resolucion = datetime.now(timezone.utc)
        solicitud.motivo_rechazo = "El recinto ya tiene propietario."
        db.session.commit()

        logger.warning(
            f'Admin {current_user.username} rechaz? autom?ticamente solicitud {id_solicitud} '
            f'del usuario {usuario_solicitante.username if usuario_solicitante else "desconocido"} '
            f'para recinto {recinto.id_recinto} (ya ten?a propietario)',
            extra={'tipo_operacion': 'RECHAZO_AUTOMATICO_SOLICITUD', 'modulo': 'SOLICITUDES'}
        )

        flash("El recinto ya ten?a propietario. Solicitud rechazada.", "danger")
        return redirect(url_for("admin.gestion_recintos"))

    # Asignar propietario
    recinto.id_propietario = solicitud.id_usuario
    solicitud.estado = "aprobada"
    solicitud.fecha_resolucion = datetime.now(timezone.utc)
    db.session.commit()

    # Notificaci?n aceptaci?n
    if usuario_solicitante and usuario_solicitante.email and usuario_solicitante.notificaciones_activas:
        numero_recinto = f"{recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}"
        direccion_recinto = f"Provincia: {recinto.provincia}, Municipio: {recinto.municipio}, Pol?gono: {recinto.poligono}, Parcela: {recinto.parcela}"
        enviar_notificacion_aceptacion(
            destinatario=usuario_solicitante.email,
            nombre_usuario=usuario_solicitante.username,
            numero_recinto=numero_recinto,
            direccion_recinto=direccion_recinto
        )

    logger.info(
        f'Admin {current_user.username} aprob? solicitud de ACEPTACI��N {id_solicitud} '
        f'del usuario {usuario_solicitante.username if usuario_solicitante else "desconocido"} '
        f'para recinto {recinto.id_recinto} (Prov: {recinto.provincia}, Mun: {recinto.municipio}, '
        f'Pol: {recinto.poligono}, Par: {recinto.parcela})',
        extra={'tipo_operacion': 'APROBAR_SOLICITUD_ACEPTACION', 'modulo': 'SOLICITUDES'}
    )

    flash("Recinto asignado correctamente al usuario.", "success")
    return redirect(url_for("admin.gestion_recintos"))

@admin_bp.post("/gestion_recintos/<int:id_solicitud>/rechazar")
@login_required
@admin_required
def rechazar_solicitud_recinto(id_solicitud):
    solicitud = Solicitudrecinto.query.get_or_404(id_solicitud)

    if solicitud.estado != "pendiente":
        flash("La solicitud ya est? procesada.", "warning")
        logger.warning(
            f'Admin {current_user.username} intent? rechazar solicitud {id_solicitud} que ya estaba procesada (estado: {solicitud.estado})',
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
        f'Admin {current_user.username} rechaz? solicitud {id_solicitud} del usuario {usuario_solicitante.username if usuario_solicitante else "desconocido"} para recinto {recinto.id_recinto if recinto else "desconocido"}. Motivo: {motivo}',
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
        id_usuario = request.form.get('id_usuario')
        nuevo_username = request.form.get('username', '').strip()
        nuevo_email = request.form.get('email', '').strip()
        nuevo_telefono = request.form.get('telefono', '').strip()
        nueva_password = request.form.get('password', '').strip()
        nuevo_rol = request.form.get('rol')
        nuevo_activo = 'activo' in request.form
        
        # Buscar el usuario
        usuario = User.query.get_or_404(id_usuario)
        
        # Validaciones b?sicas
        if not nuevo_username or not nuevo_email:
            flash('El nombre de usuario y el correo son obligatorios', 'danger')
            return redirect(url_for('admin.gestion_usuarios'))
        
        # Verificar si el username ya existe (excepto el del usuario actual)
        if nuevo_username != usuario.username:
            usuario_existente = User.query.filter_by(username=nuevo_username).first()
            if usuario_existente:
                flash('El nombre de usuario ya est? en uso', 'danger')
                return redirect(url_for('admin.gestion_usuarios'))
        
        # Verificar si el email ya existe (excepto el del usuario actual)
        if nuevo_email != usuario.email:
            email_existente = User.query.filter_by(email=nuevo_email).first()
            if email_existente:
                flash('El correo electr?nico ya est? en uso', 'danger')
                return redirect(url_for('admin.gestion_usuarios'))
        
        # Validar y normalizar tel?fono
        telefono_normalizado = None
        if nuevo_telefono:
            try:
                telefono_normalizado = normalizar_telefono_es(nuevo_telefono)
            except ValueError as e:
                flash(str(e), 'danger')
                logger.warning(
                    f'Formato de tel?fono inv?lido en edici?n de usuario: {nuevo_telefono}',
                    extra={'tipo_operacion': 'EDICION_USUARIO', 'modulo': 'ADMIN'}
                )
                return redirect(url_for('admin.gestion_usuarios'))
        if nueva_password:
            usuario.set_password(nueva_password)
        
        usuario.username = nuevo_username
        usuario.email = nuevo_email
        usuario.telefono = telefono_normalizado
        usuario.rol = nuevo_rol
        usuario.activo = nuevo_activo
        db.session.commit()
        
        logger.info(
            f'Administrador edit? el usuario {usuario.username} (ID: {id_usuario})',
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
            f'Administrador {current_user.username} asign? el propietario (ID: {propietario_id}) al recinto {recinto.id_recinto}',
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
    productos_fega = ProductoFega.query.order_by(ProductoFega.descripcion.asc()).all()
    return render_template('admin/gestion_variedades.html', productos_fega=productos_fega)

@admin_bp.route('/gestion_cultivos')
@login_required
@admin_required
def gestion_cultivos():
    productos_fega = ProductoFega.query.order_by(ProductoFega.codigo.asc()).all()


    return render_template('admin/gestion_cultivos.html' , productos_fega=productos_fega)

@admin_bp.route('/crear_cultivo', methods=['POST'])
@login_required
@admin_required
def crear_cultivo():
    descripcion = request.form.get('nombre', '').strip()
    variedad_nombre = request.form.get('variedad', '').strip()

    if not descripcion:
        flash('La descripci?n del cultivo no puede estar vac?a.', 'danger')
        return redirect(url_for('admin.gestion_cultivos'))

    max_cod = db.session.query(db.func.max(ProductoFega.codigo)).scalar() or 0
    nuevo_codigo = int(max_cod) + 1

    nuevo_cultivo = ProductoFega(
        codigo=nuevo_codigo,
        descripcion=descripcion,
    )
    db.session.add(nuevo_cultivo)
    db.session.flush()

    if variedad_nombre:
        existente = Variedad.query.filter(
            db.func.lower(Variedad.nombre) == variedad_nombre.lower()
        ).first()
        if existente:
            flash(f'Cultivo creado, pero la variedad "{variedad_nombre}" ya exist?a.', 'warning')
        else:
            db.session.add(Variedad(
                nombre=variedad_nombre,
                producto_fega_id=nuevo_cultivo.codigo,
            ))
            flash('Cultivo y variedad creados correctamente.', 'success')
            db.session.commit()
            return redirect(url_for('admin.gestion_cultivos'))

    db.session.commit()
    flash('Cultivo creado correctamente.', 'success')
    return redirect(url_for('admin.gestion_cultivos'))


@admin_bp.route('/crear_variedad', methods=['POST'])
@login_required
@admin_required
def crear_variedad():
    nombre = request.form.get('nombre', '').strip()
    producto_fega_id = request.form.get('producto_fega_id', type=int)

    if not nombre:
        flash('El nombre de la variedad no puede estar vac?o.', 'danger')
        return redirect(url_for('admin.gestion_variedades'))

    existente = Variedad.query.filter(
        db.func.lower(Variedad.nombre) == nombre.lower()
    ).first()
    if existente:
        flash(f'Ya existe una variedad llamada "{nombre}".', 'danger')
        return redirect(url_for('admin.gestion_variedades'))

    if producto_fega_id:
        cultivo = ProductoFega.query.get(producto_fega_id)
        if not cultivo:
            flash('El cultivo seleccionado no existe.', 'danger')
            return redirect(url_for('admin.gestion_variedades'))

    db.session.add(Variedad(
        nombre=nombre,
        producto_fega_id=producto_fega_id or None,
    ))
    db.session.commit()

    flash('Variedad creada correctamente.', 'success')
    return redirect(url_for('admin.gestion_variedades'))


@admin_bp.route('/eliminar_cultivo/<int:codigo>', methods=['POST'])
@login_required
@admin_required
def eliminar_cultivo(codigo):
    cultivo = ProductoFega.query.get_or_404(codigo)

    db.session.delete(cultivo)
    db.session.commit()

    flash('Cultivo eliminado correctamente.', 'success')
    return redirect(url_for('admin.gestion_cultivos'))

@admin_bp.route('/variedades/ajax', methods=['POST'])
@login_required
@admin_required
def obtener_variedades_ajax():
    try:
        draw = request.form.get('draw', type=int)
        start = request.form.get('start', type=int, default=0)
        length = request.form.get('length', type=int, default=25)
        search_value = request.form.get('search[value]', '')
        
        # Ordenamiento
        order_column_index = request.form.get('order[0][column]', type=int, default=2)
        order_dir = request.form.get('order[0][dir]', default='asc')
        
        # Mapeo de columnas
        columns = ['id_variedad', 'nombre', 'producto_fega_descripcion']  # CAMBIADO
        order_column = columns[order_column_index] if order_column_index < len(columns) else 'producto_fega_descripcion'
        
        # Query base con join
        query = db.session.query(Variedad).outerjoin(
            ProductoFega, 
            Variedad.producto_fega_id == ProductoFega.codigo
        )
        
        # Filtro de b?squeda
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
        if order_column == 'producto_fega_descripcion':
            # Ordenamiento alfab?tico por descripci?n del producto
            if order_dir == 'asc':
                query = query.order_by(ProductoFega.descripcion.asc().nullslast())
            else:
                query = query.order_by(ProductoFega.descripcion.desc().nullslast())
        elif order_column == 'nombre':
            if order_dir == 'asc':
                query = query.order_by(Variedad.nombre.asc())
            else:
                query = query.order_by(Variedad.nombre.desc())
        else:  # id_variedad
            if order_dir == 'asc':
                query = query.order_by(Variedad.id_variedad.asc())
            else:
                query = query.order_by(Variedad.id_variedad.desc())
        
        # paginaci?n
        variedades = query.offset(start).limit(length).all()
        
        # total de registros sin filtrar
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
        print(f"Error en AJAX: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e)
        }), 500


@admin_bp.route('/fix-riego-deficit', methods=['POST'])
@login_required
def fix_riego_deficit():
    """
    Corrige las tablas riego_prediccion_* que tienen deficit_mm=0 por error de fórmula.
    Establece deficit_mm = riego_mm (ETc directamente) y recalcula color y m3_ha.
    """
    if current_user.rol not in ("admin", "superadmin"):
        return jsonify({"error": "Solo admins"}), 403

    resultados = {}
    for i in range(8):
        tabla = f"riego_prediccion_{i}"
        try:
            existe = db.session.execute(sa_text("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=:t
            """), {"t": tabla}).scalar()
            if not existe:
                break

            # Determinar si es día urgente (0/1) o moderado (2/3)
            es_urgente = tabla.endswith("_0") or tabla.endswith("_1")
            color_no_blue = "red" if es_urgente else "orange"
            db.session.execute(sa_text(f"""
                UPDATE public."{tabla}"
                SET
                    deficit_mm  = riego_mm,
                    m3_ha       = ROUND((riego_mm * 10)::numeric, 2),
                    litros_dia  = ROUND((riego_mm * superficie_ha * 10000)::numeric)::integer,
                    litros_txt  = CASE
                                    WHEN riego_mm <= 0 THEN ''
                                    WHEN (riego_mm * 10) >= 100
                                         THEN ROUND((riego_mm * 10)::numeric, 0)::text || ' m³/ha'
                                    ELSE ROUND((riego_mm * 10)::numeric, 1)::text || ' m³/ha'
                                  END,
                    color       = CASE
                                    WHEN riego_mm <= 2.0 THEN 'blue'
                                    ELSE '{color_no_blue}'
                                  END
            """))
            db.session.commit()

            n = db.session.execute(sa_text(f'SELECT COUNT(*) FROM public."{tabla}"')).scalar()
            rojos = db.session.execute(sa_text(f"SELECT COUNT(*) FROM public.\"{tabla}\" WHERE color='red'")).scalar()
            resultados[tabla] = {"filas": n, "rojos": rojos, "ok": True}
        except Exception as e:
            db.session.rollback()
            resultados[tabla] = {"error": str(e)}

    # Limpiar caché GeoServer para que los tiles se regeneren con litros_txt nuevo
    gs_base = current_app.config.get("GEOSERVER_BASE_URL", "").rstrip("/")
    gs_user = current_app.config.get("GEOSERVER_USER")
    gs_pass = current_app.config.get("GEOSERVER_PASSWORD")
    if gs_base and gs_user:
        import requests as _req
        for tabla in resultados:
            if resultados[tabla].get("ok"):
                try:
                    _req.delete(
                        f"{gs_base}/gwc/rest/layers/gis_project:{tabla}.json",
                        auth=(gs_user, gs_pass), timeout=5
                    )
                except Exception:
                    pass

    return jsonify(resultados)


@admin_bp.route('/fix-itacyl-codigos', methods=['POST'])
@login_required
def fix_itacyl_codigos():
    """Rellena uso_descripcion desde los CSV mcsncyl_{año}.csv cuando solo hay código."""
    if current_user.rol not in ("admin", "superadmin"):
        return jsonify({"error": "Solo admins"}), 403
    try:
        from pathlib import Path
        from ..utils.legend_loader import load_legend_from_csv

        base = Path(current_app.root_path) / "static" / "csv" / "legends"
        leyendas: dict[int, dict[str, str]] = {}
        for csv_file in base.glob("mcsncyl_*.csv"):
            try:
                anio = int(csv_file.stem.split("_")[-1])
                payload = load_legend_from_csv(str(csv_file))
                leyendas[anio] = {str(it["code"]): it["label"] for it in payload.get("items", [])}
            except Exception:
                continue

        rows = db.session.execute(sa_text("""
            SELECT id, año, uso_codigo
            FROM public.cultivo_historico_itacyl
            WHERE uso_descripcion IS NULL AND uso_codigo IS NOT NULL
        """)).mappings().all()

        actualizados = 0
        for row in rows:
            anio = int(row["año"])
            cod = str(row["uso_codigo"]).strip()
            desc = leyendas.get(anio, {}).get(cod)
            if desc:
                db.session.execute(sa_text("""
                    UPDATE public.cultivo_historico_itacyl
                    SET uso_descripcion = :desc
                    WHERE id = :id
                """), {"desc": desc, "id": row["id"]})
                actualizados += 1
        db.session.commit()
        return jsonify({"ok": True, "filas_actualizadas": actualizados})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/debug-riego')
@login_required
def debug_riego():
    """Diagnóstico rápido del estado de las tablas de riego. Solo admins."""
    if current_user.rol not in ("admin", "superadmin"):
        return jsonify({"error": "Solo admins"}), 403

    info: dict = {}

    for tabla in ("riego_prediccion_0", "riego_prediccion_1",
                  "etp_prediccion_0", "etp_prediccion_1"):
        try:
            n = db.session.execute(
                sa_text(f'SELECT COUNT(*) FROM public."{tabla}"')
            ).scalar()
            sample = db.session.execute(
                sa_text(f'SELECT etp, kc, riego_mm, deficit_mm, color, fecha '
                        f'FROM public."{tabla}" LIMIT 3')
            ).mappings().all()
            info[tabla] = {
                "filas": n,
                "muestra": [dict(r) for r in sample],
            }
        except Exception as e:
            info[tabla] = {"error": str(e)}

    # Recintos del usuario actual con join
    try:
        rows = db.session.execute(sa_text("""
            SELECT r.id_recinto, r.nombre,
                   rp.etp, rp.kc, rp.riego_mm, rp.deficit_mm, rp.color
            FROM public.recintos r
            LEFT JOIN LATERAL (
                SELECT rp2.etp, rp2.kc, rp2.riego_mm,
                       rp2.deficit_mm, rp2.color
                FROM public.riego_prediccion_0 rp2
                WHERE ST_Intersects(r.geom, rp2.geometry)
                ORDER BY COALESCE(ST_Area(ST_Intersection(r.geom, rp2.geometry)), 0) DESC
                LIMIT 1
            ) rp ON true
            WHERE r.id_propietario = :uid
            LIMIT 10
        """), {"uid": current_user.id_usuario}).mappings().all()
        info["join_usuario"] = [dict(r) for r in rows]
    except Exception as e:
        info["join_usuario"] = {"error": str(e)}

    return jsonify(info)


@admin_bp.route("/plan-cultivo")
@login_required
@admin_required
def admin_plan_cultivo():
    from ..dashboard.routes import _datos_plan_cultivo

    recintos = (
        Recinto.query
        .filter(Recinto.id_propietario.isnot(None))
        .order_by(Recinto.id_propietario, Recinto.poligono, Recinto.parcela, Recinto.recinto)
        .all()
    )
    user_ids = {r.id_propietario for r in recintos if r.id_propietario}
    usuarios = {
        u.id_usuario: u.username
        for u in User.query.filter(User.id_usuario.in_(user_ids)).all()
    } if user_ids else {}

    plan, total_ha = _datos_plan_cultivo(recintos, usuarios_por_id=usuarios)
    return render_template(
        "plan_cultivo.html",
        plan=plan,
        total_ha=total_ha,
        n_usuarios=len(usuarios),
        es_admin=True,
        volver_url=url_for("admin.gestion_recintos"),
        descargar_shp_url=url_for("admin.admin_plan_cultivo_descargar_shp"),
    )


@admin_bp.route("/plan-cultivo/descargar-shp")
@login_required
@admin_required
def admin_plan_cultivo_descargar_shp():
    from ..dashboard.routes import _features_plan_cultivo_shp, _respuesta_zip_plan_cultivo

    try:
        import geopandas  # noqa: F401
        from shapely.geometry import shape  # noqa: F401
    except ImportError:
        return jsonify({"error": "geopandas/shapely no disponible en el servidor"}), 500

    try:
        features = _features_plan_cultivo_shp(uid=None, incluir_usuario=True)
    except Exception:
        logger.exception("Error leyendo geometrías admin para SHP")
        return jsonify({"error": "No se pudieron leer las geometrías"}), 500

    try:
        return _respuesta_zip_plan_cultivo(features, download_name="plan_cultivo_global.zip")
    except Exception:
        logger.exception("Error generando SHP plan cultivo admin")
        return jsonify({"error": "Error generando el shapefile"}), 500