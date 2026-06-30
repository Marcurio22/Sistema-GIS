# -*- coding: utf-8-sig -*-
import ctypes
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from project_paths import DATOS_SALIDA_DIR, MODELOS_PRED_DIR, PREDICCION_DLL_DIR, SALIDA_PRED_DIR  # noqa: E402

CARPETA_DLL    = str(PREDICCION_DLL_DIR)
CARPETA_MOD    = str(MODELOS_PRED_DIR)
CARPETA_SALIDA = str(SALIDA_PRED_DIR)
FECHA = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
CSV_ENTRADA = str(DATOS_SALIDA_DIR / f"datoscultivospred{FECHA}.csv")

# ─────────────────────────────────────────
# FECHAS
# En producción cambia FECHA_CSV por:
#   FECHA_CSV = (datetime.today() + timedelta(days=3)).strftime("%Y-%m-%d")
# ─────────────────────────────────────────
FECHA_CSV = FECHA

FECHA_DT  = datetime.strptime(FECHA_CSV, "%Y-%m-%d")
HOY       = FECHA_DT + timedelta(days=1)  

dia = {
    "ET_t-3": HOY.strftime("%d/%m"),                          # +1
    "ET_t-2": (HOY + timedelta(days=1)).strftime("%d/%m"),    # +2
    "ET_t-1": (HOY + timedelta(days=2)).strftime("%d/%m"),    # +3
    "ET_t":   (HOY + timedelta(days=3)).strftime("%d/%m"),    # +4
}

print(f"📅 Fecha CSV           : {FECHA_CSV}")
print(f"   Predicciones para   : {list(dia.values())}\n")

# ─────────────────────────────────────────
# CARGAR DLL
# ─────────────────────────────────────────
lib  = ctypes.CDLL(os.path.join(CARPETA_DLL, "DllRiegos64.dll"))
func = lib.DLLPrediccionFichero
func.restype  = ctypes.c_int
func.argtypes = [
    ctypes.c_bool,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_int,
    ctypes.c_wchar_p,
]

# ─────────────────────────────────────────
# COLUMNAS
# ─────────────────────────────────────────

cols_entrada = (
    [f"Tp_t-{i}" for i in range(10, 0, -1)] + ["Tp_t"] + 
    [f"Hd_t-{i}" for i in range(10, 0, -1)] + ["Hd_t"] +
    [f"Ev_t-{i}" for i in range(10, 0, -1)] + ["Ev_t"]
)



# ─────────────────────────────────────────
# LEER CSV
# ─────────────────────────────────────────
print(f"📂 Leyendo CSV: {CSV_ENTRADA}")
df = pd.read_csv(CSV_ENTRADA)
print(f"   {len(df):,} parcelas — {df['Cl'].nunique()} cultivos\n")

os.makedirs(CARPETA_SALIDA, exist_ok=True)
dat_tmp = os.path.join(CARPETA_SALIDA, "_tmp_ent.dat")
sal_tmp = os.path.join(CARPETA_SALIDA, "_tmp_sal.txt")

# ─────────────────────────────────────────
# PREDECIR POR CULTIVO
# ─────────────────────────────────────────
resultados          = []
ok, sin_modelo, err = 0, 0, 0



# comprueba cuáles faltan
faltantes = [c for c in cols_entrada if c not in df.columns]
if faltantes:
    print(f"\n❌ Faltan estas columnas: {faltantes}")
else:
    print("\n✅ Todas las columnas presentes")
    
for cultivo, grupo in df.groupby("Cl"):
    modelo_bin = os.path.join(CARPETA_MOD, f"{cultivo}.bin")

    if not os.path.exists(modelo_bin):
        sin_modelo += 1
        continue

    grupo_limpio = grupo.dropna(subset=cols_entrada)
    if len(grupo_limpio) == 0:
        print(f"  ⚠️  {cultivo}: todas las filas tienen NaN, saltando")
        continue
    r = func(
        False,
        ctypes.create_unicode_buffer(modelo_bin, 512),
        ctypes.create_unicode_buffer(dat_tmp, 512),
        4,
        ctypes.create_unicode_buffer(sal_tmp, 512),
    )
    df_tmp = grupo_limpio[cols_entrada].round(3)
    df_tmp.to_csv(
        dat_tmp, sep=" ", index=False, header=False, float_format="%.3f"
    )

    r = func(
        False,
        ctypes.create_unicode_buffer(modelo_bin, 512),
        ctypes.create_unicode_buffer(dat_tmp, 512),
        4,
        ctypes.create_unicode_buffer(sal_tmp, 512),
    )

    bin_ok = os.path.exists(sal_tmp) and os.path.getsize(sal_tmp) > 0
    if not bin_ok:
        print(f"  ❌ {cultivo}: la DLL no generó salida")
        err += 1
        continue

    preds = pd.read_csv(sal_tmp, sep=r"\s+", header=None,
                        names=["ET_t-3", "ET_t-2", "ET_t-1", "ET_t"])
    preds.index = grupo_limpio.index

    preds["Cl"]           = cultivo
    preds["Rg"]           = grupo_limpio["Rg"].values
    preds["Ev_t"]         = grupo_limpio["Ev_t"].values
    preds["geometry_wkt"] = grupo_limpio["geometry_wkt"].values

    resultados.append(preds)
    print(f"  ✅ {cultivo}: {len(preds):,} parcelas")
    ok += 1

# ─────────────────────────────────────────
# GUARDAR RESULTADO
# ─────────────────────────────────────────
print(f"\n✅ OK: {ok}  ❌ Error: {err}  ⚠️  Sin modelo: {sin_modelo}")

if not resultados:
    print("❌ No hay resultados que guardar.")
else:
    df_pred = pd.concat(resultados).reset_index(drop=True)

    # Renombrar columnas con fechas reales
    df_pred = df_pred.rename(columns={
        "ET_t-3": f"ET_{dia['ET_t-3']}",
        "ET_t-2": f"ET_{dia['ET_t-2']}",
        "ET_t-1": f"ET_{dia['ET_t-1']}",
        "ET_t":   f"ET_{dia['ET_t']}",
    })

    # Orden final: Cl, Rg, ET cols, geometry_wkt al final
    cols_et = [c for c in df_pred.columns if c.startswith("ET_")]
    df_pred = df_pred[["Cl", "Rg", "Ev_t"] + cols_et + ["geometry_wkt"]]

    ruta_sal = os.path.join(
        CARPETA_SALIDA,
        f"predicciones_{FECHA_DT.strftime('%Y-%m-%d')}.csv"
    )
    df_pred.to_csv(ruta_sal, index=False, encoding="utf-8-sig")

    print(f"\n💾 Guardado: {ruta_sal}")
    print(f"   {len(df_pred):,} parcelas × 4 días")
    print(f"   Columnas: {list(df_pred.columns)}")