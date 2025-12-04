# app/utils.py
import re
import os
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




