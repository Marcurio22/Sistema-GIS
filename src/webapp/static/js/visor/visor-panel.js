
// visor-panel-cultivos-mapa.js
// Generación dinámica del panel de Mapa de Cultivos (MCSNCyL)
// y toggles de secciones del panel lateral.
// Sin dependencias de Jinja2 → archivo estático puro.
// Requiere: window.map, window.cylLayersData, cargarCyLSiProcede,
//           window.MCSNCYL_LEGEND (de legend_mcsncyl.js)

(function () {
  // 👇 CONFIGURA AQUÍ LOS AÑOS (del más reciente al más antiguo)
  const years = ['2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017', '2016', '2015', '2014', '2013', '2012'];


  const container = document.getElementById('mapa-cultivos-panel');

  if (!container) return;

  // Generar HTML para cada año
  years.forEach(year => {
    const div = document.createElement('div');
    div.style.cssText = 'padding: 10px; background: #f8f9fa; border-radius: 8px; border: 1px solid #dee2e6;';
    div.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
        <span style="font-weight: 600;">MCSNCyL ${year}</span>
        <button class="btn btn-sm btn-outline-secondary" id="btn-mcsncyl-${year}" data-year="${year}" data-active="false" style="border: none; padding: 4px 8px;">
          <i class="bi bi-eye-slash" style="font-size: 1.1rem;" title="Mostrar capa"></i>
        </button>
      </div>
      <div id="legend-mcsncyl-${year}" class="d-none mt-2"></div>
    `;
    container.appendChild(div);
  });

  // Manejar eventos
  let topZIndex = 590;

  years.forEach(year => {
    const btn = document.getElementById(`btn-mcsncyl-${year}`);
    if (!btn) return;

    btn.addEventListener("click", async () => {
      const isActive = btn.getAttribute('data-active') === 'true';
      const legendContainer = document.getElementById(`legend-mcsncyl-${year}`);

      if (!isActive) {
        // ACTIVAR capa
        btn.setAttribute('data-active', 'true');
        btn.classList.remove('btn-outline-secondary');
        btn.classList.add('btn-primary');
        btn.innerHTML = '<i class="bi bi-eye-fill" style="font-size: 1.1rem;" title="Ocultar capa"></i>';

        // Mostrar leyenda
        if (legendContainer && window.MCSNCYL_LEGEND) {
          legendContainer.classList.remove('d-none');
          await window.MCSNCYL_LEGEND.show(parseInt(year), `legend-mcsncyl-${year}`);
        }

        // Activar la capa en cylLayersData
        if (window.cylLayersData && window.cylLayersData[year]) {
          window.cylLayersData[year].active = true;

          // Poner esta capa por encima de las demás (sistema dinámico de z-index)
          topZIndex++;
          const paneName = `cultivos${year}`;
          const pane = window.map.getPane(paneName);
          if (pane) {
            pane.style.zIndex = topZIndex;
          }

          // Cargar la capa en el mapa
          cargarCyLSiProcede(parseInt(year));
        }

      } else {
        // DESACTIVAR capa
        btn.setAttribute('data-active', 'false');
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-outline-secondary');
        btn.innerHTML = '<i class="bi bi-eye-slash" style="font-size: 1.1rem;"></i>';

        // Ocultar leyenda
        if (legendContainer && window.MCSNCYL_LEGEND) {
          legendContainer.classList.add('d-none');
          window.MCSNCYL_LEGEND.hide(`legend-mcsncyl-${year}`);
        }

        // Desactivar la capa en cylLayersData
        if (window.cylLayersData && window.cylLayersData[year]) {
          window.cylLayersData[year].active = false;
          cargarCyLSiProcede(parseInt(year));
        }
      }
    });
  });
})();


// Toggle Detalles Adicionales
document.getElementById('toggle-detalles-adicionales').addEventListener('click', function () {
  const contenido = document.getElementById('contenido-detalles-adicionales');
  const icono = document.getElementById('icon-detalles-adicionales');

  if (contenido.style.display === 'none' || contenido.style.display === '') {
    contenido.style.display = 'block';
    icono.style.transform = 'rotate(180deg)';
  } else {
    contenido.style.display = 'none';
    icono.style.transform = 'rotate(0deg)';
  }
});

// Toggle Mapa de Cultivos
document.getElementById('toggle-mapa-cultivos').addEventListener('click', function () {
  const panel = document.getElementById('mapa-cultivos-panel');
  const icono = document.getElementById('icon-mapa-cultivos');

  if (panel.style.display === 'none' || panel.style.display === '') {
    panel.style.display = 'flex';
    icono.style.transform = 'rotate(180deg)';
  } else {
    panel.style.display = 'none';
    icono.style.transform = 'rotate(0deg)';
  }
});