# app/filters.py
import re

def formato_tel_es(value: str) -> str:
    """
    Convierte '+34666768633' en '+34 666 76 86 33'
    Si no cumple el patrón esperado, devuelve el valor tal cual.
    """
    if not value:
        return ''
    
    # Esperamos +34 + 9 dígitos
    m = re.match(r'^\+34(\d{9})$', value)
    if not m:
        return value 
    
    num = m.group(1)  # '666768633'
    return f'+34 {num[0:3]} {num[3:5]} {num[5:7]} {num[7:9]}'