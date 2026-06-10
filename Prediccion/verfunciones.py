import pefile

pe = pefile.PE(r"C:\Users\Instalador\Documents\Sistema-GIS-main\Prediccion\DllRiegos64.dll")

for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    print(exp.ordinal, exp.name)