(function () {
  // Años disponibles
  const years = ['2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017', '2016', '2015', '2014', '2013', '2012'];

  // Contenedor principal del panel
  const container = document.getElementById('mapa-cultivos-panel');
  if (!container) return;

  // Array para guardar el orden de activación (los años activos, ordenados por último clic)
  let ordenActivacion = [];

  // Generar HTML para cada año
  years.forEach(year => {
    const div = document.createElement('div');
    div.id = `contenedor-mcsncyl-${year}`;
    div.style.cssText = 'padding: 10px; background: #f8f9fa; border-radius: 8px; border: 1px solid #dee2e6; margin-bottom: 8px;';
    div.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between;">
        <span style="font-weight: 600;">MCSNCyL ${year}</span>
        <button class="btn btn-sm btn-outline-secondary" id="btn-mcsncyl-${year}" data-year="${year}" data-active="false" style="border: none; padding: 4px 8px;">
          <i class="bi bi-eye-slash" style="font-size: 1.1rem;" title="Mostrar capa"></i>
        </button>
      </div>
      <div id="legend-mcsncyl-${year}" class="d-none mt-2"></div>
    `;
    container.appendChild(div);
  });

  // Función para aplicar la clase de resalte al contenedor del año indicado
  function aplicarResalte(year) {
    // Quitar la clase de todos los contenedores
    years.forEach(y => {
      const cont = document.getElementById(`contenedor-mcsncyl-${y}`);
      if (cont) cont.classList.remove('resalte-activo');
    });
    // Poner la clase al contenedor del año (si existe)
    if (year) {
      const cont = document.getElementById(`contenedor-mcsncyl-${year}`);
      if (cont) cont.classList.add('resalte-activo');
    }
  }

  // Actualizar el resalte basado en el último elemento de ordenActivacion
  function actualizarResalteDesdeOrden() {
    if (ordenActivacion.length > 0) {
      const ultimo = ordenActivacion[ordenActivacion.length - 1];
      aplicarResalte(ultimo);
    } else {
      aplicarResalte(null);
    }
  }

  // Función para manejar la activación de un año
  function activarYear(year, btn, legendContainer) {
    // Cambiar el botón a estado activo
    btn.setAttribute('data-active', 'true');
    btn.classList.remove('btn-outline-secondary');
    btn.classList.add('btn-primary');
    btn.innerHTML = '<i class="bi bi-eye-fill" style="font-size: 1.1rem;" title="Ocultar capa"></i>';

    // Mostrar leyenda si existe
    if (legendContainer && window.MCSNCYL_LEGEND) {
      legendContainer.classList.remove('d-none');
      window.MCSNCYL_LEGEND.show(parseInt(year), `legend-mcsncyl-${year}`);
    }

    // Activar la capa en cylLayersData
    if (window.cylLayersData && window.cylLayersData[year]) {
      window.cylLayersData[year].active = true;
      // Subir el z-index
      if (window.map) {
        const paneName = `cultivos${year}`;
        const pane = window.map.getPane(paneName);
        if (pane) {
          // Incrementar zIndex global (puedes usar un contador externo si quieres)
          let topZIndex = 590;
          if (window.ultimoZIndexCultivos === undefined) window.ultimoZIndexCultivos = 590;
          window.ultimoZIndexCultivos++;
          pane.style.zIndex = window.ultimoZIndexCultivos;
        }
      }
      // Llamar a la función que carga la capa (definida en visor.html)
      if (typeof cargarCyLSiProcede === 'function') {
        cargarCyLSiProcede(parseInt(year));
      }
    }

    // Actualizar ordenActivacion
    // Si ya estaba en el array, lo movemos al final
    const index = ordenActivacion.indexOf(year);
    if (index !== -1) {
      ordenActivacion.splice(index, 1);
    }
    ordenActivacion.push(year);

    // Aplicar resalte
    actualizarResalteDesdeOrden();
  }

  // Función para manejar la desactivación de un año
  function desactivarYear(year, btn, legendContainer) {
    // Cambiar el botón a estado inactivo
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
      if (typeof cargarCyLSiProcede === 'function') {
        cargarCyLSiProcede(parseInt(year));
      }
    }

    // Quitar el año del ordenActivacion
    const index = ordenActivacion.indexOf(year);
    if (index !== -1) {
      ordenActivacion.splice(index, 1);
    }

    // Aplicar resalte
    actualizarResalteDesdeOrden();
  }

  // Inicializar eventos y estado actual
  years.forEach(year => {
    const btn = document.getElementById(`btn-mcsncyl-${year}`);
    if (!btn) return;

    const legendContainer = document.getElementById(`legend-mcsncyl-${year}`);

    // Al hacer clic en el botón
    btn.addEventListener('click', async () => {
      const isActive = btn.getAttribute('data-active') === 'true';

      if (!isActive) {
        activarYear(year, btn, legendContainer);
      } else {
        desactivarYear(year, btn, legendContainer);
      }
    });

    // Verificar si el año está activo inicialmente (por ejemplo, si se recargó la página y ya había capas activas)
    if (window.cylLayersData && window.cylLayersData[year] && window.cylLayersData[year].active) {
      // Si está activo, actualizamos el botón y lo añadimos a ordenActivacion
      btn.setAttribute('data-active', 'true');
      btn.classList.remove('btn-outline-secondary');
      btn.classList.add('btn-primary');
      btn.innerHTML = '<i class="bi bi-eye-fill" style="font-size: 1.1rem;" title="Ocultar capa"></i>';
      if (legendContainer && window.MCSNCYL_LEGEND) {
        legendContainer.classList.remove('d-none');
        // No llamamos a show porque la leyenda ya debería estar visible
      }
      // Añadir al ordenActivacion (pero sin duplicados)
      if (!ordenActivacion.includes(year)) {
        ordenActivacion.push(year);
      }
    }
  });

  // Una vez procesados todos los años, ordenamos el array de activación para que el resalte inicial sea el último activado
  // (por ejemplo, si hay varios activos, queremos que el resalte sea el año más reciente según algún criterio; 
  // como no tenemos información de cuál fue el último clic, podemos ordenar por año descendente)
  if (ordenActivacion.length > 0) {
    ordenActivacion.sort((a, b) => parseInt(b) - parseInt(a));
    aplicarResalte(ordenActivacion[0]);
  }

  // Exponer funciones si se necesitan externamente
  window.cultivosPanel = {
    activarYear,
    desactivarYear
  };
})();

// Toggle Detalles Adicionales
document.getElementById('toggle-detalles-adicionales')?.addEventListener('click', function () {
  const contenido = document.getElementById('contenido-detalles-adicionales');
  const icono = document.getElementById('icon-detalles-adicionales');
  if (contenido) {
    if (contenido.style.display === 'none' || contenido.style.display === '') {
      contenido.style.display = 'block';
      if (icono) icono.style.transform = 'rotate(180deg)';
    } else {
      contenido.style.display = 'none';
      if (icono) icono.style.transform = 'rotate(0deg)';
    }
  }
});

// Toggle Mapa de Cultivos
document.getElementById('toggle-mapa-cultivos')?.addEventListener('click', function () {
  const panel = document.getElementById('mapa-cultivos-panel');
  const icono = document.getElementById('icon-mapa-cultivos');
  if (panel) {
    if (panel.style.display === 'none' || panel.style.display === '') {
      panel.style.display = 'flex';
      if (icono) icono.style.transform = 'rotate(180deg)';
    } else {
      panel.style.display = 'none';
      if (icono) icono.style.transform = 'rotate(0deg)';
    }
  }
});