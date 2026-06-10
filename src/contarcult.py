import pandas as pd

df = pd.read_csv(r"C:\datos\salida\datoscultivos33final2026-05-31.csv")
print(df['Cl'].value_counts())