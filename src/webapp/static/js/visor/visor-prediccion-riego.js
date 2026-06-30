(function () {

  window.addEventListener("load", function () {
    setTimeout(initPrediccionRiego, 500);
  });

  function initPrediccionRiego() {

    const map = window.map;
    if (!map) { console.error("[PRED-RIEGO] window.map no encontrado."); return; }

    const GEOSERVER_WMS = window.GEOSERVER_WMS;
    if (!GEOSERVER_WMS) { console.error("[PRED-RIEGO] window.GEOSERVER_WMS no encontrado."); return; }

    const BASE_URL  = "/static/riego_prediccion";
    const WORKSPACE = "gis_project";

    const btnPrediccion = document.querySelector('.basemap-option.basemap-main[data-layer="prediccion-riego"]');
    if (!btnPrediccion) { console.warn("[PRED-RIEGO] Botón no encontrado."); return; }

    if (!map.getPane("prediccionRiegoPane")) {
      map.createPane("prediccionRiegoPane");
      map.getPane("prediccionRiegoPane").style.zIndex = 261;
    }

    let prediccionActivo = false;
    let offsetDias       = 0;
    let capaActual       = null;
    let indice           = {};
    const capasWMS       = {};

    _inyectarUI();

    async function cargarIndice() {
      try {
        const r = await fetch(`${BASE_URL}/indice.json`);
        indice = await r.json();
        actualizarBotonesDias();
      } catch (e) {
        console.error("[PRED-RIEGO] No se pudo cargar indice.json", e);
      }
    }

    function actualizarBotonesDias() {
      document.querySelectorAll(".pred-riego-opcion").forEach(el => {
        const offset = el.dataset.offset;
        if (indice[offset]) {
          const sub = el.querySelector(".pred-riego-opcion-fecha");
          if (sub) sub.textContent = indice[offset];
        }
      });
    }

    function crearCapaWMS(offset) {
      const params = {
        layers:      `${WORKSPACE}:riego_prediccion_${offset}`,
        format:      "image/png",
        transparent: true,
        tiled:       true,
        pane:        "prediccionRiegoPane",
        opacity:     1,
        maxZoom:     20,
        minZoom:     7,
        interactive: false
      };

      if (window.CURRENT_USER_ID) {
        params.CQL_FILTER = `id_propietario=${window.CURRENT_USER_ID}`;
      }

      return L.tileLayer.wms(GEOSERVER_WMS, params);
    }

    function buildGetFeatureInfoUrl(latlng, offset) {
      const size   = map.getSize();
      const bounds = map.getBounds();
      const point  = map.latLngToContainerPoint(latlng);

      let url = GEOSERVER_WMS +
        `?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo` +
        `&LAYERS=${WORKSPACE}:riego_prediccion_${offset}` +
        `&QUERY_LAYERS=${WORKSPACE}:riego_prediccion_${offset}` +
        `&INFO_FORMAT=application/json` +
        `&FEATURE_COUNT=1` +
        `&WIDTH=${size.x}&HEIGHT=${size.y}` +
        `&BBOX=${bounds.toBBoxString()}` +
        `&X=${Math.round(point.x)}&Y=${Math.round(point.y)}` +
        `&SRS=EPSG:4326`;

      if (window.CURRENT_USER_ID) {
        url += `&CQL_FILTER=id_propietario=${window.CURRENT_USER_ID}`;
      }

      return url;
    }

    function cargarCapa(offset) {
      if (capaActual) { map.removeLayer(capaActual); capaActual = null; }
      if (!capasWMS[offset]) capasWMS[offset] = crearCapaWMS(offset);
      capaActual = capasWMS[offset];
      map.addLayer(capaActual);
    }

    map.on("click", async function (e) {
      if (!prediccionActivo) return;

      const url = buildGetFeatureInfoUrl(e.latlng, offsetDias);
      try {
        const r    = await fetch(url);
        const data = await r.json();
        if (!data.features || data.features.length === 0) return;

        const p = data.features[0].properties;
        const ndviTxt = (p.ndvi != null && p.ndvi !== "") ? p.ndvi : "—";
        const riegoMm = parseFloat(p.riego_mm);
        const deficitMm = parseFloat(p.deficit_mm);
        const m3Ha = parseFloat(p.m3_ha);
        const supHa = parseFloat(p.superficie_ha);
        let litros = parseInt(p.litros_dia, 10);
        if (!Number.isFinite(litros) && Number.isFinite(deficitMm) && Number.isFinite(supHa)) {
          litros = Math.round(deficitMm * supHa * 10000);
        }
        const deficitTxt = Number.isFinite(deficitMm)
          ? `${deficitMm.toLocaleString("es-ES", { maximumFractionDigits: 2 })} mm/día`
          : "—";
        const m3HaTxt = Number.isFinite(m3Ha) && m3Ha > 0
          ? `${m3Ha.toLocaleString("es-ES", { maximumFractionDigits: 1 })} m³/ha`
          : "—";
        const litrosTxt = Number.isFinite(litros) && litros > 0
          ? litros.toLocaleString("es-ES") + " L/día (total parcela)"
          : "—";
        const supTxt = Number.isFinite(supHa) ? `${supHa} ha` : "—";
        const urgencia = p.color === "red" || p.color === "orange"
          ? "Riego recomendado"
          : "Sin recomendación";
        L.popup()
          .setLatLng(e.latlng)
          .setContent(`
            <strong>${p.cultivo}</strong><br>
            Riego: ${p.riego}<br>
            Superficie: ${supTxt}<br>
            NDVI: ${ndviTxt}<br>
            Kc: <strong>${p.kc}</strong><br>
            ET₀: ${p.etp} mm/día<br>
            ETc: <strong>${p.riego_mm} mm/día</strong><br>
            Déficit: <strong>${deficitTxt}</strong><br>
            Aporte recomendado: <strong>${m3HaTxt}</strong><br>
            Volumen total: ${litrosTxt}<br>
            Estado: <strong>${urgencia}</strong><br>
            Fecha: ${p.fecha}
          `)
          .openOn(map);
      } catch (err) {
        console.error("[PRED-RIEGO] Error GetFeatureInfo:", err);
      }
    });

    function aplicarOffset(offset) {
      offsetDias = offset;

      document.querySelectorAll(".pred-riego-opcion").forEach(el => {
        el.classList.toggle("seleccionada", parseInt(el.dataset.offset) === offset);
      });

      const lbl = document.getElementById("pred-riego-fecha-label");
      if (lbl) lbl.textContent = indice[String(offset)] || "";

      if (prediccionActivo) cargarCapa(offset);
    }

    function activar() {
      prediccionActivo = true;

      const panel = document.getElementById("pred-riego-panel");
      if (panel) panel.style.display = "block";

      cargarCapa(offsetDias);

      if (window.highZoomLayers && window.setActiveHighLayerKey && window.actualizarMapaSegunZoom) {
        window.setActiveHighLayerKey("satellite");
        window.actualizarMapaSegunZoom();
      }

      document.querySelectorAll(".basemap-option.basemap-main")
        .forEach(el => el.classList.remove("active"));
      const btnSat = document.querySelector('.basemap-option.basemap-main[data-layer="satellite"]');
      if (btnSat) btnSat.classList.add("active");
      btnPrediccion.classList.add("active");

      if (typeof window.activarDetalleExclusivo === "function") {
        window.activarDetalleExclusivo("cultivosSigpac");
      }
    }

    function desactivar() {
      prediccionActivo = false;

      if (capaActual) { map.removeLayer(capaActual); capaActual = null; }

      const panel = document.getElementById("pred-riego-panel");
      if (panel) panel.style.display = "none";

      btnPrediccion.classList.remove("active");

      if (typeof window.desactivarDetalle === "function") {
        window.desactivarDetalle("cultivosSigpac");
      }
    }

    btnPrediccion.addEventListener("click", function () {
      if (prediccionActivo) {
        desactivar();
        return;
      }

      document.querySelectorAll(".basemap-option.basemap-main")
        .forEach(el => el.classList.remove("active"));
      btnPrediccion.classList.add("active");
      activar();
    });

    document.querySelectorAll(".basemap-option.basemap-main[data-layer]").forEach(btn => {
      if (btn.dataset.layer !== "prediccion-riego") {
        btn.addEventListener("click", () => { if (prediccionActivo) desactivar(); });
      }
    });

    document.addEventListener("click", function (e) {
      const opcion = e.target.closest(".pred-riego-opcion");
      if (!opcion) return;
      const offset = parseInt(opcion.dataset.offset);
      if (!isNaN(offset)) aplicarOffset(offset);
    });

    cargarIndice();

    const params = new URLSearchParams(window.location.search);
    if (params.get("modo") === "riego") {
      activar();
    }
  }

  function _inyectarUI() {
    if (document.getElementById("pred-riego-panel")) return;

    const html = `
    <style>
      #pred-riego-panel {
        display: none;
        margin-top: 10px;
        padding: 10px 12px;
        background: #f7faee;
        border-radius: 8px;
        border: 1px solid #c5dc6a;
        user-select: none;
      }
      .pred-riego-panel-label {
        font-size: 0.82rem;
        font-weight: 600;
        color: #5a7503;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      #pred-riego-fecha-label {
        margin-left: auto;
        background: #90bc05;
        color: white;
        border-radius: 4px;
        padding: 1px 7px;
        font-size: 0.78rem;
      }
      .pred-riego-leyenda {
        display: flex;
        flex-wrap: wrap;
        gap: 6px 10px;
        margin-bottom: 10px;
        font-size: 0.72rem;
        color: #444;
      }
      .pred-riego-leyenda span { display: inline-flex; align-items: center; gap: 4px; }
      .pred-riego-leyenda i {
        display: inline-block;
        width: 11px;
        height: 11px;
        border-radius: 2px;
        flex-shrink: 0;
      }
      .pred-riego-opciones {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 5px;
      }
      .pred-riego-opcion {
        cursor: pointer;
        text-align: center;
        padding: 6px 4px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        background: #e8f2c2;
        color: #5a7503;
        border: 2px solid transparent;
        transition: background 0.15s, border-color 0.15s;
        line-height: 1.3;
      }
      .pred-riego-opcion:hover { background: #d4e89a; }
      .pred-riego-opcion.seleccionada {
        background: #90bc05;
        color: white;
        border-color: #6d9004;
      }
      .pred-riego-opcion-dia   { font-size: 0.85rem; display: block; }
      .pred-riego-opcion-fecha { font-size: 0.70rem; display: block; opacity: 0.85; }
    </style>

    <div id="pred-riego-panel">
      <div class="pred-riego-panel-label">
        <i class="bi bi-droplet-half"></i>
        Recomendación riego
        <span id="pred-riego-fecha-label"></span>
      </div>
      <div class="pred-riego-leyenda">
        <span><i style="background:#d32f2f;"></i> Regar hoy/mañana</span>
        <span><i style="background:#f57c00;"></i> Regar +2/+3 días</span>
        <span><i style="background:#1976d2;"></i> Sin recomendación</span>
        <span style="opacity:0.85;">Etiqueta: m³/ha</span>
      </div>
      <div class="pred-riego-opciones">
        <div class="pred-riego-opcion seleccionada" data-offset="0">
          <span class="pred-riego-opcion-dia">Hoy</span>
          <span class="pred-riego-opcion-fecha"></span>
        </div>
        <div class="pred-riego-opcion" data-offset="1">
          <span class="pred-riego-opcion-dia">+1 día</span>
          <span class="pred-riego-opcion-fecha"></span>
        </div>
        <div class="pred-riego-opcion" data-offset="2">
          <span class="pred-riego-opcion-dia">+2 días</span>
          <span class="pred-riego-opcion-fecha"></span>
        </div>
        <div class="pred-riego-opcion" data-offset="3">
          <span class="pred-riego-opcion-dia">+3 días</span>
          <span class="pred-riego-opcion-fecha"></span>
        </div>
      </div>
    </div>`;

    const etpPanel = document.getElementById("pred-etp-panel");
    if (etpPanel) {
      etpPanel.insertAdjacentHTML("afterend", html);
    } else {
      const grid = document.querySelector("#basemap-panel .basemap-grid");
      if (grid) grid.insertAdjacentHTML("afterend", html);
    }
  }

})();
