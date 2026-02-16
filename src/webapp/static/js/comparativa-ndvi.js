/**
 * Gestor del Modal de Comparativa de Campañas NDVI
 * Muestra 3 gráficas comparativas de diferentes campañas agrícolas
 * VERSIÓN MEJORADA: Tooltip inteligente + línea vertical gris
 */

(function() {
  'use strict';

  // Variables globales
  let charts = {};
  let currentRecintoId = null;
  let campaniasData = [];
  let lineaVerticalX = null; // Posición X de la línea vertical

  /**
   * Inicializa el modal y los event listeners
   */
  function initComparativaModal() {
    
    const btnComparativa = document.getElementById('btn-comparativa-ndvi');
    const btnCerrar = document.getElementById('btn-cerrar-comparativa');
    const modal = document.getElementById('modal-comparativa-campanias');

    if (!btnComparativa || !modal) {
      console.error('❌ No se encontraron elementos necesarios');
      return;
    }

    btnComparativa.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      
      const recintoId = getRecintoIdActual();
      
      if (!recintoId) {
        alert('Por favor, selecciona un recinto primero');
        return;
      }

      currentRecintoId = recintoId;
      openModal();
      loadComparativaData(recintoId);
    });

    if (btnCerrar) {
      btnCerrar.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        closeModal();
      });
    }

    modal.addEventListener('click', function(e) {
      if (e.target === modal) {
        closeModal();
      }
    });

    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal.style.display !== 'none') {
        closeModal();
      }
    });

  }

  /**
   * Obtiene el ID del recinto actualmente seleccionado
   */
  function getRecintoIdActual() {
    if (typeof window.currentSideRecintoId !== 'undefined' && window.currentSideRecintoId) {
      return window.currentSideRecintoId;
    }
    return null;
  }

  /**
   * Abre el modal
   */
  function openModal() {
    const modal = document.getElementById('modal-comparativa-campanias');
    const loading = document.getElementById('comparativa-loading');
    const contenido = document.getElementById('comparativa-contenido');
    const error = document.getElementById('comparativa-error');

    modal.style.display = 'flex';
    loading.style.display = 'block';
    contenido.style.display = 'none';
    error.style.display = 'none';

    document.body.style.overflow = 'hidden';
  }

  /**
   * Cierra el modal y limpia la gráfica
   */
  function closeModal() {
    const modal = document.getElementById('modal-comparativa-campanias');
    modal.style.display = 'none';
    document.body.style.overflow = '';

    hideImagenesPanel();
    campaniasData = [];
    lineaVerticalX = null; // Limpiar línea vertical

    // Limpiar tooltip personalizado si existe
    const tooltipEl = document.getElementById('chartjs-tooltip-custom');
    if (tooltipEl) {
      tooltipEl.remove();
    }

    if (charts['chart-unificado']) {
      charts['chart-unificado'].destroy();
      delete charts['chart-unificado'];
    }
  }

  /**
   * Carga los datos de comparativa desde el servidor
   */
  async function loadComparativaData(recintoId) {
    
    const url = `/api/comparativa-campanias/${recintoId}`;
    
    try {
      const response = await fetch(url);
      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || 'Error al cargar los datos');
      }

      document.getElementById('comparativa-loading').style.display = 'none';
      document.getElementById('comparativa-contenido').style.display = 'block';

      createCharts(data.campanias);

    } catch (error) {
      console.error('💥 Error al cargar comparativa:', error);
      showError(`Error al cargar los datos: ${error.message}`);
    }
  }

  /**
   * Crea las gráficas con todas las campañas
   */
  function createCharts(campanias) {
    
    if (!campanias || campanias.length === 0) {
      showError('No hay datos disponibles para las campañas');
      return;
    }

    campaniasData = campanias;
    createUnifiedChart(campanias);
    
    campanias.forEach((campania, index) => {
      updateStats(index + 1, campania.datos, campania.nombre);
    });
    
    const btnCerrarImagenes = document.getElementById('btn-cerrar-imagenes');
    if (btnCerrarImagenes) {
      btnCerrarImagenes.onclick = hideImagenesPanel;
    }
  }

  /**
   * Calcula días desde el inicio de la campaña (1 sept = día 0)
   * NORMALIZADO: Mismo día del año = mismo valor X en todas las campañas
   */
  function calcularDiaCampania(fechaStr, yearCampania) {
    const fecha = new Date(fechaStr);
    const mes = fecha.getMonth(); // 0-11
    const dia = fecha.getDate(); // 1-31
    
    // Definir días acumulados hasta el inicio de cada mes (año NO bisiesto)
    const diasAcumulados = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    
    // Si la fecha es de septiembre a diciembre (meses 8-11), es del primer año de campaña
    if (mes >= 8) {
      const diasDesdeInicioCampania = diasAcumulados[mes] - diasAcumulados[8] + (dia - 1);
      return diasDesdeInicioCampania;
    } 
    // Si es de enero a agosto (meses 0-7), es del segundo año de campaña
    else {
      const diasPrimeraParteAnio = diasAcumulados[11] - diasAcumulados[8] + 30;
      const diasSegundaParteAnio = diasAcumulados[mes] + (dia - 1);
      return diasPrimeraParteAnio + diasSegundaParteAnio;
    }
  }

  /**
   * Crea una gráfica unificada con todas las campañas
   */
  function createUnifiedChart(campanias) {
    
    const ctx = document.getElementById('chart-campania-unificado');
    if (!ctx) {
      console.error('❌ Canvas no encontrado');
      return;
    }

    if (charts['chart-unificado']) {
      charts['chart-unificado'].destroy();
    }

    const colors = [
      { border: 'rgba(25, 135, 84, 1)', background: 'rgba(25, 135, 84, 0.2)' },
      { border: 'rgba(13, 110, 253, 1)', background: 'rgba(13, 110, 253, 0.2)' },
      { border: 'rgba(255, 193, 7, 1)', background: 'rgba(255, 193, 7, 0.2)' }
    ];

    // Crear datasets - CADA PUNTO ES UNA FECHA INDIVIDUAL
    const datasets = campanias.map((campania, campaniaIndex) => {
      if (!campania.datos || campania.datos.length === 0) {
        return null;
      }

      // Convertir cada dato a {x: día de campaña, y: valor}
      const puntos = campania.datos.map(dato => {
        const diaCampania = calcularDiaCampania(dato.fecha, campania.year);
        return {
          x: diaCampania,
          y: dato.valor_medio,
          fecha: dato.fecha // Guardar fecha original
        };
      });

      // Ordenar por día de campaña
      puntos.sort((a, b) => a.x - b.x);

      const color = colors[campaniaIndex] || colors[0];

      return {
        label: campania.nombre,
        data: puntos,
        borderColor: color.border,
        backgroundColor: color.background,
        borderWidth: 2,
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        pointHoverRadius: 7,
        pointBackgroundColor: color.border,
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        campaniaIndex: campaniaIndex,
        yearCampania: campania.year
      };
    }).filter(dataset => dataset !== null);

    if (datasets.length === 0) {
      showError('No hay datos disponibles');
      return;
    }

    try {
      // Plugin para dibujar la línea vertical (GRIS SUAVE)
      const lineaVerticalPlugin = {
        id: 'lineaVertical',
        afterDraw: (chart) => {
          if (lineaVerticalX !== null) {
            const ctx = chart.ctx;
            const xAxis = chart.scales.x;
            const yAxis = chart.scales.y;
            
            const x = xAxis.getPixelForValue(lineaVerticalX);
            
            // Dibujar línea vertical con estilo GRIS SUAVE
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(x, yAxis.top);
            ctx.lineTo(x, yAxis.bottom);
            ctx.lineWidth = 1.5;
            ctx.strokeStyle = 'rgba(100, 100, 100, 0.4)'; // ← GRIS en lugar de rojo
            ctx.setLineDash([3, 3]); // ← Línea discontinua más corta
            ctx.stroke();
            ctx.restore();
          }
        }
      };

      charts['chart-unificado'] = new Chart(ctx, {
        type: 'line',
        data: {
          datasets: datasets
        },
        plugins: [lineaVerticalPlugin], // Registrar el plugin
        options: {
          responsive: true,
          maintainAspectRatio: true,
          aspectRatio: 2.5,
          interaction: {
            mode: 'nearest',
            intersect: false,
            axis: 'x'
          },
          onClick: (event, activeElements) => {
            handleChartClick(event, activeElements);
          },
          plugins: {
            legend: {
              display: true,
              position: 'top',
              reverse: true,
              labels: {
                usePointStyle: true,
                padding: 15,
                font: { size: 12 }
              }
            },
            // TOOLTIP PERSONALIZADO INTELIGENTE
            tooltip: {
              enabled: false, // Desactivar tooltip por defecto
              external: function(context) {
                const {chart, tooltip} = context;
                
                // Crear o obtener elemento del tooltip
                let tooltipEl = document.getElementById('chartjs-tooltip-custom');
                
                if (!tooltipEl) {
                  tooltipEl = document.createElement('div');
                  tooltipEl.id = 'chartjs-tooltip-custom';
                  tooltipEl.style.cssText = `
                    position: absolute;
                    background: rgba(255, 255, 255, 0.95);
                    border: 1px solid #ddd;
                    border-radius: 6px;
                    color: #000;
                    padding: 12px;
                    pointer-events: none;
                    font-size: 12px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                    z-index: 9999;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                  `;
                  document.body.appendChild(tooltipEl);
                }

                if (tooltip.opacity === 0) {
                  tooltipEl.style.opacity = '0';
                  return;
                }

                // Obtener posición X del hover
                const activePoint = tooltip.dataPoints[0];
                if (!activePoint) return;
                
                const hoveredX = activePoint.parsed.x;
                
                const puntosEncontrados = [];
                
                chart.data.datasets.forEach((dataset, idx) => {
                  let puntoMasCercano = null;
                  let menorDistancia = Infinity;
                  
                  dataset.data.forEach(punto => {
                    const distancia = Math.abs(punto.x - hoveredX);
                    if (distancia < menorDistancia && distancia <= 0.5) { 
                      menorDistancia = distancia;
                      puntoMasCercano = punto;
                    }
                  });
                  
                  if (puntoMasCercano) {
                    puntosEncontrados.push({
                      label: dataset.label,
                      valor: puntoMasCercano.y,
                      fecha: puntoMasCercano.fecha,
                      color: dataset.borderColor
                    });
                  }
                });

                if (puntosEncontrados.length === 0) {
                  tooltipEl.style.opacity = '0';
                  return;
                }

                // Construir HTML
                let html = '';
                
                // Título (fecha del primer punto)
                if (puntosEncontrados[0].fecha) {
                  const fecha = new Date(puntosEncontrados[0].fecha);
                  html += `<div style="font-weight: bold; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid #eee;">
                    ${fecha.toLocaleDateString('es-ES', { day: 'numeric', month: 'long' })}
                  </div>`;
                }
                
                // Lista de valores
                puntosEncontrados.forEach(punto => {
                  html += `
                    <div style="display: flex; align-items: center; margin: 4px 0;">
                      <span style="
                        display: inline-block;
                        width: 10px;
                        height: 10px;
                        background: ${punto.color};
                        border-radius: 50%;
                        margin-right: 8px;
                      "></span>
                      <span>${punto.label}: <strong>${punto.valor.toFixed(3)}</strong></span>
                    </div>
                  `;
                });
                
                tooltipEl.innerHTML = html;
                
                // Posicionar tooltip
                const position = chart.canvas.getBoundingClientRect();
                tooltipEl.style.opacity = '1';
                tooltipEl.style.left = position.left + window.pageXOffset + tooltip.caretX + 'px';
                tooltipEl.style.top = position.top + window.pageYOffset + tooltip.caretY + 'px';
              }
            }
          },
          scales: {
            x: {
              type: 'linear',
              min: 0,
              max: 365,
              grid: { display: false },
              ticks: {
                stepSize: 30.4, // Aproximadamente un mes
                callback: function(value) {   
                  const meses = [
                    { dia: 0, label: 'Sep' },     
                    { dia: 30, label: 'Oct' },     
                    { dia: 61, label: 'Nov' },     
                    { dia: 91, label: 'Dic' },     
                    { dia: 122, label: 'Ene' },   
                    { dia: 153, label: 'Feb' },    
                    { dia: 181, label: 'Mar' },    
                    { dia: 212, label: 'Abr' },   
                    { dia: 242, label: 'May' },   
                    { dia: 273, label: 'Jun' },    
                    { dia: 303, label: 'Jul' },   
                    { dia: 334, label: 'Ago' }     
                  ];
                  
                  // Buscar el mes más cercano a este valor
                  const mesEncontrado = meses.reduce((prev, curr) => {
                    return Math.abs(curr.dia - value) < Math.abs(prev.dia - value) ? curr : prev;
                  });
                  
                  // Solo mostrar si está muy cerca del inicio del mes (tolerancia de ±5 días)
                  if (Math.abs(mesEncontrado.dia - value) < 5) {
                    return mesEncontrado.label;
                  }
                  return '';
                },
                autoSkip: false,
                maxRotation: 0,
                font: { size: 11 }
              },
              afterBuildTicks: function(axis) {
                // Forzar ticks en las posiciones exactas de los meses
                axis.ticks = [
                  { value: 0 },    // Sep
                  { value: 30 },   // Oct
                  { value: 61 },   // Nov
                  { value: 91 },   // Dic
                  { value: 122 },  // Ene
                  { value: 153 },  // Feb
                  { value: 181 },  // Mar
                  { value: 212 },  // Abr
                  { value: 242 },  // May
                  { value: 273 },  // Jun
                  { value: 303 },  // Jul
                  { value: 334 }   // Ago
                ];
              }
            },
            y: {
              beginAtZero: true,
              max: 1,
              grid: { color: 'rgba(0, 0, 0, 0.05)' },
              ticks: {
                callback: function(value) {
                  return value.toFixed(2);
                },
                font: { size: 11 }
              },
              title: {
                display: true,
                text: 'NDVI',
                font: { size: 12, weight: 'bold' }
              }
            }
          }
        }
      });
      
      
    } catch (error) {
      console.error('💥 Error al crear gráfica:', error);
    }
  }

  /**
   * Actualiza las estadísticas de una campaña
   */
  function updateStats(index, datos, nombreCampania) {
    const tituloElement = document.getElementById(`campania-${index}-titulo`);
    if (tituloElement) {
      tituloElement.textContent = nombreCampania;
    }

    if (!datos || datos.length === 0) {
      document.getElementById(`campania-${index}-promedio`).textContent = 'Sin datos';
      document.getElementById(`campania-${index}-max`).textContent = 'Sin datos';
      document.getElementById(`campania-${index}-min`).textContent = 'Sin datos';
      return;
    }

    const valores = datos.map(d => d.valor_medio);
    const promedio = valores.reduce((a, b) => a + b, 0) / valores.length;
    const max = Math.max(...valores);
    const min = Math.min(...valores);

    document.getElementById(`campania-${index}-promedio`).textContent = promedio.toFixed(3);
    document.getElementById(`campania-${index}-max`).textContent = max.toFixed(3);
    document.getElementById(`campania-${index}-min`).textContent = min.toFixed(3);
  }

  /**
   * Maneja el clic en la gráfica
   */
  function handleChartClick(event, activeElements) {
    if (activeElements.length === 0) {
      hideImagenesPanel();
      lineaVerticalX = null; // Ocultar línea vertical
      if (charts['chart-unificado']) {
        charts['chart-unificado'].update(); // Redibujar sin la línea
      }
      return;
    }

    const element = activeElements[0];
    const datasetIndex = element.datasetIndex;
    const pointIndex = element.index;
    
    const dataset = charts['chart-unificado'].data.datasets[datasetIndex];
    const point = dataset.data[pointIndex];
    
    // Establecer posición de línea vertical
    lineaVerticalX = point.x;
    
    // Redibujar gráfica con la línea vertical
    if (charts['chart-unificado']) {
      charts['chart-unificado'].update();
    }

    // Obtener la campaña y la fecha
    const campania = campaniasData[datasetIndex];
    const fechaSeleccionada = point.fecha;

    // Cargar imágenes de todas las campañas para esa misma fecha relativa
    loadImagenesDeTodasCampanias(fechaSeleccionada, campania);
  }

  /**
   * Carga las imágenes de todas las campañas para una fecha equivalente
   * Orden: de más antiguo a más reciente
   */
  async function loadImagenesDeTodasCampanias(fechaSeleccionada, campaniaOrigen) {

    const panelImagenes = document.getElementById('imagenes-dia-seleccionado');
    const fechaElement = document.getElementById('fecha-seleccionada');
    
    if (!panelImagenes || !fechaElement) return;

    const fecha = new Date(fechaSeleccionada);
    fechaElement.textContent = fecha.toLocaleDateString('es-ES', { 
      day: 'numeric', 
      month: 'long', 
      year: 'numeric' 
    });
    
    panelImagenes.style.display = 'block';

    // INVERTIR ORDEN: del más antiguo al más reciente
    const campaniasInvertidas = [...campaniasData].reverse();

    // Cargar imagen para cada campaña (ahora en orden inverso)
    for (let i = 0; i < campaniasInvertidas.length; i++) {
      const campania = campaniasInvertidas[i];
      const indexOriginal = campaniasData.length - 1 - i; // Índice en array original
      const posicionVisual = i + 1; // Posición visual (1, 2, 3)
      
      const label = document.getElementById(`imagen-label-${posicionVisual}`);
      if (label) {
        label.textContent = campania.nombre;
      }

      // Buscar la fecha equivalente en esta campaña
      await loadImagenCampania(posicionVisual, campania, fechaSeleccionada, indexOriginal);
    }

    panelImagenes.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  /**
   * Carga la imagen de una campaña específica
   * Busca imagen del mismo día de campaña (±10 días) en cada campaña
   */
  async function loadImagenCampania(index, campania, fechaObjetivo, indexCampaniaOriginal) {
    const container = document.getElementById(`imagen-container-${index}`);
    
    if (!container) return;

    // Colores de las campañas (mismo orden que en la gráfica)
    const colors = [
      'rgba(25, 135, 84, 1)',    // Verde
      'rgba(13, 110, 253, 1)',   // Azul
      'rgba(255, 193, 7, 1)'     // Amarillo
    ];
    
    // Obtener color de esta campaña
    const borderColor = colors[indexCampaniaOriginal] || colors[0];

    container.innerHTML = `
      <div class="imagen-loading">
        <div class="spinner-border spinner-border-sm"></div>
        <span>Buscando imagen...</span>
      </div>
    `;

    try {
      // Calcular el día de campaña de la fecha objetivo (usando la campaña original)
      const fechaObj = new Date(fechaObjetivo);
      const diaCampaniaObjetivo = calcularDiaCampaniaDesdeObjeto(fechaObj);
      
      // Convertir ese día de campaña a fecha absoluta en ESTA campaña
      const fechaEquivalente = obtenerFechaAbsolutaDesdeDiaCampania(diaCampaniaObjetivo, campania.year);
      
      const campaniaYear = campania.year;
      const campaniaInicio = `${campaniaYear - 1}-09-01`;
      const campaniaFin = `${campaniaYear}-08-31`;
      
      const url = `/api/buscar-imagen-ndvi/${currentRecintoId}?fecha=${fechaEquivalente}&margen=10&campania_inicio=${campaniaInicio}&campania_fin=${campaniaFin}`;
      
      const response = await fetch(url);
      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || 'No se encontró imagen');
      }

      const fechaReal = new Date(data.imagen.fecha_ndvi);
      const fechaObjetivoAbs = new Date(fechaEquivalente);
      container.innerHTML = `
        <img src="/${data.imagen.ruta_ndvi}" 
             alt="NDVI ${campania.nombre}" 
             style="border: 3px solid ${borderColor}; border-radius: 4px;"
             onerror="this.parentElement.innerHTML='<div class=\\'imagen-no-disponible\\' style=\\'border: 3px solid ${borderColor};\\' ><i class=\\'bi bi-image-fill\\'></i><span>Error al cargar</span></div>'">
        <div class="imagen-fecha-info">
          ${fechaReal.toLocaleDateString('es-ES')}

        </div>
      `;


    } catch (error) {
      console.error(`❌ Error:`, error);
      container.innerHTML = `
        <div class="imagen-no-disponible" style="border: 3px solid ${borderColor};">
          <i class="bi bi-image-fill"></i>
          <span>Ninguna imagen disponible cercana a la fecha seleccionada </span>
        </div>
      `;
    }
  }

  /**
   * Calcula el día de campaña desde un objeto Date
   */
  function calcularDiaCampaniaDesdeObjeto(fecha) {
    const mes = fecha.getMonth(); // 0-11
    const dia = fecha.getDate(); // 1-31
    
    const diasAcumulados = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    
    if (mes >= 8) {
      return diasAcumulados[mes] - diasAcumulados[8] + (dia - 1);
    } else {
      const diasPrimeraParteAnio = diasAcumulados[11] - diasAcumulados[8] + 30;
      return diasPrimeraParteAnio + diasAcumulados[mes] + (dia - 1);
    }
  }

  /**
   * Obtiene fecha absoluta (YYYY-MM-DD) desde día de campaña y año de campaña
   */
  function obtenerFechaAbsolutaDesdeDiaCampania(diaCampania, yearCampania) {
    // Año de inicio de la campaña
    const anioInicio = yearCampania - 1;
    
    // Septiembre a Diciembre = días 0 a 121
    if (diaCampania <= 121) {
      // Está en la primera parte (sept-dic del año anterior)
      const fechaInicio = new Date(anioInicio, 8, 1); // 1 sept
      fechaInicio.setDate(fechaInicio.getDate() + diaCampania);
      return fechaInicio.toISOString().split('T')[0];
    } else {
      // Está en la segunda parte (ene-ago del año actual)
      const diasEnSegundaParte = diaCampania - 122; // Restar días de sept-dic
      const fechaInicio = new Date(yearCampania, 0, 1); // 1 enero
      fechaInicio.setDate(fechaInicio.getDate() + diasEnSegundaParte);
      return fechaInicio.toISOString().split('T')[0];
    }
  }

  /**
   * Oculta el panel de imágenes
   */
  function hideImagenesPanel() {
    const panelImagenes = document.getElementById('imagenes-dia-seleccionado');
    if (panelImagenes) {
      panelImagenes.style.display = 'none';
    }
  }

  /**
   * Muestra un mensaje de error
   */
  function showError(message) {
    console.error('🚨 Error:', message);
    
    document.getElementById('comparativa-loading').style.display = 'none';
    document.getElementById('comparativa-contenido').style.display = 'none';
    
    const errorDiv = document.getElementById('comparativa-error');
    const errorMessage = document.getElementById('comparativa-error-mensaje');
    
    if (errorDiv && errorMessage) {
      errorMessage.textContent = message;
      errorDiv.style.display = 'block';
    }
  }

  // Inicializar
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initComparativaModal);
  } else {
    initComparativaModal();
  }

})();