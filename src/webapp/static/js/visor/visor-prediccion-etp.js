(function () {

  document.addEventListener("DOMContentLoaded", function () {
    setTimeout(initPrediccionEtp, 300);
  });

  // ── Init ────────────────────────────────────────────────────────────────────
  function initPrediccionEtp() {

    const map = window.map;
    if (!map) { console.error("[PRED-ETP] window.map no encontrado."); return; }

    const GEOSERVER_WMS = window.GEOSERVER_WMS;
    if (!GEOSERVER_WMS) { console.error("[PRED-ETP] window.GEOSERVER_WMS no encontrado."); return; }

    const BASE_URL = "/static/etp_prediccion"; // solo para el indice.json
    const WORKSPACE = "gis_project";

    const btnPrediccion = document.querySelector('.basemap-option.basemap-main[data-layer="prediccion-etp"]');
    if (!btnPrediccion) { console.warn("[PRED-ETP] Botón no encontrado."); return; }

    if (!map.getPane("prediccionEtpPane")) {
      map.createPane("prediccionEtpPane");
      map.getPane("prediccionEtpPane").style.zIndex = 260;
    }

    let prediccionActivo = false;
    let offsetDias       = 0;
    let capaActual       = null;
    let indice           = {};
    const capasWMS       = {}; // cache de capas ya creadas

    // ── Cargar índice de fechas ───────────────────────────────────────────────
    async function cargarIndice() {
      try {
        const r = await fetch(`${BASE_URL}/indice.json`);
        indice = await r.json();
        actualizarBotonesDias();
      } catch (e) {
        console.error("[PRED-ETP] No se pudo cargar indice.json", e);
      }
    }

    function actualizarBotonesDias() {
      document.querySelectorAll(".pred-etp-opcion").forEach(el => {
        const offset = el.dataset.offset;
        if (indice[offset]) {
          const sub = el.querySelector(".pred-etp-opcion-fecha");
          if (sub) sub.textContent = indice[offset];
        }
      });
    }

    // ── Crear capa WMS ────────────────────────────────────────────────────────
    function crearCapaWMS(offset) {
      return L.tileLayer.wms(GEOSERVER_WMS, {
        layers:      `${WORKSPACE}:etp_prediccion_${offset}`,
        format:      "image/png",
        transparent: true,
        tiled:       true,
        pane:        "prediccionEtpPane",
        opacity:     1,
        maxZoom:     20,
        minZoom:     7,
        interactive: false
      });
    }

    // ── Cargar capa del día ───────────────────────────────────────────────────
    function cargarCapa(offset) {
      if (capaActual) { map.removeLayer(capaActual); capaActual = null; }

      // Reutiliza si ya se instanció antes
      if (!capasWMS[offset]) capasWMS[offset] = crearCapaWMS(offset);

      capaActual = capasWMS[offset];
      map.addLayer(capaActual);
    }

    // ── Popup al hacer click ──────────────────────────────────────────────────
    map.on("click", async function (e) {
      if (!prediccionActivo) return;

      const url = buildGetFeatureInfoUrl(e.latlng, offsetDias);
      try {
        const r    = await fetch(url);
        const data = await r.json();
        if (!data.features || data.features.length === 0) return;

        const p = data.features[0].properties;
        L.popup()
          .setLatLng(e.latlng)
          .setContent(`
            <strong>${p.cultivo}</strong><br>
            Riego: ${p.riego}<br>
            ET₀: <strong>${p.etp} mm/día</strong><br>
            Fecha: ${p.fecha}
          `)
          .openOn(map);
      } catch (e) {
        console.error("[PRED-ETP] Error GetFeatureInfo:", e);
      }
    });

    function buildGetFeatureInfoUrl(latlng, offset) {
      const size   = map.getSize();
      const bounds = map.getBounds();
      const point  = map.latLngToContainerPoint(latlng);

      return GEOSERVER_WMS +
        `?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo` +
        `&LAYERS=${WORKSPACE}:etp_prediccion_${offset}` +
        `&QUERY_LAYERS=${WORKSPACE}:etp_prediccion_${offset}` +
        `&INFO_FORMAT=application/json` +
        `&FEATURE_COUNT=1` +
        `&WIDTH=${size.x}&HEIGHT=${size.y}` +
        `&BBOX=${bounds.toBBoxString()}` +
        `&X=${Math.round(point.x)}&Y=${Math.round(point.y)}` +
        `&SRS=EPSG:4326`;
    }

    // ── Cambiar día ───────────────────────────────────────────────────────────
    function aplicarOffset(offset) {
      offsetDias = offset;

      document.querySelectorAll(".pred-etp-opcion").forEach(el => {
        el.classList.toggle("seleccionada", parseInt(el.dataset.offset) === offset);
      });

      const lbl = document.getElementById("pred-etp-fecha-label");
      if (lbl) lbl.textContent = indice[String(offset)] || "";

      if (prediccionActivo) cargarCapa(offset);
    }

    // ── Activar / desactivar ──────────────────────────────────────────────────
    function activar() {
      prediccionActivo = true;

      const panel = document.getElementById("pred-etp-panel");
      if (panel) panel.style.display = "block";

      cargarCapa(offsetDias);

      // ── Forzar mapa base: Imagen Satelital (OSM Standard / Esri) ─────────
      if (window.highZoomLayers && window.setActiveHighLayerKey && window.actualizarMapaSegunZoom) {
        window.setActiveHighLayerKey("satellite");
        window.actualizarMapaSegunZoom();

        // Sincronizar UI del selector de capa base
        document.querySelectorAll(".basemap-option.basemap-main")
          .forEach(el => el.classList.remove("active"));
        const btnSat = document.querySelector('.basemap-option.basemap-main[data-layer="satellite"]');
        if (btnSat) btnSat.classList.add("active");

        btnPrediccion.classList.add("active");  
      }

      // ── Activar capa temática: Cultivos SigPac ────────────────────────────
      // Requiere que visor.html exponga: window.activarDetalleExclusivo
      if (typeof window.activarDetalleExclusivo === "function") {
        window.activarDetalleExclusivo("cultivosSigpac");
      } else {
        console.warn("[PRED-ETP] window.activarDetalleExclusivo no disponible. " +
          "Añade 'window.activarDetalleExclusivo = activarDetalleExclusivo;' en visor.html.");
      }
    }

    function desactivar() {
      prediccionActivo = false;

      if (capaActual) { map.removeLayer(capaActual); capaActual = null; }

      const panel = document.getElementById("pred-etp-panel");
      if (panel) panel.style.display = "none";

      // ── Desactivar capa temática de cultivos al salir ─────────────────────
      if (typeof window.desactivarDetalle === "function") {
        window.desactivarDetalle("cultivosSigpac");
      }
    }

    // ── Eventos ───────────────────────────────────────────────────────────────
    btnPrediccion.addEventListener("click", function () {
      document.querySelectorAll(".basemap-option.basemap-main")
        .forEach(el => el.classList.remove("active"));
      btnPrediccion.classList.add("active");
      activar();
    });

    document.querySelectorAll(".basemap-option.basemap-main[data-layer]").forEach(btn => {
      if (btn.dataset.layer !== "prediccion-etp") {
        btn.addEventListener("click", () => { if (prediccionActivo) desactivar(); });
      }
    });

    document.addEventListener("click", function (e) {
      const opcion = e.target.closest(".pred-etp-opcion");
      if (!opcion) return;
      const offset = parseInt(opcion.dataset.offset);
      if (!isNaN(offset)) aplicarOffset(offset);
    });

    // ── Arranque ──────────────────────────────────────────────────────────────
    cargarIndice();
    _inyectarUI();
  }

  // ── UI ────────────────────────────────────────────────────────────────────
  function _inyectarUI() {
    if (document.getElementById("pred-etp-panel")) return;

    const html = `
    <style>
      #pred-etp-panel {
        display: none;
        margin-top: 10px;
        padding: 10px 12px;
        background: #eef4fb;
        border-radius: 8px;
        border: 1px solid #b6d4f5;
        user-select: none;
      }
      .pred-etp-panel-label {
        font-size: 0.82rem;
        font-weight: 600;
        color: #0a3d7a;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      #pred-etp-fecha-label {
        margin-left: auto;
        background: #1565c0;
        color: white;
        border-radius: 4px;
        padding: 1px 7px;
        font-size: 0.78rem;
      }
      .pred-etp-opciones {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 5px;
      }
      .pred-etp-opcion {
        cursor: pointer;
        text-align: center;
        padding: 6px 4px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        background: #d0e4f7;
        color: #0a3d7a;
        border: 2px solid transparent;
        transition: background 0.15s, border-color 0.15s;
        line-height: 1.3;
      }
      .pred-etp-opcion:hover { background: #a8ccee; }
      .pred-etp-opcion.seleccionada {
        background: #1565c0;
        color: white;
        border-color: #0a3d7a;
      }
      .pred-etp-opcion-dia   { font-size: 0.85rem; display: block; }
      .pred-etp-opcion-fecha { font-size: 0.70rem; display: block; opacity: 0.85; }
    </style>

    <div id="pred-etp-panel">
      <div class="pred-etp-panel-label">
        <i class="bi bi-cloud-sun"></i>
        Predicción ET₀
        <span id="pred-etp-fecha-label"></span>
      </div>
      <div class="pred-etp-opciones">
        <div class="pred-etp-opcion seleccionada" data-offset="0">
          <span class="pred-etp-opcion-dia">Hoy</span>
          <span class="pred-etp-opcion-fecha"></span>
        </div>
        <div class="pred-etp-opcion" data-offset="1">
          <span class="pred-etp-opcion-dia">+1 día</span>
          <span class="pred-etp-opcion-fecha"></span>
        </div>
        <div class="pred-etp-opcion" data-offset="2">
          <span class="pred-etp-opcion-dia">+2 días</span>
          <span class="pred-etp-opcion-fecha"></span>
        </div>
        <div class="pred-etp-opcion" data-offset="3">
          <span class="pred-etp-opcion-dia">+3 días</span>
          <span class="pred-etp-opcion-fecha"></span>
        </div>
      </div>
    </div>`;

    const grid = document.querySelector("#basemap-panel .basemap-grid");
    if (grid) grid.insertAdjacentHTML("afterend", html);
  }

})();