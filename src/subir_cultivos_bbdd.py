import pandas as pd
# ── CAMBIO: sustituido psycopg2 por SQLAlchemy ──────────────────────────────
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from webapp.config import Config

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)
# ────────────────────────────────────────────────────────────────────────────

# ── CAMBIO: devuelve sesión SQLAlchemy ───────────────────────────────────────
def conectar_bd():
    """Establece conexión con PostgreSQL"""
    try:
        session = Session()
        session.execute(text("SELECT 1"))  # ping de comprobación
        print("✓ Conexión exitosa")
        return session
    except Exception as e:
        print(f"✗ Error: {e}")
        return None
# ────────────────────────────────────────────────────────────────────────────

def importar_variedades(ruta_csv):
    """Importa variedades desde CSV"""
    
    # Leer CSV (con comas como separador)
    df = pd.read_csv(ruta_csv, encoding='utf-8')
    df.columns = df.columns.str.strip()
    
    # Conectar
    session = conectar_bd()
    if not session:
        return
    
    insertados = 0

    # ── CAMBIO: session.execute(text(...)) en lugar de cursor.execute ─────────
    for _, row in df.iterrows():
        try:
            producto_fega_id = int(row['Código cultivo'])
            nombre = row['Variedad/ Especie/ Tipo'].strip()
            
            # Saltar "SIN VARIEDAD" si quieres
            if nombre.upper() == 'SIN VARIEDAD':
                continue
            
            session.execute(
                text("INSERT INTO variedad (nombre, producto_fega_id) VALUES (:nombre, :producto_fega_id)"),
                {"nombre": nombre, "producto_fega_id": producto_fega_id}
            )
            insertados += 1
            
        except Exception as e:
            print(f"✗ Error: {e}")

    session.commit()
    session.close()
    # ─────────────────────────────────────────────────────────────────────────
    
    print(f"\n✓ {insertados} variedades insertadas")


# Ejecutar
importar_variedades('C:\\Users\\Instalador\\Downloads\\variedades.csv')