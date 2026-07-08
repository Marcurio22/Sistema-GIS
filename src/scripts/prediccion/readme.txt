para ejecutar

# 1) Una vez al dia (Planificador): API -> gisdb -> todas las comunidades
python -m scripts.prediccion.sync_meteo_global

# 2) Por cada comunidad: prediccion local (parcelas/cultivos de esa comunidad)
python -m scripts.prediccion.run_all

Variables utiles:
  METEO_ENV_FILE=C:\ruta\instancia-maestra\.env
  COMUNIDADES_ROOT=C:\GIS\comunidades
  REFERENCE_SOURCE_DB=gisdb   (en .env de cada comunidad)

desde src