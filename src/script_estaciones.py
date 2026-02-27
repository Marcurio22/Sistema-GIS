import requests
import pandas as pd
import json
from pyproj import Transformer

API_KEY = "eyJvcmciOiI2NTVmNzExNDc0N2I4OTAwMDE4NDIyMTQiLCJpZCI6IjhmYjEzYTk2MDFmMjQ3ODg5OTY4MGRmMmE0YmNjZjQ0IiwiaCI6Im11cm11cjEyOCJ9"
BASE = "https://gateway.api.itacyl.es/inforiego"
HEADERS = {"apikey": API_KEY}

transformer = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)

r = requests.get(f"{BASE}/cnt/rest/estaciones/", headers=HEADERS)
r.raise_for_status()

df = pd.DataFrame(r.json())
df = df.dropna(subset=["xpublicas", "ypublicas"])
df["lon"], df["lat"] = transformer.transform(df["xpublicas"].values, df["ypublicas"].values)

features = []
for _, row in df.iterrows():
    features.append({
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [row["lon"], row["lat"]]
        },
        "properties": {
            "idprovincia": row["idprovincia"],
            "idestacion": row["idestacion"],
            "nombre": row["sestacion"],
            "codigo": row["sestacioncorto"],
            "altitud": row["altitud"],
            "activa": row["fechafindatos"] is None,
        }
    })

geojson = {
    "type": "FeatureCollection",
    "features": features
}

with open("estaciones_todas.geojson", "w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False, indent=2)

print(f"Guardado estaciones_todas.geojson con {len(features)} estaciones")