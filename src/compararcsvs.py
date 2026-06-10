import pandas as pd
import numpy as np

CSV_ANTIGUO = r"C:\datos\salida\datoscultivos50_2026-03-01.csv"
CSV_NUEVO   = r"C:\datos\salida\datoscultivos60_2026-03-01.csv"

# Columnas a ignorar en la comparación (identificadores, geometría)
COLS_IGNORAR = {"id", "geometry_wkt"}

# Tolerancia para considerar que un número ha cambiado
TOLERANCIA = 0.001

# ------------------------------------------------------------

df_old = pd.read_csv(CSV_ANTIGUO, encoding="utf-8-sig")
df_new = pd.read_csv(CSV_NUEVO,   encoding="utf-8-sig")

print(f"📂 Antiguo : {len(df_old):,} filas  |  {len(df_old.columns)} columnas")
print(f"📂 Nuevo   : {len(df_new):,} filas  |  {len(df_new.columns)} columnas")

# ── Diferencias en columnas ───────────────────────────────────
cols_old = set(df_old.columns)
cols_new = set(df_new.columns)
if cols_old != cols_new:
    print(f"\n⚠️  Columnas solo en antiguo : {cols_old - cols_new}")
    print(f"⚠️  Columnas solo en nuevo   : {cols_new - cols_old}")
else:
    print("\n✅ Mismas columnas en ambos CSV.")

# ── Diferencias en número de filas ───────────────────────────
if len(df_old) != len(df_new):
    print(f"\n⚠️  Diferencia de filas: {len(df_new) - len(df_old):+,}")

# ── Comparar valores columna a columna ───────────────────────
cols_comparar = [c for c in df_old.columns if c in df_new.columns and c not in COLS_IGNORAR]
n_filas       = min(len(df_old), len(df_new))

print(f"\n📊 Comparando {len(cols_comparar)} columnas ({n_filas:,} filas)...\n")

resumen = []

for col in cols_comparar:
    serie_old = df_old[col].iloc[:n_filas]
    serie_new = df_new[col].iloc[:n_filas]

    # Columnas numéricas
    if pd.api.types.is_numeric_dtype(serie_old) and pd.api.types.is_numeric_dtype(serie_new):
        diff      = (serie_new - serie_old).abs()
        cambiados = (diff > TOLERANCIA).sum()
        if cambiados > 0:
            resumen.append({
                "columna":   col,
                "cambiados": cambiados,
                "diff_media": diff[diff > TOLERANCIA].mean(),
                "diff_max":   diff.max(),
            })
    # Columnas de texto
    else:
        cambiados = (serie_old.astype(str) != serie_new.astype(str)).sum()
        if cambiados > 0:
            resumen.append({
                "columna":   col,
                "cambiados": cambiados,
                "diff_media": "-",
                "diff_max":   "-",
            })

if not resumen:
    print("✅ Los dos CSV son idénticos (dentro de la tolerancia).")
else:
    df_res = pd.DataFrame(resumen).sort_values("cambiados", ascending=False)
    print(df_res.to_string(index=False))
    print(f"\n→ {len(resumen)} columna(s) con diferencias.")