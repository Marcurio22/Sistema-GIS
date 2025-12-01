// 1) Mapa base
const map = L.map("map").setView([41.95, -4.20], 11);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap"
}).addTo(map);

// 2) WMS SIGPAC (cascaded desde tu GeoServer)
const sigpacRecintos = L.tileLayer.wms(
  "http://100.102.237.86:8080/geoserver/gis_project/wms",
  {
    layers: "gis_project:recintos",
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

// --- Selección de mapa principal (satélite / NDVI) ---
document
  .querySelectorAll(".basemap-option.basemap-main[data-layer]")
  .forEach((option) => {
    option.addEventListener("click", () => {
      const layerKey = option.dataset.layer;
      if (!highZoomLayers[layerKey]) return;

      document
        .querySelectorAll(".basemap-option.basemap-main")
        .forEach((el) => el.classList.remove("active"));
      option.classList.add("active");

      activeHighLayerKey = layerKey;
      actualizarMapaSegunZoom();
    });
  });

// --- Toggle Recintos SigPac (nivel de detalle) ---
const recintosOption = document.querySelector(
  '.basemap-option.basemap-detail[data-detail="sigpac"]'
);
