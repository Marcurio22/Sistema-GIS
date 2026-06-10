import pandas as pd
import numpy as np

CSV_ANTIGUO = r"C:\datos\salida\datoscultivos50_2026-03-01.csv"
CSV_NUEVO   = r"C:\datos\salida\datoscultivos60_2026-03-01.csv"
TOLERANCIA = 0.001

df_old = pd.read_csv(CSV_ANTIGUO)
df_new = pd.read_csv(CSV_NUEVO)

print(f"Antiguo: {len(df_old):,} filas")
print(f"Nuevo  : {len(df_new):,} filas")

# ── ¿Son exactamente las mismas filas en el mismo orden? ─────────────────
print("\n── Comprobando parc_sistexp ──")
if (df_old["parc_sistexp"].values == df_new["parc_sistexp"].values).all():
    print("✅ parc_sistexp idéntico en ambos — mismo orden de filas.")
else:
    print("❌ parc_sistexp DISTINTO — las filas no están alineadas.")
    print("   Primeras diferencias:")
    mask = df_old["parc_sistexp"].values != df_new["parc_sistexp"].values
    print(df_old[mask][["parc_sistexp"]].head(5))

# ── Ver filas concretas que cambian en tempmax ────────────────────────────
print("\n── Filas que cambian en tempmax ──")
diff_temp = (df_new["tempmax"] - df_old["tempmax"]).abs()
cambiadas = diff_temp > TOLERANCIA
print(f"  {cambiadas.sum():,} filas cambian")
if cambiadas.sum() > 0:
    muestra = df_old[cambiadas][["parc_sistexp", "cultivo"]].copy()
    muestra["tempmax_old"] = df_old.loc[cambiadas, "tempmax"].values
    muestra["tempmax_new"] = df_new.loc[cambiadas, "tempmax"].values
    muestra["diff"]        = diff_temp[cambiadas].values
    print(muestra.head(10).to_string(index=False))

# ── Ver filas concretas que cambian en ndvi ───────────────────────────────
print("\n── Filas que cambian en ndvi ──")
diff_ndvi = (df_new["ndvi"] - df_old["ndvi"]).abs()
cambiadas_ndvi = diff_ndvi > TOLERANCIA
print(f"  {cambiadas_ndvi.sum():,} filas cambian")
if cambiadas_ndvi.sum() > 0:
    muestra = df_old[cambiadas_ndvi][["parc_sistexp", "cultivo"]].copy()
    muestra["ndvi_old"] = df_old.loc[cambiadas_ndvi, "ndvi"].values
    muestra["ndvi_new"] = df_new.loc[cambiadas_ndvi, "ndvi"].values
    muestra["diff"]     = diff_ndvi[cambiadas_ndvi].values
    print(muestra.head(10).to_string(index=False))

# ── ¿Las filas que cambian en tempmax son las mismas que en ndvi? ─────────
print("\n── ¿Coinciden las filas que cambian en tempmax y ndvi? ──")
solo_temp = cambiadas & ~cambiadas_ndvi
solo_ndvi = cambiadas_ndvi & ~cambiadas
ambas     = cambiadas & cambiadas_ndvi
print(f"  Solo tempmax : {solo_temp.sum():,}")
print(f"  Solo ndvi    : {solo_ndvi.sum():,}")
print(f"  Ambas        : {ambas.sum():,}")

# ── ¿Hay filas donde TODO es diferente a la vez? ─────────────────────────
print("\n── Filas donde cambian 5 o más columnas numéricas a la vez ──")
cols_num = df_old.select_dtypes(include=[np.number]).columns.difference(["id"])
n_cambios_por_fila = sum(
    (df_new[c] - df_old[c]).abs() > TOLERANCIA
    for c in cols_num
    if c in df_new.columns
)
muchos_cambios = n_cambios_por_fila >= 5
print(f"  {muchos_cambios.sum():,} filas con 5+ columnas distintas")
if muchos_cambios.sum() > 0:
    print(df_old[muchos_cambios][["parc_sistexp", "cultivo"]].head(10).to_string(index=False))