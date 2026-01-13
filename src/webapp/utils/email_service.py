"""
Servicio de envío de correos electrónicos
"""
from flask_mail import Message
from webapp import mail


def enviar_correo_prueba(destinatario):
    print(f"=" * 60)
    print(f"INICIANDO ENVÍO DE CORREO")
    print(f"=" * 60)
    print(f"Destinatario: {destinatario}")
    
    try:
        from flask import current_app
        from flask_mail import Message, Mail
        
        # Verificar configuración
        print("\n--- CONFIGURACIÓN DETECTADA ---")
        print(f"MAIL_SERVER: {current_app.config.get('MAIL_SERVER')}")
        print(f"MAIL_PORT: {current_app.config.get('MAIL_PORT')}")
        print(f"MAIL_USE_TLS: {current_app.config.get('MAIL_USE_TLS')}")
        print(f"MAIL_USE_SSL: {current_app.config.get('MAIL_USE_SSL')}")
        print(f"MAIL_USERNAME: {current_app.config.get('MAIL_USERNAME')}")
        print(f"MAIL_PASSWORD: {current_app.config.get('MAIL_PASSWORD')[:5]}***")
        print(f"MAIL_DEFAULT_SENDER: {current_app.config.get('MAIL_DEFAULT_SENDER')}")
        
        from webapp import mail
        print(f"\nObjeto mail: {mail}")
        print(f"Tipo: {type(mail)}")
        
        # HTML del mensaje bonito
        html_body = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                @media only screen and (max-width: 600px) {
                    .container {
                        width: 100% !important;
                        max-width: 100% !important;
                    }
                    .content {
                        padding: 20px !important;
                    }
                    .header {
                        padding: 20px !important;
                    }
                    h1 {
                        font-size: 20px !important;
                    }
                    .button {
                        padding: 10px 20px !important;
                        font-size: 14px !important;
                    }
                }
            </style>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td align="center" style="padding: 20px;">
                        <table class="container" width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            
                            <!-- Header -->
                            <tr>
                                <td class="header" style="background-color: #4CAF50; padding: 30px; text-align: center;">
                                    <h1 style="color: #ffffff; margin: 0; font-size: 24px;">✅ ¡Solicitud Aceptada!</h1>
                                </td>
                            </tr>
                            
                            <!-- Contenido -->
                            <tr>
                                <td class="content" style="padding: 30px;">
                                    <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 0 0 20px;">
                                        Hola <strong>Usuario</strong>,
                                    </p>
                                    
                                    <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 0 0 20px;">
                                        El administrador ha <strong style="color: #4CAF50;">aceptado tu solicitud</strong> de parcela. 
                                    </p>
                                    
                                    <!-- Info de la parcela -->
                                    <table width="100%" cellpadding="15" style="background-color: #f9f9f9; border-radius: 6px; margin: 20px 0;">
                                        <tr>
                                            <td>
                                                <p style="margin: 0 0 10px; color: #666; font-size: 14px;"><strong>📋 Detalles de tu Parcela</strong></p>
                                                <p style="margin: 5px 0; color: #333; font-size: 14px;"><strong>Número:</strong> P-2024-001</p>
                                                <p style="margin: 5px 0; color: #333; font-size: 14px;"><strong>Ubicación:</strong> Calle Principal 123, Sector Norte</p>
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 20px 0;">
                                        Ya puedes acceder a tu panel para gestionar tu parcela.
                                    </p>
                                    
                                    <!-- Botón -->
                                    <table cellpadding="0" cellspacing="0" style="margin: 20px 0;">
                                        <tr>
                                            <td align="center">
                                                <a href="http://100.102.237.86:5000/mis_recintos" class="button" style="background-color: #4CAF50; color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-size: 16px; display: inline-block;">
                                                    Ir a Mi Panel
                                                </a>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                                    <p style="color: #999; font-size: 12px; margin: 0;">
                                        © 2026 Sistema GIS - Correo automático
                                    </p>
                                </td>
                            </tr>
                            
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        text_body = """
        ¡Solicitud Aceptada!
        
        Hola Usuario,
        
        El administrador ha aceptado tu solicitud de parcela.
        
        Detalles:
        - Número: P-2024-001
        - Ubicación: Calle Principal 123, Sector Norte
        
        Accede a tu panel para más información.
        
        Saludos,
        Sistema GIS
        """
        
        # Crear mensaje
        print("\n--- CREANDO MENSAJE ---")
        msg = Message(
            subject="✅ Tu solicitud de parcela ha sido aceptada",
            recipients=[destinatario],
            body=text_body,
            html=html_body
        )
        print(f"Mensaje creado: {msg}")
        print(f"Subject: {msg.subject}")
        print(f"Recipients: {msg.recipients}")
        
        # Intentar enviar
        print("\n--- ENVIANDO CORREO ---")
        mail.send(msg)
        
        print("\n✓✓✓ CORREO ENVIADO EXITOSAMENTE ✓✓✓")
        print(f"=" * 60)
        return True
        
    except AttributeError as e:
        print(f"\n✗ ERROR de Atributo: {e}")
        print("Posible causa: mail no está inicializado correctamente")
        import traceback
        traceback.print_exc()
        return False
        
    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    

def enviar_notificacion_aceptacion(destinatario, nombre_usuario, numero_recinto, direccion_recinto):
    """
    Envía notificación cuando se acepta una solicitud de añadir recinto
    
    Args:
        destinatario: Email del usuario
        nombre_usuario: Nombre del usuario
        numero_recinto: Número o ID del recinto
        direccion_recinto: Dirección del recinto
    """
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @media only screen and (max-width: 600px) {{
                .container {{
                    width: 100% !important;
                    max-width: 100% !important;
                }}
                .content {{
                    padding: 20px !important;
                }}
                .header {{
                    padding: 20px !important;
                }}
                h1 {{
                    font-size: 20px !important;
                }}
                .button {{
                    padding: 10px 20px !important;
                    font-size: 14px !important;
                }}
            }}
        </style>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td align="center" style="padding: 20px;">
                    <table class="container" width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        
                        <!-- Header -->
                        <tr>
                            <td class="header" style="background-color: #4CAF50; padding: 30px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px;">✅ ¡Solicitud Aceptada!</h1>
                            </td>
                        </tr>
                        
                        <!-- Contenido -->
                        <tr>
                            <td class="content" style="padding: 30px;">
                                <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 0 0 20px;">
                                    Hola <strong>{nombre_usuario}</strong>,
                                </p>
                                
                                <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 0 0 20px;">
                                    El administrador ha <strong style="color: #4CAF50;">aceptado tu solicitud</strong> de recinto. 
                                </p>
                                
                                <!-- Info del recinto -->
                                <table width="100%" cellpadding="15" style="background-color: #f9f9f9; border-radius: 6px; margin: 20px 0;">
                                    <tr>
                                        <td>
                                            <p style="margin: 0 0 10px; color: #666; font-size: 14px;"><strong>📋 Detalles de tu Recinto</strong></p>
                                            <p style="margin: 5px 0; color: #333; font-size: 14px;"><strong>Número:</strong> {numero_recinto}</p>
                                            <p style="margin: 5px 0; color: #333; font-size: 14px;"><strong>Ubicación:</strong> {direccion_recinto}</p>
                                        </td>
                                    </tr>
                                </table>
                                
                                <!-- Botón -->
                                <table cellpadding="0" cellspacing="0" style="margin: 20px 0;">
                                    <tr>
                                        <td align="center">
                                            <a href="http://100.102.237.86:5000/mis_recintos" class="button" style="background-color: #4CAF50; color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-size: 16px; display: inline-block;">
                                                Ver mis recintos
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                                <p style="color: #999; font-size: 12px; margin: 0;">
                                    © 2026 Sistema GIS - Correo automático
                                </p>
                            </td>
                        </tr>
                        
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    text_body = f"""
    ¡Solicitud Aceptada!
    
    Hola {nombre_usuario},
    
    El administrador ha aceptado tu solicitud de recinto.
    
    Detalles:
    - Número: {numero_recinto}
    - Ubicación: {direccion_recinto}
    
    Accede a tu panel para más información.
    
    Saludos,
    Sistema GIS
    """
    
    try:
        from webapp import mail
        from flask_mail import Message
        
        msg = Message(
            subject="✅ Tu solicitud de recinto ha sido aceptada",
            recipients=[destinatario],
            body=text_body,
            html=html_body
        )
        
        mail.send(msg)
        print(f"✓ Notificación de aceptación enviada a {destinatario}")
        return True
        
    except Exception as e:
        print(f"✗ Error enviando notificación de aceptación: {e}")
        import traceback
        traceback.print_exc()
        return False


def enviar_notificacion_eliminacion_aceptada(destinatario, nombre_usuario, numero_recinto, direccion_recinto):
    """
    Envía notificación cuando el admin ACEPTA la solicitud de eliminación de recinto
    
    Args:
        destinatario: Email del usuario
        nombre_usuario: Nombre del usuario
        numero_recinto: Número o ID del recinto
        direccion_recinto: Dirección del recinto
    """
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @media only screen and (max-width: 600px) {{
                .container {{
                    width: 100% !important;
                    max-width: 100% !important;
                }}
                .content {{
                    padding: 20px !important;
                }}
                .header {{
                    padding: 20px !important;
                }}
                h1 {{
                    font-size: 20px !important;
                }}
                .button {{
                    padding: 10px 20px !important;
                    font-size: 14px !important;
                }}
            }}
        </style>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td align="center" style="padding: 20px;">
                    <table class="container" width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        
                        <!-- Header -->
                        <tr>
                            <td class="header" style="background-color: #ff9800; padding: 30px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px;">✅ Solicitud de Eliminación Aprobada</h1>
                            </td>
                        </tr>
                        
                        <!-- Contenido -->
                        <tr>
                            <td class="content" style="padding: 30px;">
                                <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 0 0 20px;">
                                    Hola <strong>{nombre_usuario}</strong>,
                                </p>
                                
                                <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 0 0 20px;">
                                    El administrador ha <strong style="color: #ff9800;">aceptado tu solicitud de eliminación</strong> de recinto.
                                </p>
                                
                                <!-- Info del recinto eliminado -->
                                <table width="100%" cellpadding="15" style="background-color: #f9f9f9; border-radius: 6px; margin: 20px 0;">
                                    <tr>
                                        <td>
                                            <p style="margin: 0 0 10px; color: #666; font-size: 14px;"><strong>📋 Recinto Eliminado</strong></p>
                                            <p style="margin: 5px 0; color: #333; font-size: 14px;"><strong>Número:</strong> {numero_recinto}</p>
                                            <p style="margin: 5px 0; color: #333; font-size: 14px;"><strong>Ubicación:</strong> {direccion_recinto}</p>
                                        </td>
                                    </tr>
                                </table>
                                
                                <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 20px 0;">
                                    El recinto ha sido eliminado del sistema. Si necesitas solicitar un nuevo recinto en el futuro, puedes hacerlo desde tu panel.
                                </p>
                                
                                <!-- Botón -->
                                <table cellpadding="0" cellspacing="0" style="margin: 20px 0;">
                                    <tr>
                                        <td align="center">
                                            <a href="http://100.102.237.86:5000/mis_recintos" class="button" style="background-color: #2196F3; color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-size: 16px; display: inline-block;">
                                                Ver mis recintos
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                                <p style="color: #999; font-size: 12px; margin: 0;">
                                    © 2026 Sistema GIS - Correo automático
                                </p>
                            </td>
                        </tr>
                        
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    text_body = f"""
    Solicitud de Eliminación Aprobada
    
    Hola {nombre_usuario},
    
    El administrador ha aceptado tu solicitud de eliminación de recinto.
    
    Recinto eliminado:
    - Número: {numero_recinto}
    - Ubicación: {direccion_recinto}
    
    El recinto ha sido eliminado del sistema.
    
    Saludos,
    Sistema GIS
    """
    
    try:
        from webapp import mail
        from flask_mail import Message
        
        msg = Message(
            subject="✅ Solicitud de eliminación aprobada",
            recipients=[destinatario],
            body=text_body,
            html=html_body
        )
        
        mail.send(msg)
        print(f"✓ Notificación de eliminación aceptada enviada a {destinatario}")
        return True
        
    except Exception as e:
        print(f"✗ Error enviando notificación de eliminación aceptada: {e}")
        import traceback
        traceback.print_exc()
        return False


def enviar_notificacion_rechazo(destinatario, nombre_usuario, numero_recinto, tipo_solicitud, motivo_rechazo=""):
    """
    Envía notificación cuando se rechaza una solicitud (tanto de creación como de eliminación)
    
    Args:
        destinatario: Email del usuario
        nombre_usuario: Nombre del usuario
        numero_recinto: Número o ID del recinto
        tipo_solicitud: 'creacion' o 'eliminacion'
        motivo_rechazo: Razón del rechazo (opcional)
    """
    
    # Textos según el tipo de solicitud
    if tipo_solicitud == 'eliminacion':
        texto_accion = "eliminación"
        emoji_estado = "ℹ️"
        color_header = "#2196F3"
        mensaje_estado = "Tu recinto <strong>permanece activo</strong> en el sistema."
        estado_recinto = '<p style="margin: 10px 0 0; color: #4CAF50; font-size: 14px;"><strong>Estado:</strong> Sigue activo</p>'
    else:  # creacion
        texto_accion = "creación"
        emoji_estado = "❌"
        color_header = "#f44336"
        mensaje_estado = "Puedes realizar una nueva solicitud o contactar con el administrador para más información."
        estado_recinto = ''
    
    # Si hay motivo, mostrarlo
    if motivo_rechazo:
        mensaje_motivo = f"""
        <table width="100%" cellpadding="15" style="background-color: #fff3cd; border-left: 4px solid #ffc107; border-radius: 6px; margin: 20px 0;">
            <tr>
                <td>
                    <p style="margin: 0; color: #856404; font-size: 14px;"><strong>💬 Motivo del rechazo:</strong></p>
                    <p style="margin: 5px 0 0; color: #856404; font-size: 14px;">{motivo_rechazo}</p>
                </td>
            </tr>
        </table>
        """
        texto_motivo = f"\n\nMotivo: {motivo_rechazo}"
    else:
        mensaje_motivo = ""
        texto_motivo = ""
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @media only screen and (max-width: 600px) {{
                .container {{
                    width: 100% !important;
                    max-width: 100% !important;
                }}
                .content {{
                    padding: 20px !important;
                }}
                .header {{
                    padding: 20px !important;
                }}
                h1 {{
                    font-size: 20px !important;
                }}
                .button {{
                    padding: 10px 20px !important;
                    font-size: 14px !important;
                }}
            }}
        </style>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td align="center" style="padding: 20px;">
                    <table class="container" width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        
                        <!-- Header -->
                        <tr>
                            <td class="header" style="background-color: {color_header}; padding: 30px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px;">{emoji_estado} Solicitud de {texto_accion.capitalize()} Rechazada</h1>
                            </td>
                        </tr>
                        
                        <!-- Contenido -->
                        <tr>
                            <td class="content" style="padding: 30px;">
                                <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 0 0 20px;">
                                    Hola <strong>{nombre_usuario}</strong>,
                                </p>
                                
                                <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 0 0 20px;">
                                    Tu solicitud de <strong>{texto_accion}</strong> del recinto <strong>{numero_recinto}</strong> no ha sido aprobada.
                                </p>
                                
                                <!-- Info del recinto -->
                                <table width="100%" cellpadding="15" style="background-color: #f9f9f9; border-radius: 6px; margin: 20px 0;">
                                    <tr>
                                        <td>
                                            <p style="margin: 0 0 10px; color: #666; font-size: 14px;"><strong>📋 Recinto</strong></p>
                                            <p style="margin: 5px 0; color: #333; font-size: 14px;"><strong>Número:</strong> {numero_recinto}</p>
                                            {estado_recinto}
                                        </td>
                                    </tr>
                                </table>
                                
                                {mensaje_motivo}
                                
                                <p style="color: #333; font-size: 16px; line-height: 1.5; margin: 20px 0;">
                                    {mensaje_estado}
                                </p>
                                
                                <!-- Botón -->
                                <table cellpadding="0" cellspacing="0" style="margin: 20px 0;">
                                    <tr>
                                        <td align="center">
                                            <a href="http://100.102.237.86:5000/mis_recintos" class="button" style="background-color: #2196F3; color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-size: 16px; display: inline-block;">
                                                Ver mis recintos
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                                <p style="color: #999; font-size: 12px; margin: 0;">
                                    © 2026 Sistema GIS - Correo automático
                                </p>
                            </td>
                        </tr>
                        
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    text_body = f"""
    Solicitud de {texto_accion.capitalize()} Rechazada
    
    Hola {nombre_usuario},
    
    Tu solicitud de {texto_accion} del recinto {numero_recinto} no ha sido aprobada.{texto_motivo}
    
    {mensaje_estado}
    
    Saludos,
    Sistema GIS
    """
    
    try:
        from webapp import mail
        from flask_mail import Message
        
        msg = Message(
            subject=f"{emoji_estado} Solicitud de {texto_accion} rechazada",
            recipients=[destinatario],
            body=text_body,
            html=html_body
        )
        
        mail.send(msg)
        print(f"✓ Notificación de rechazo de {texto_accion} enviada a {destinatario}")
        return True
        
    except Exception as e:
        print(f"✗ Error enviando notificación de rechazo: {e}")
        import traceback
        traceback.print_exc()
        return False