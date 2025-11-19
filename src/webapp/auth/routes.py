from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from .. import db, login_manager
from ..models import User
from ..utils.logging_handler import SQLAlchemyHandler
import logging

auth_bp = Blueprint('auth', __name__)

# Configuración del logger
logger = logging.getLogger('app.auth')
logger.setLevel(logging.INFO)

# Handler a la base de datos
db_handler = SQLAlchemyHandler()
formatter = logging.Formatter('%(levelname)s - %(message)s')
db_handler.setFormatter(formatter)
logger.addHandler(db_handler)


# Login manager
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Rutas
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user is None:
            new_user = User(username=username, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            logger.info(
                f'Usuario {username} registrado exitosamente',
                extra={'tipo_operacion': 'REGISTRO', 'modulo': 'AUTH'}
            )
            
            flash('Registro exitoso. Por favor, inicia sesión.', 'success')
            return redirect(url_for('auth.login'))
        else:
            logger.warning(
                f'Intento de registro con username existente: {username}',
                extra={'tipo_operacion': 'REGISTRO', 'modulo': 'AUTH'}
            )
            flash('El nombre de usuario ya existe.', 'danger')
            
    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            logger.info(
                f'Login exitoso: {username}',
                extra={'tipo_operacion': 'LOGIN', 'modulo': 'AUTH'}
            )
            return redirect(url_for('auth.dashboard'))
        else:
            logger.warning(
                f'Intento de login fallido: {username}',
                extra={'tipo_operacion': 'LOGIN', 'modulo': 'AUTH'}
            )
            flash('Usuario o contraseña incorrectos', 'danger')

    return render_template('login.html')


@auth_bp.route('/dashboard')
@login_required
def dashboard():
    logger.info(
        f'Usuario {current_user.username} accedió al dashboard',
        extra={'tipo_operacion': 'ACCESO', 'modulo': 'DASHBOARD'}
    )
    return render_template('dashboard.html', username=current_user.username)


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
    return render_template('perfil.html', user=current_user)


@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))




