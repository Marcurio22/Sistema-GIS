/**
 * visor-etp.js  —  Capa ETP (ET₀ Monteith) con calendario de fechas disponibles.
 * Mejora: navegación salta a meses con datos.
 */

(function () {

  document.addEventListener("DOMContentLoaded", function () {
    setTimeout(initEtp, 300);
  });

  function initEtp() {

    const map = window.map;
    if (!map) { console.error("[ETP] window.map no encontrado."); return; }

    const GEOSERVER_WMS = window.GEOSERVER_WMS;
    if (!GEOSERVER_WMS) { console.error("[ETP] window.GEOSERVER_WMS no encontrado."); return; }

    const btnEtp = document.querySelector('.basemap-option.basemap-main[data-layer="etp"]');
    if (!btnEtp) { console.warn("[ETP] Botón [data-layer='etp'] no encontrado."); return; }

    if (!map.getPane("etpPane")) {
      map.createPane("etpPane");
      map.getPane("etpPane").style.zIndex = 250;
    }

    let etpActivo         = false;
    let etpFecha          = null;
    let fechasDisponibles = new Set();
    let calMes            = null; // { year, month } mostrado en el calendario

    const etpLayer = L.tileLayer.wms(GEOSERVER_WMS, {
      layers:      "gis_project:mapascontinuos",
      format:      "image/png",
      transparent: true,
      tiled:       true,
      pane:        "etpPane",
      opacity:     1,
      mazZoom:     22,
      minZoom:     7,
      interactive: false
    });

    // ── Fetch fechas ────────────────────────────────────────────────────────
    async function cargarFechasDisponibles() {
      try {
        const res  = await fetch("/api/etp/fechas");
        const data = await res.json();
        if (!data.ok) { console.error("[ETP]", data.error); return []; }
        return data.fechas;
      } catch (e) {
        console.error("[ETP] Error cargando fechas:", e);
        return [];
      }
    }

    // ── Activar / desactivar ────────────────────────────────────────────────
    function activarEtp() {
      etpActivo = true;
      if (!map.hasLayer(etpLayer)) {
        map.addLayer(etpLayer);
        if (etpFecha) {
          etpLayer.setParams({ TIME: etpFecha }, false);
        }
      }
      const panel = document.getElementById("etp-fecha-panel");
      if (panel) panel.style.display = "block";
    }

    function desactivarEtp() {
      etpActivo = false;
      if (map.hasLayer(etpLayer)) map.removeLayer(etpLayer);
      const panel = document.getElementById("etp-fecha-panel");
      if (panel) panel.style.display = "none";
    }

    map.on("zoomend moveend", function () {
      if (etpActivo && !map.hasLayer(etpLayer)) map.addLayer(etpLayer);
    });

    // ── Click botón ETP ─────────────────────────────────────────────────────
    btnEtp.addEventListener("click", async function () {
      document.querySelectorAll(".basemap-option.basemap-main")
        .forEach(el => el.classList.remove("active"));
      btnEtp.classList.add("active");

      activarEtp();

      if (fechasDisponibles.size > 0) {
        _renderCalendario();
        return;
      }

      _setLoading(true);
      try {
        const lista = await cargarFechasDisponibles();
        fechasDisponibles = new Set(lista);
        if (lista.length > 0) {
          const ultima = lista[lista.length - 1];
          const [y, m] = ultima.split("-").map(Number);
          calMes = { year: y, month: m };
          _seleccionarFecha(ultima);
        } else {
          calMes = null;
        }
      } catch (error) {
        console.error("Error cargando fechas:", error);
        calMes = null;
      } finally {
        _setLoading(false);
        _renderCalendario();
      }
    });

    // Desactivar ETP si se pulsa otro botón de capas base
    document.querySelectorAll(".basemap-option.basemap-main[data-layer]").forEach(btn => {
      if (btn.dataset.layer !== "etp") {
        btn.addEventListener("click", function () {
          if (etpActivo) desactivarEtp();
        });
      }
    });

    // ── Función para encontrar el mes anterior/siguiente con datos ──────────
    function _encontrarMesDisponible(year, month, step) {
      // step: -1 para anterior, +1 para siguiente
      let y = year;
      let m = month;
      // Límite de búsqueda: 24 meses para evitar loop infinito
      for (let i = 0; i < 24; i++) {
        m += step;
        if (m < 1) {
          m = 12;
          y -= 1;
        } else if (m > 12) {
          m = 1;
          y += 1;
        }
        const mesStr = `${y}-${String(m).padStart(2, '0')}`;
        // Comprobar si alguna fecha comienza con ese prefijo
        for (let fecha of fechasDisponibles) {
          if (fecha.startsWith(mesStr)) {
            return { year: y, month: m };
          }
        }
      }
      return null; // No encontrado
    }

    // ── Navegación del calendario ───────────────────────────────────────────
    document.addEventListener("click", function (e) {
      if (!calMes) return;

      if (e.target && e.target.id === "etp-cal-prev") {
        const nuevoMes = _encontrarMesDisponible(calMes.year, calMes.month, -1);
        if (nuevoMes) {
          calMes = nuevoMes;
          _renderCalendario();
        }
      }
      if (e.target && e.target.id === "etp-cal-next") {
        const nuevoMes = _encontrarMesDisponible(calMes.year, calMes.month, 1);
        if (nuevoMes) {
          calMes = nuevoMes;
          _renderCalendario();
        }
      }
    });

    // ── Seleccionar fecha y actualizar WMS ──────────────────────────────────
    function _seleccionarFecha(fecha) {
      if (!fechasDisponibles.has(fecha)) return;
      etpFecha = fecha;
      etpLayer.setParams({ TIME: fecha }, false);

      const lbl = document.getElementById("etp-fecha-label");
      if (lbl) {
        const [y, m, d] = fecha.split("-");
        lbl.textContent = `${d}/${m}/${y}`;
        lbl.style.display = "inline-block";
      }

      document.querySelectorAll(".etp-cal-day.disponible").forEach(el => {
        el.classList.toggle("seleccionado", el.dataset.fecha === fecha);
      });
    }

    // ── Render del calendario ───────────────────────────────────────────────
    function _renderCalendario() {
      const grid = document.getElementById("etp-cal-grid");
      const titulo = document.getElementById("etp-cal-titulo");
      if (!grid || !titulo) return;

      if (!calMes) {
        titulo.textContent = "Sin datos";
        grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:10px;">❌ No hay fechas disponibles</div>';
        return;
      }

      const { year, month } = calMes;
      const MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                     "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
      titulo.textContent = `${MESES[month - 1]} ${year}`;

      const primerDia = new Date(year, month - 1, 1).getDay();
      const inicio    = primerDia === 0 ? 6 : primerDia - 1;
      const diasMes   = new Date(year, month, 0).getDate();

      grid.innerHTML = "";

      ["L","M","X","J","V","S","D"].forEach(d => {
        const h = document.createElement("div");
        h.className = "etp-cal-header";
        h.textContent = d;
        grid.appendChild(h);
      });

      for (let i = 0; i < inicio; i++) {
        const v = document.createElement("div");
        grid.appendChild(v);
      }

      for (let dia = 1; dia <= diasMes; dia++) {
        const fecha = `${year}-${String(month).padStart(2,"0")}-${String(dia).padStart(2,"0")}`;
        const cel   = document.createElement("div");
        cel.className = "etp-cal-day";
        cel.textContent = dia;
        cel.dataset.fecha = fecha;

        if (fechasDisponibles.has(fecha)) {
          cel.classList.add("disponible");
          if (fecha === etpFecha) cel.classList.add("seleccionado");
          cel.addEventListener("click", function () {
            _seleccionarFecha(fecha);
          });
        } else {
          cel.classList.add("no-disponible");
        }

        grid.appendChild(cel);
      }
    }

    _inyectarUI();
  }

  // ── Utilidades ────────────────────────────────────────────────────────────
  function _setLoading(loading) {
    const spin = document.getElementById("etp-loading");
    if (spin) spin.style.display = loading ? "inline-block" : "none";
  }

  function _inyectarUI() {
    if (document.getElementById("etp-fecha-panel")) return;

    const html = `
    <style>
      #etp-fecha-panel {
        display: none;
        margin-top: 10px;
        padding: 10px 12px;
        background: #f0f7f0;
        border-radius: 8px;
        border: 1px solid #c3e6cb;
        user-select: none;
      }
      .etp-panel-label {
        font-size: 0.82rem; font-weight: 600;
        color: #155724; margin-bottom: 8px;
        display: flex; align-items: center; gap: 6px;
      }
      #etp-fecha-label {
        display: none;
        margin-left: auto;
        background: #198754;
        color: white;
        border-radius: 4px;
        padding: 1px 7px;
        font-size: 0.78rem;
      }
      .etp-cal-nav {
        display: flex; align-items: center;
        justify-content: space-between;
        margin-bottom: 6px;
      }
      .etp-cal-nav button {
        background: none; border: none;
        cursor: pointer; font-size: 1rem;
        color: #155724; padding: 2px 6px;
        border-radius: 4px;
        line-height: 1;
      }
      .etp-cal-nav button:hover { background: #c3e6cb; }
      #etp-cal-titulo {
        font-size: 0.82rem; font-weight: 600; color: #155724;
      }
      #etp-cal-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 2px;
        margin-bottom: 10px;
      }
      .etp-cal-header {
        text-align: center; font-size: 0.65rem;
        font-weight: 700; color: #888;
        padding: 2px 0;
      }
      .etp-cal-day {
        text-align: center; font-size: 0.72rem;
        padding: 4px 2px; border-radius: 4px;
        line-height: 1.2;
      }
      .etp-cal-day.disponible {
        cursor: pointer; font-weight: 600;
        color: #155724; background: #d4edda;
      }
      .etp-cal-day.disponible:hover { background: #a3d4ad; }
      .etp-cal-day.seleccionado {
        background: #198754 !important;
        color: white !important;
      }
      .etp-cal-day.no-disponible {
        color: #ccc;
      }
      .etp-leyenda-bar {
        display: flex; align-items: center; gap: 5px;
      }
      .etp-leyenda-gradient {
        flex: 1;
        height: 11px;
        border-radius: 4px;
        border: 1px solid #ccc;
        background: linear-gradient(to right,
          #313695 0%,   #4575b4 10%, #74add1 20%, #abd9e9 30%, #e0f3f8 40%,
          #ffffbf 50%, #fee090 60%, #fdae61 70%, #f46d43 80%, #d73027 90%, #a50026 100%);
      }
    </style>

    <div id="etp-fecha-panel">
      <div class="etp-panel-label">
        <i class="bi bi-droplet-half"></i>
        ET₀ Monteith
        <span id="etp-loading" style="display:none;">
          <span class="spinner-border spinner-border-sm text-success"></span>
        </span>
        <span id="etp-fecha-label"></span>
      </div>

      <div class="etp-cal-nav">
        <button id="etp-cal-prev" title="Mes anterior">&#8249;</button>
        <span id="etp-cal-titulo"></span>
        <button id="etp-cal-next" title="Mes siguiente">&#8250;</button>
      </div>
      <div id="etp-cal-grid"></div>

      <div style="font-size:0.7rem; color:#555; font-weight:600; margin-bottom:3px;">
        ET₀ (mm/día)
      </div>
      <div class="etp-leyenda-bar">
        <span style="font-size:0.68rem;">0.5</span>
        <div class="etp-leyenda-gradient"></div>
        <span style="font-size:0.68rem;">3.0</span>
      </div>
      <div style="display:flex; justify-content:space-between;
                  font-size:0.63rem; color:#888; margin-top:1px; padding:0 22px;">
        <span>Bajo</span><span>Medio</span><span>Alto</span>
      </div>
    </div>`;

    const grid = document.querySelector("#basemap-panel .basemap-grid");
    if (grid) grid.insertAdjacentHTML("afterend", html);
  }

})();