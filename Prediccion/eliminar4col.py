import pandas as pd
from pathlib import Path

ruta_entrada = input("Ruta del archivo .dat: ").strip()
ruta_entrada = Path(ruta_entrada)

df = pd.read_csv(ruta_entrada, sep='\s+', engine='python')
print(f"Columnas originales ({len(df.columns)}): {list(df.columns)}")

df = df.iloc[:, :-4]
print(f"Columnas tras eliminar las últimas 4 ({len(df.columns)}): {list(df.columns)}")

ruta_salida = ruta_entrada.with_stem(ruta_entrada.stem + "_modificado")
df.to_csv(ruta_salida, sep=' ', index=False)
print(f"Archivo guardado en: {ruta_salida}")