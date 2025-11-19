import logging
from datetime import datetime, timezone
from sqlalchemy.exc import SQLAlchemyError
from flask import has_request_context
from flask_login import current_user
from ..models import LogsSistema, db

class SQLAlchemyHandler(logging.Handler):
    """Handler de logging que guarda los logs en la base de datos."""

    def emit(self, record):
        try:
            mensaje = self.format(record)
            nivel = record.levelname
            tipo_operacion = getattr(record, 'tipo_operacion', 'GENERAL')
            modulo = getattr(record, 'modulo', 'GENERAL')
            datos_adicionales = getattr(record, 'datos_adicionales', None)

            if has_request_context() and current_user.is_authenticated:
                id_usuario = current_user.id_usuario
            else:
                id_usuario = None

            log_entry = LogsSistema(
                id_usuario=id_usuario,
                fecha_hora=datetime.now(timezone.utc),
                tipo_operacion=tipo_operacion,
                modulo=modulo,
                nivel=nivel,
                mensaje=mensaje,
                datos_adicionales=datos_adicionales
            )

            db.session.add(log_entry)
            db.session.commit()

        except SQLAlchemyError:
            db.session.rollback()
        except Exception:
            self.handleError(record)
