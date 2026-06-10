import pandas as pd
import os

CARPETA = r"C:\datos\salida"

fechas = [
    "2025-01-15",
    "2025-03-15", 
    "2025-06-15",
    "2025-09-15",
    "2025-11-15",
]

dfs = []
for f in fechas:
    ruta = os.path.join(CARPETA, f"datoscultivospred{f}.csv")
    df = pd.read_csv(ruta)
    df["fecha"] = f  # para saber de qué fecha viene cada fila
    dfs.append(df)
    print(f"✅ {f}: {len(df):,} filas")

df_todo = pd.concat(dfs).reset_index(drop=True)
df_todo = df_todo.drop(columns=["fecha", "Rf"], errors="ignore")
df_todo.insert(0, "Rf", df_todo.index + 1)

ruta_sal = os.path.join(CARPETA, "entrenamiento_anual.csv")
df_todo.to_csv(ruta_sal, index=False, encoding="utf-8-sig")

print(f"\n💾 Guardado: {ruta_sal}")
print(f"   {len(df_todo):,} filas totales")
print(f"   {df_todo['Cl'].nunique()} cultivos")