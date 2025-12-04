# app/utils.py
import re
import pandas as pd
import pandas as pd
import os

class MunicipiosFinder:
    """Buscador de nombres de municipios por código de provincia y municipio."""
    
    def __init__(self):
        # Ruta fija al CSV
        base_dir = os.path.dirname(__file__)
        csv_path = os.path.join(base_dir, 'data', 'municipios.csv')
        
        # Cargar CSV
        self.df = pd.read_csv(csv_path, dtype={'CPRO': str, 'CMUN': str})
        
        # Limpiar y preparar datos
        self.df['CPRO'] = self.df['CPRO'].str.strip()
        self.df['CMUN'] = self.df['CMUN'].str.strip()
        self.df['NOMBRE'] = self.df['NOMBRE'].str.strip()
        self.df['CODIGO'] = self.df['CPRO'] + self.df['CMUN']
        
        # Índice para búsqueda rápida
        self.df.set_index('CODIGO', inplace=True)
    
    def obtener_nombre(self, cod_provincia, cod_municipio):
        """
        Obtiene el nombre del municipio.
        
        Args:
            cod_provincia: Código provincia (16 o '16')
            cod_municipio: Código municipio (51 o '051')
        
        Returns:
            Nombre del municipio o None si no existe
        """
        cpro = str(cod_provincia).zfill(2)
        cmun = str(cod_municipio).zfill(3)
        codigo = f"{cpro}{cmun}"
        
        try:
            return self.df.loc[codigo, 'NOMBRE']
        except KeyError:
            return None

def normalizar_telefono_es(valor: str) -> str:
    """
    Normaliza un teléfono español al formato +34XXXXXXXXX
    
    Args:
        valor: Teléfono en cualquier formato (666 76 86 33, +34666768633, etc.)
    
    Returns:
        Teléfono normalizado: +34XXXXXXXXX
    
    Raises:
        ValueError: Si el formato no es válido
    """

    solo_digitos_y_mas = re.sub(r'[^\d+]', '', valor)
    
    # Si empieza por +34
    if solo_digitos_y_mas.startswith('+34'):
        resto = re.sub(r'\D', '', solo_digitos_y_mas[3:])
        if len(resto) != 9:
            raise ValueError("El teléfono debe tener 9 dígitos después de +34")
        return f'+34{resto}'
    
    # Si empieza por 34 (sin el +)
    if solo_digitos_y_mas.startswith('34') and len(solo_digitos_y_mas) == 11:
        resto = solo_digitos_y_mas[2:]
        return f'+34{resto}'
    
    # Si son solo 9 dígitos (asumimos que es español)
    if len(solo_digitos_y_mas) == 9:
        return f'+34{solo_digitos_y_mas}'
    
    raise ValueError("Formato de teléfono no válido. Usa +34XXXXXXXXX o 9 dígitos")



