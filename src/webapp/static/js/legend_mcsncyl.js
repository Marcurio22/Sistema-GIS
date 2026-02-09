(function () {
  async function fetchLegend(year) {
    const res = await fetch(`/api/legend/mcsncyl/${year}`, { credentials: "same-origin" });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`Legend fetch failed ${res.status}: ${txt}`);
    }
    return res.json();
  }

  function renderLegend(container, json) {
    container.innerHTML = "";

    const title = document.createElement("div");
    title.className = "legend-title";
    title.textContent = `Leyenda MCSNCyL ${json.year || ""}`.trim();
    container.appendChild(title);

    const grid = document.createElement("div");
    grid.className = "legend-grid";

    (json.items || []).forEach(it => {
      const row = document.createElement("div");
      row.className = "legend-row";

      const sw = document.createElement("span");
      sw.className = "legend-swatch";
      sw.style.backgroundColor = it.hex;

      const label = document.createElement("span");
      label.className = "legend-label";
      label.textContent = `${it.code} — ${it.label}`;

      row.appendChild(sw);
      row.appendChild(label);
      grid.appendChild(row);
    });

    container.appendChild(grid);
  }

  window.MCSNCYL_LEGEND = {
    async show(year, containerId) {
      const el = document.getElementById(containerId);
      if (!el) return;

      el.classList.remove("d-none");
      el.innerHTML = `<div class="legend-loading">Cargando leyenda…</div>`;

      try {
        const json = await fetchLegend(year);
        renderLegend(el, json);
      } catch (e) {
        console.error(e);
        el.innerHTML = `<div class="legend-error">No se pudo cargar la leyenda.</div>`;
      }
    },

    hide(containerId) {
      const el = document.getElementById(containerId);
      if (!el) return;
      el.classList.add("d-none");
    }
  };
})();