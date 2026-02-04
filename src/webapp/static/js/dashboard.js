/* Dashboard minimap preview (robusto) */

(function () {
  function safeParseStartView() {
    try {
      const el = document.getElementById("dashboard-start-view");
      if (el && el.textContent) return JSON.parse(el.textContent);
    } catch (e) {}
    return {};
  }

  function toBBoxParam(bounds) {
    const w = bounds.getWest();
    const s = bounds.getSouth();
    const e = bounds.getEast();
    const n = bounds.getNorth();
    return [w, s, e, n].map((v) => Number(v).toFixed(6)).join(",");
  }

  function showFallbackPreview(el) {
    // Preview simple si Leaflet o tiles no van finos
    el.innerHTML = `
      <div class="dashboard-map-fallback">
        <div class="dashboard-map-fallback-inner">
          <div class="fw-semibold">Preview de situación</div>
          <div class="text-muted small">No se pudo renderizar el mapa aquí.</div>
        </div>
      </div>
    `;
  }

  function initSituacionMap() {
    const el = document.getElementById("dashboard-sit-map");
    if (!el) return;

    if (el.querySelector("img")) return;
    if (el.querySelector(".dashboard-map-fallback")) return;

    if (typeof L === "undefined") {
      showFallbackPreview(el);
      return;
    }

    // --- A partir de aquí, lógica de Leaflet (solo si no hay imagen estática) ---

    // Crear mapa
    const map = L.map(el, {
      zoomControl: false,
      attributionControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      tap: false,
    });

    // Tiles (retina y crossOrigin para evitar artefactos raros)
    const tiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      detectRetina: true,
      crossOrigin: true,
    }).addTo(map);

    // Si falla la carga de tiles -> fallback
    let tileErrorCount = 0;
    tiles.on("tileerror", function () {
      tileErrorCount += 1;
      if (tileErrorCount >= 6) {
        try {
          map.remove();
        } catch (e) {}
        showFallbackPreview(el);
      }
    });

    const start = safeParseStartView();
    const bbox = Array.isArray(start.bbox) && start.bbox.length === 4 ? start.bbox : null;
    const center =
      start.center && typeof start.center.lat === "number" && typeof start.center.lng === "number"
        ? [start.center.lat, start.center.lng]
        : [41.95, -4.2];
    const zoom = typeof start.zoom_sugerido === "number" ? start.zoom_sugerido : 11;

    let boundsToUse = null;

    if (bbox) {
      // bbox en 4326: [minx, miny, maxx, maxy]
      boundsToUse = L.latLngBounds([
        [bbox[1], bbox[0]],
        [bbox[3], bbox[2]],
      ]);
      map.fitBounds(boundsToUse, { padding: [12, 12] });
      L.rectangle(boundsToUse, { color: "#198754", weight: 2, fill: false }).addTo(map);
    } else {
      map.setView(center, zoom);
    }

    const geo = L.geoJSON(null, {
      style: { color: "#198754", weight: 2, fillOpacity: 0 },
    }).addTo(map);

    // MUY IMPORTANTE: invalidar size tras layout final (evita tiles rotos)
    function stabilize() {
      try {
        map.invalidateSize(true);
      } catch (e) {}
    }

    // 1) al cargar DOM
    setTimeout(stabilize, 50);
    // 2) tras primer “frame” de navegador
    requestAnimationFrame(() => setTimeout(stabilize, 50));
    // 3) y un poco más tarde por si Bootstrap termina de ajustar
    setTimeout(stabilize, 300);

    // Redimensionado
    window.addEventListener("resize", () => {
      setTimeout(stabilize, 100);
    });

    const fetchBounds = boundsToUse || map.getBounds();
    const bboxParam = toBBoxParam(fetchBounds);

    fetch(`/api/mis-recintos?bbox=${encodeURIComponent(bboxParam)}`, { credentials: "same-origin" })
      .then((r) => r.json())
      .then((fc) => {
        if (fc && fc.type === "FeatureCollection" && Array.isArray(fc.features)) {
          geo.addData(fc);
          // estabilizar otra vez tras pintar geometrías
          setTimeout(stabilize, 50);
        }
      })
      .catch(() => {
        // silencioso
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSituacionMap);
  } else {
    initSituacionMap();
  }
})();