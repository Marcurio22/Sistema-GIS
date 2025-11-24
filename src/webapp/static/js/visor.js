// 1) Mapa base
const map = L.map("map").setView([41.95, -4.20], 11);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap"
}).addTo(map);

// 2) WMS SIGPAC (cascaded desde tu GeoServer)
const sigpacRecintos = L.tileLayer.wms(
  "http://localhost:8080/geoserver/gis_project/wms",
  {
    layers: "AU.Sigpac:recinto",   // ⚠️ confirma nombre exacto en tu store
    format: "image/png",
    transparent: true,
    tiled: true
  }
).addTo(map);

// 3) Control de capas
const overlays = {
  "Recintos SIGPAC": sigpacRecintos
};
L.control.layers(null, overlays).addTo(map);
