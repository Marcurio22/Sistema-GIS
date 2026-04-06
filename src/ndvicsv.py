import pandas as pd

df = pd.read_csv('C:\\datos\\salida\\cultivospacheco_2026-03-01.csv')
filtrado = df[df['ndvi'] < 0]
filtrado.to_csv('ndvi_menor_0.csv', index=False)
print(f"Se encontraron {len(filtrado)} filas con NDVI < 0")