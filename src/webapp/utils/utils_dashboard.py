# app/utils.py
import re
import pandas as pd
from pathlib import Path
import os

class MunicipiosFinder:
    """Buscador de nombres de municipios por código de provincia y municipio."""
    
    def __init__(self):
        # Ruta base
        base_dir = Path(__file__).parent.parent
        csv_dir = base_dir / 'static' / 'csv'
        
        # Cargar municipios
        self.df_municipios = pd.read_csv(
            csv_dir / 'nombres_municipios.csv', 
            skiprows=1, 
            dtype=str
        )
        self.df_municipios['CPRO'] = self.df_municipios['CPRO'].str.strip()
        self.df_municipios['CMUN'] = self.df_municipios['CMUN'].str.strip()
        self.df_municipios['NOMBRE'] = self.df_municipios['NOMBRE'].str.strip()
        self.df_municipios['CODIGO'] = self.df_municipios['CPRO'] + self.df_municipios['CMUN']
        self.df_municipios.set_index('CODIGO', inplace=True)
        
        # Cargar provincias
        self.df_provincias = pd.read_csv(
            csv_dir / 'nombres_provincias.csv', 
            dtype=str
        )
        self.df_provincias['CPRO'] = self.df_provincias['CPRO'].str.strip()
        self.df_provincias['NOMBRE'] = self.df_provincias['NOMBRE'].str.strip()
        self.df_provincias.set_index('CPRO', inplace=True)
    
    def obtener_nombre_municipio(self, cod_provincia, cod_municipio):
        """
        Obtiene el nombre del municipio y el nombre de la provincia.
        
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
            return self.df_municipios.loc[codigo, 'NOMBRE']
        except KeyError:
            return None
        
    def obtener_nombre_provincia(self, cod_provincia):
        """Obtiene el nombre de la provincia."""
        cpro = str(cod_provincia).zfill(2)
        
        try:
            return self.df_provincias.loc[cpro, 'NOMBRE']
        except KeyError:
            return None
        
        
        
municipios_finder = MunicipiosFinder()
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



