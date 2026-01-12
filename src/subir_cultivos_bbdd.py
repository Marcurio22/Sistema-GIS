import pandas as pd
import psycopg2
from psycopg2 import Error

def conectar_bd():
    """Establece conexión con PostgreSQL"""
    try:
        conexion = psycopg2.connect(
            host='localhost',
            database='gisdb',
            user='postgres',
            password='postgres',
            port='5432'
        )
        print("✓ Conexión exitosa")
        return conexion
    except Error as e:
        print(f"✗ Error: {e}")
        return None

def importar_variedades(ruta_csv):
    """Importa variedades desde CSV"""
    
    # Leer CSV (con comas como separador)
    df = pd.read_csv(ruta_csv, encoding='utf-8')
    df.columns = df.columns.str.strip()
    
    # Conectar
    conexion = conectar_bd()
    if not conexion:
        return
    
    cursor = conexion.cursor()
    insertados = 0
    
    for _, row in df.iterrows():
        try:
            producto_fega_id = int(row['Código cultivo'])
            nombre = row['Variedad/ Especie/ Tipo'].strip()
            
            # Saltar "SIN VARIEDAD" si quieres
            if nombre.upper() == 'SIN VARIEDAD':
                continue
            
            cursor.execute(
                "INSERT INTO variedad (nombre, producto_fega_id) VALUES (%s, %s)",
                (nombre, producto_fega_id)
            )
            insertados += 1
            
        except Exception as e:
            print(f"✗ Error: {e}")
    
    conexion.commit()
    cursor.close()
    conexion.close()
    
    print(f"\n✓ {insertados} variedades insertadas")


# Ejecutar
importar_variedades('C:\\Users\\Instalador\\Downloads\\variedades.csv')