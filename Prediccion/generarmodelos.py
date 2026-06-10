# entrenar_modelos.py
import ctypes, os
import pandas as pd
from datetime import datetime, timedelta

CARPETA_DLL = r"C:\Users\Instalador\Documents\Sistema-GIS-main\prediccion"
CARPETA_MOD = r"C:\Users\Instalador\Documents\Sistema-GIS-main\prediccion\modelosPred"

FECHA = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
CSV =         r"C:\datos\salida\datoscultivospred" + FECHA + ".csv"

os.makedirs(CARPETA_MOD, exist_ok=True)

lib  = ctypes.CDLL(os.path.join(CARPETA_DLL, "DllRiegos64.dll"))
func = lib.DLLObtenerModelo
func.restype  = ctypes.c_int
func.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p]

cols_entrada = (
    [f"Tp_t-{i}" for i in range(14, 3, -1)] +
    [f"Hd_t-{i}" for i in range(14, 3, -1)] +
    [f"Ev_t-{i}" for i in range(14, 3, -1)]
)
cols_salida = ["Ev_t-3", "Ev_t-2", "Ev_t-1", "Ev_t"]

df  = pd.read_csv(CSV)
dat_tmp = os.path.join(CARPETA_DLL, "_tmp_ent.dat")

ok, err, skip = 0, 0, 0

for cultivo, grupo in df.groupby("Cl"):
    grupo_limpio = grupo[cols_entrada + cols_salida].dropna()
    if len(grupo_limpio)  < 6:
        print(f"⚠️  {cultivo}: solo {len(grupo_limpio)} filas válidas, saltando")
        skip += 1
        continue

    bin_mod = os.path.join(CARPETA_MOD, f"{cultivo}.bin")
    txt_mod = os.path.join(CARPETA_MOD, f"{cultivo}.txt")

    grupo_limpio = grupo_limpio.round(3)
    grupo_limpio.to_csv(dat_tmp, sep=" ", index=False, header=False, 
                        decimal=".", float_format="%.3f")
    r = func(
        ctypes.create_unicode_buffer(dat_tmp, 512),
        ctypes.create_unicode_buffer(bin_mod, 512),
        ctypes.create_unicode_buffer(txt_mod, 512)
    )

    if r == 0:
        print(f"✅ {cultivo}: {len(grupo_limpio)} parcelas")
        ok += 1
    else:
        print(f"❌ {cultivo}: error DLL código {r}")
        err += 1

print(f"\n✅ OK: {ok}  ❌ Error: {err}  ⚠️ Saltados: {skip}  Total: {ok+err+skip}")