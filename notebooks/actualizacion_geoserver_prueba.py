import requests

### CONFIGURACIÓN ###
GEOSERVER = "http://100.102.237.86:8080/geoserver"
WORKSPACE = "gis_project"
DATASTORE = "sigpac.recintos"
CAPA = "recintos"    

USER = "admin"
PASSWORD = "geoserver"


# ----------------------------------------------------
# 1) Recargar datastore (GeoServer)
# ----------------------------------------------------
def recargar_datastore():
    url = f"{GEOSERVER}/rest/workspaces/{WORKSPACE}/datastores/{DATASTORE}/reload"
    r = requests.post(url, auth=(USER, PASSWORD))
    
    if r.status_code == 200:
        print("✔️ Datastore recargado OK")
    else:
        print("❌ Error:", r.status_code, r.text)


# ----------------------------------------------------
# 2) Recarga global de GeoServer
# ----------------------------------------------------
def recargar_geoserver():
    url = f"{GEOSERVER}/rest/reload"
    r = requests.post(url, auth=(USER, PASSWORD))

    if r.status_code == 200:
        print("✔️ GeoServer recargado OK")
    else:
        print("❌ Error recargando GeoServer:", r.status_code, r.text)


# ----------------------------------------------------
# EJECUCIÓN
# ----------------------------------------------------
if __name__ == "__main__":
    recargar_datastore()
    recargar_geoserver()
    print("✔️ Actualización de capa terminada")
