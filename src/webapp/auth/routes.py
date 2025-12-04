from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from . import auth_bp 
from .. import db, login_manager
from sqlalchemy import desc
from ..models import LogsSistema, User
from ..utils.logging_handler import SQLAlchemyHandler
from ..utils.utils import normalizar_telefono_es
import logging
import re

# Configuración del logger
logger = logging.getLogger('app.auth')
logger.setLevel(logging.INFO)

# Handler a la base de datos
db_handler = SQLAlchemyHandler()
formatter = logging.Formatter('%(levelname)s - %(message)s')
db_handler.setFormatter(formatter)
logger.addHandler(db_handler)


@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    # Si el usuario existe pero no está activo, no lo cargues
    if user and not user.activo:
        return None
    return user

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        telefono = request.form.get('telefono')

        password_pattern = re.compile(
            r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
        )
        if not password_pattern.match(password):
            flash('La contraseña debe tener al menos 8 caracteres, incluir una mayúscula, una minúscula, un número y un carácter especial.', 'danger')
            return render_template('register.html', 
                                   username=username, 
                                   email=email, 
                                   telefono=telefono)

        # Validar usuario existente por username
        user_by_username = User.query.filter_by(username=username).first()
        if user_by_username:
            logger.warning(
                f'Intento de registro con username existente: {username}',
                extra={'tipo_operacion': 'REGISTRO', 'modulo': 'AUTH'}
            )
            flash('El nombre de usuario ya existe.', 'danger')
            return render_template('register.html', 
                                   username=username, 
                                   email=email, 
                                   telefono=telefono)

        # Validar usuario existente por email
        user_by_email = User.query.filter_by(email=email).first()
        if user_by_email:
            logger.warning(
                f'Intento de registro con email existente: {email}',
                extra={'tipo_operacion': 'REGISTRO', 'modulo': 'AUTH'}
            )
            flash('El correo electrónico ya está registrado.', 'danger')
            return render_template('register.html', 
                                   username=username, 
                                   email=email, 
                                   telefono=telefono)
        
        # Validar teléfono
        telefono_normalizado = None
        if telefono:
            try:
                telefono_normalizado = normalizar_telefono_es(telefono)
            except ValueError as e:
                flash(str(e), 'danger')
                logger.warning(
                    f'Formato de teléfono inválido en registro: {telefono}',
                    extra={'tipo_operacion': 'REGISTRO', 'modulo': 'AUTH'}
                )
                return render_template('register.html', 
                                       username=username, 
                                       email=email, 
                                       telefono=telefono)

        # Crear el usuario si todo es válido
        new_user = User(username=username, email=email, telefono=telefono_normalizado)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        logger.info(
            f'Usuario {username} registrado exitosamente',
            extra={'tipo_operacion': 'REGISTRO', 'modulo': 'AUTH'}
        )

        flash('Registro exitoso. Por favor, inicia sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            # Verificar si el usuario está activo
            if not user.activo:
                logger.warning(
                    f'Intento de login de usuario inactivo: {username}',
                    extra={'tipo_operacion': 'LOGIN', 'modulo': 'AUTH'}
                )
                flash('Tu cuenta está inactiva. Contacta al administrador para activarla.', 'danger')
                return render_template('login.html')
            
            login_user(user)
            logger.info(
                f'Login exitoso: {username}',
                extra={'tipo_operacion': 'LOGIN', 'modulo': 'AUTH'}
            )
            return redirect(url_for('dashboard.dashboard'))
        else:
            logger.warning(
                f'Intento de login fallido: {username}',
                extra={'tipo_operacion': 'LOGIN', 'modulo': 'AUTH'}
            )
            flash('Usuario o contraseña incorrectos', 'danger')

    return render_template('login.html')



@auth_bp.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    
    logger.info(
        f'Logout: {username}',
        extra={'tipo_operacion': 'LOGOUT', 'modulo': 'AUTH'}
    )
    
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/perfil')
@login_required
def perfil():
    # current_user viene de Flask-Login
    ultimo_log = LogsSistema.query.filter(
        LogsSistema.id_usuario == current_user.id_usuario,
        LogsSistema.modulo.in_(['DASHBOARD']),
        LogsSistema.tipo_operacion == 'ACCESO'
    ).order_by(desc(LogsSistema.fecha_hora)).first()

    logger.info(
        f'Usuario {current_user.username} accedió al perfil',
        extra={'tipo_operacion': 'ACCESO', 'modulo': 'PERFIL'}
    )
    return render_template('perfil.html', user=current_user, ultimo_acceso=ultimo_log.fecha_hora if ultimo_log else None)



@auth_bp.route('/perfil/actualizar', methods=['POST'])
@login_required
def actualizar():
    """Actualiza la información del usuario"""
    try:
        # Obtener datos del formulario
        nuevo_username = request.form.get('username', '').strip()
        nuevo_email = request.form.get('email', '').strip()
        nuevo_telefono = request.form.get('telefono', '').strip()
        
        # Validaciones básicas
        if not nuevo_username or not nuevo_email:
            flash('El nombre de usuario y el correo son obligatorios', 'danger')
            return redirect(url_for('auth.perfil'))
        
        # Verificar si el username ya existe (excepto el del usuario actual)
        if nuevo_username != current_user.username:
            usuario_existente = User.query.filter_by(username=nuevo_username).first()
            if usuario_existente:
                flash('El nombre de usuario ya está en uso', 'danger')
                return redirect(url_for('auth.perfil'))
        
        # Verificar si el email ya existe (excepto el del usuario actual)
        if nuevo_email != current_user.email:
            email_existente = User.query.filter_by(email=nuevo_email).first()
            if email_existente:
                flash('El correo electrónico ya está en uso', 'danger')
                return redirect(url_for('auth.perfil'))
        
        # Validar y normalizar teléfono (igual que en register)
        telefono_normalizado = None
        if nuevo_telefono:
            try:
                telefono_normalizado = normalizar_telefono_es(nuevo_telefono)
            except ValueError as e:
                flash(str(e), 'danger')
                logger.warning(
                    f'Formato de teléfono inválido en actualización de perfil: {nuevo_telefono}',
                    extra={'tipo_operacion': 'ACTUALIZACION', 'modulo': 'PERFIL'}
                )
                return redirect(url_for('auth.perfil'))
        
        # Actualizar los datos del usuario
        current_user.username = nuevo_username
        current_user.email = nuevo_email
        current_user.telefono = telefono_normalizado
        
        # Guardar cambios en la base de datos
        db.session.commit()
        
        # Registrar el cambio en logs
        logger.info(
            f'Usuario {current_user.username} actualizó su perfil',
            extra={'tipo_operacion': 'ACTUALIZACION', 'modulo': 'PERFIL'}
        )
        
        flash('Tu información ha sido actualizada correctamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(
            f'Error al actualizar perfil de {current_user.username}: {str(e)}',
            extra={'tipo_operacion': 'ERROR', 'modulo': 'PERFIL'}
        )
        flash(f'Error al actualizar la información: {str(e)}', 'danger')
    
    return redirect(url_for('auth.perfil'))


@auth_bp.route('/cambiar_contrasena', methods=['POST'])
@login_required
def cambiar_contrasena():
    """Permite al usuario cambiar su contraseña"""
    try:
        antigua_password = request.form.get('old_password', '').strip()
        nueva_password = request.form.get('new_password', '').strip()
        
        # Validar la contraseña antigua
        if not current_user.check_password(antigua_password):
            flash('La contraseña actual es incorrecta', 'danger')
            return redirect(url_for('auth.perfil'))
        
        # Validar la nueva contraseña
        password_pattern = re.compile(
            r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
        )
        if not password_pattern.match(nueva_password):
            flash('La nueva contraseña debe tener al menos 8 caracteres, incluir una mayúscula, una minúscula, un número y un carácter especial.', 'danger')
            return redirect(url_for('auth.perfil'))
        
        # Actualizar la contraseña
        current_user.set_password(nueva_password)
        db.session.commit()
        
        # Registrar el cambio en logs
        logger.info(
            f'Usuario {current_user.username} cambió su contraseña',
            extra={'tipo_operacion': 'CAMBIO_CONTRASENA', 'modulo': 'PERFIL'}
        )
        
        flash('Tu contraseña ha sido cambiada exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(
            f'Error al cambiar contraseña de {current_user.username}: {str(e)}',
            extra={'tipo_operacion': 'ERROR', 'modulo': 'PERFIL'}
        )
        flash(f'Error al cambiar la contraseña: {str(e)}', 'danger')
    
    return redirect(url_for('auth.perfil'))

@auth_bp.route('/')
@login_required
def index():
    return redirect(url_for('auth.login'))


@auth_bp.route('/mis_parcelas')
@login_required
def mis_parcelas():
    logger.info(
        f'Usuario {current_user.username} accedió a sus parcelas',
        extra={'tipo_operacion': 'ACCESO', 'modulo': 'MIS_PARCELAS'}
    )
    return render_template('mis_parcelas.html')