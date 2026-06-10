import ctypes, os

carpeta = os.getcwd()
os.chdir(carpeta)
lib = ctypes.CDLL(os.path.join(carpeta, "DllRiegos64.dll"))

func = lib.DLLObtenerModelo
func.restype = ctypes.c_int

modelox = os.path.join(carpeta, "BARBECHO_TRADICIONAL_Ent.dat")
modeloy = os.path.join(carpeta, "dat.bin")
modeloz = os.path.join(carpeta, "dat.txt")


buf_entrada = ctypes.create_unicode_buffer(modelox)
buf_modelo  = ctypes.create_unicode_buffer(modeloy, 512)
buf_salida  = ctypes.create_unicode_buffer(modeloz, 512)

func.argtypes = [
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p
]

try:
    r = func(buf_entrada, buf_modelo, buf_salida)
    print("RET:", r)
    print("Modelo creado:", os.path.exists(modeloy))
    print("TXT creado:", os.path.exists(modeloz))
except OSError as e:
    print("Falló:", e)