import ctypes, os

carpeta = os.getcwd()
os.chdir(carpeta)
lib = ctypes.CDLL(os.path.join(carpeta, "DllRiegos64.dll"))

func = lib.DLLPrediccionFichero
func.restype = ctypes.c_int
func.argtypes = [
    ctypes.c_bool,    
    ctypes.c_wchar_p, 
    ctypes.c_wchar_p,
    ctypes.c_int,     
    ctypes.c_wchar_p  
]

cadmodx = os.path.join(carpeta, "a.bin")
cadentx = os.path.join(carpeta, "BARBECHO TRADICIONAL_Tst 4col_modificado.dat")
cadsalx = os.path.join(carpeta, "resultadobin4col.txt")

buf_mod = ctypes.create_unicode_buffer(cadmodx,512)
buf_ent = ctypes.create_unicode_buffer(cadentx,512)
buf_sal = ctypes.create_unicode_buffer(cadsalx, 512)

try:
    r = func(False, buf_mod, buf_ent, 4, buf_sal)
    print("RET:", r)
    print("Resultado creado:", os.path.exists(cadsalx))
except OSError as e:
    print("Falló:", e)  