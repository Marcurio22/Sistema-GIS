import socket
import smtplib

def test_mailtrap_connection():
    """Prueba la conexión a Mailtrap"""
    
    host = 'sandbox.smtp.mailtrap.io'
    ports = [2525, 587, 465, 25]
    
    print("=" * 60)
    print("PROBANDO CONEXIÓN A MAILTRAP")
    print("=" * 60)
    
    # Prueba 1: Socket básico
    print("\n1. Probando conexión con socket...")
    for port in ports:
        try:
            print(f"   Puerto {port}...", end=" ")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                print("✓ ABIERTO")
            else:
                print("✗ CERRADO")
        except Exception as e:
            print(f"✗ ERROR: {e}")
    
    # Prueba 2: SMTP con autenticación
    print("\n2. Probando autenticación SMTP...")
    
    # Reemplaza con tus credenciales reales
    username = '4faeb7dbf380e7'
    password = '6189c***'  # Pon tu password completo aquí
    
    for port in [2525, 587]:
        try:
            print(f"\n   Puerto {port}:")
            print(f"   - Conectando...", end=" ")
            
            server = smtplib.SMTP(host, port, timeout=10)
            print("✓")
            
            print(f"   - EHLO...", end=" ")
            server.ehlo()
            print("✓")
            
            if port in [587, 2525]:
                print(f"   - STARTTLS...", end=" ")
                server.starttls()
                print("✓")
            
            print(f"   - Autenticando...", end=" ")
            server.login(username, password)
            print("✓")
            
            print(f"   ✓✓✓ PUERTO {port} FUNCIONA PERFECTAMENTE ✓✓✓")
            
            server.quit()
            return port  # Retorna el puerto que funciona
            
        except smtplib.SMTPAuthenticationError:
            print("✗ Error de autenticación (revisa username/password)")
        except socket.timeout:
            print("✗ Timeout (conexión muy lenta o bloqueada)")
        except ConnectionRefusedError:
            print("✗ Conexión rechazada (firewall o puerto bloqueado)")
        except Exception as e:
            print(f"✗ Error: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 60)
    print("RESUMEN:")
    print("Si ningún puerto funcionó, posibles causas:")
    print("  - Firewall de Windows bloqueando")
    print("  - Antivirus bloqueando")
    print("  - Red corporativa/escolar bloqueando SMTP")
    print("  - Credenciales de Mailtrap incorrectas")
    print("=" * 60)
    
    return None

if __name__ == "__main__":
    puerto_funcional = test_mailtrap_connection()
    
    if puerto_funcional:
        print(f"\n¡Usa el puerto {puerto_funcional} en tu .env!")
        print(f"MAIL_PORT={puerto_funcional}")