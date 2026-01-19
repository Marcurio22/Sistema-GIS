import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

# ========== CONFIGURACIÓN ==========
DB_CONFIG = {
    'host': 'localhost',
    'database': 'gisdb',
    'user': 'postgres',
    'password': 'postgres'
}

ARCHIVO = './webapp/static/csv/variedades.csv'  # o 'variedades.xlsx'
# ===================================

def conectar_db():
    """Conecta a PostgreSQL"""
    return psycopg2.connect(**DB_CONFIG)

def obtener_cultivos_existentes(conn):
    """Obtiene códigos y descripciones de cultivos en BD"""
    query = """
        SELECT codigo, UPPER(TRIM(descripcion)) as descripcion 
        FROM productos_fega
    """
    df = pd.read_sql(query, conn)
    # Retorna dict: {'TRIGO BLANDO': 1, 'CEBADA': 2, ...}
    return dict(zip(df['descripcion'], df['codigo']))

def obtener_variedades_existentes(conn):
    """Obtiene variedades ya en BD (nombre + producto_fega_id)"""
    query = """
        SELECT LOWER(TRIM(nombre)) as nombre, producto_fega_id 
        FROM variedades
    """
    df = pd.read_sql(query, conn)
    # Retorna set de tuplas: {('blat mort', 1), ('cebada', 2), ...}
    return set(zip(df['nombre'], df['producto_fega_id']))

def leer_archivo(ruta):
    """Lee CSV con encoding correcto"""
    return pd.read_csv(ruta, sep=';', encoding='windows-1252', quotechar='"')

def procesar_variedades(df, cultivos_bd):
    """
    Extrae variedades y las asocia con producto_fega_id
    Solo incluye cultivos que existen en BD
    """
    # Limpia espacios en columnas
    df.columns = df.columns.str.strip()
    
    # Normaliza nombres de cultivo
    df['Cultivo_norm'] = df['Cultivo'].str.strip().str.upper()
    df['Variedad_norm'] = df['Variedad/ Especie/ Tipo'].str.strip().str.upper()
    
    # Filtra: solo cultivos que existen en BD
    df_filtrado = df[df['Cultivo_norm'].isin(cultivos_bd.keys())].copy()
    
    print(f"\n📊 Estadísticas:")
    print(f"   • Total líneas en CSV: {len(df):,}")
    print(f"   • Cultivos en tu BD: {len(cultivos_bd)}")
    print(f"   • Líneas de cultivos existentes: {len(df_filtrado):,}")
    print(f"   • Líneas descartadas (cultivo no en BD): {len(df) - len(df_filtrado):,}")
    
    # Mapea cultivo -> codigo
    df_filtrado['producto_fega_id'] = df_filtrado['Cultivo_norm'].map(cultivos_bd)
    
    # Filtra variedades válidas
    df_filtrado = df_filtrado[
        (df_filtrado['Variedad_norm'].notna()) & 
        (df_filtrado['Variedad_norm'] != 'SIN VARIEDAD') &
        (df_filtrado['Variedad_norm'] != '')
    ]
    
    # Agrupa por variedad + cultivo (para evitar duplicados)
    resultado = df_filtrado.groupby(['Variedad_norm', 'producto_fega_id']).size().reset_index(name='count')
    
    # Retorna lista de tuplas: [(variedad, producto_fega_id), ...]
    return [(row['Variedad_norm'], row['producto_fega_id']) 
            for _, row in resultado.iterrows()]

def insertar_variedades(conn, nuevas_variedades):
    """Inserta las nuevas variedades en lote"""
    cursor = conn.cursor()
    
    # Obtiene el ID máximo actual
    cursor.execute("SELECT COALESCE(MAX(id_variedad), 0) FROM variedades")
    max_id = cursor.fetchone()[0]
    
    # Prepara datos: (id, nombre, producto_fega_id)
    datos = [(max_id + i + 1, nombre, prod_id) 
             for i, (nombre, prod_id) in enumerate(nuevas_variedades)]
    
    # Inserta en lote
    query = """
        INSERT INTO variedades (id_variedad, nombre, producto_fega_id)
        VALUES (%s, %s, %s)
    """
    execute_batch(cursor, query, datos, page_size=1000)
    conn.commit()
    cursor.close()
    
    return len(datos)

def main():
    print("🔄 Iniciando proceso de importación...")
    
    # 1. Conecta a BD
    print("🔗 Conectando a base de datos...")
    conn = conectar_db()
    
    # 2. Obtiene cultivos existentes en BD
    print("📦 Obteniendo cultivos en productos_fega...")
    cultivos_bd = obtener_cultivos_existentes(conn)
    print(f"   ✓ {len(cultivos_bd)} cultivos en BD")
    if len(cultivos_bd) <= 10:
        for cult, cod in list(cultivos_bd.items())[:10]:
            print(f"      • {cod}: {cult}")
    
    # 3. Obtiene variedades existentes
    print("\n📊 Obteniendo variedades existentes...")
    existentes = obtener_variedades_existentes(conn)
    print(f"   ✓ {len(existentes):,} variedades ya en BD")
    
    # 4. Lee el archivo
    print(f"\n📂 Leyendo {ARCHIVO}...")
    df = leer_archivo(ARCHIVO)
    
    # 5. Procesa y filtra variedades
    print("🔍 Procesando variedades del CSV...")
    variedades_csv = procesar_variedades(df, cultivos_bd)
    print(f"   ✓ {len(variedades_csv):,} combinaciones variedad+cultivo válidas")
    
    # 6. Filtra las nuevas (compara tuplas de nombre+producto_fega_id)
    nuevas = [(nombre, prod_id) for nombre, prod_id in variedades_csv
              if (nombre.lower(), prod_id) not in existentes]
    
    print(f"\n📌 {len(nuevas):,} variedades NUEVAS para insertar")
    
    if not nuevas:
        print("✅ ¡No hay nada que insertar!")
        conn.close()
        return
    
    # Muestra muestra por cultivo
    print("\nMuestra de nuevas variedades:")
    df_nuevas = pd.DataFrame(nuevas, columns=['Variedad', 'Cultivo_ID'])
    por_cultivo = df_nuevas.groupby('Cultivo_ID').size().sort_values(ascending=False)
    
    for cultivo_id, count in por_cultivo.head(5).items():
        # Busca nombre del cultivo
        cultivo_nombre = [k for k, v in cultivos_bd.items() if v == cultivo_id][0]
        print(f"\n  {cultivo_nombre} (ID {cultivo_id}): {count} nuevas")
        muestras = df_nuevas[df_nuevas['Cultivo_ID'] == cultivo_id]['Variedad'].head(3)
        for var in muestras:
            print(f"    • {var}")
    
    # Confirmación
    respuesta = input("\n¿Continuar con la inserción? (s/n): ")
    if respuesta.lower() != 's':
        print("❌ Cancelado")
        conn.close()
        return
    
    # 7. Inserta
    print("\n💾 Insertando variedades...")
    insertadas = insertar_variedades(conn, nuevas)
    
    print(f"✅ ¡{insertadas:,} variedades insertadas correctamente!")
    
    conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()