class NDVI {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.recintoId = null;
    this.todosLosIndices = [];
    this.indiceActual = 0;
    this.init();
    this.setupDetallePanel();
  }

  init() {
    this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver NDVI</p>';
  }

  setupDetallePanel() {
    // Configurar botón "Más detalle"
    const btnDetalle = document.getElementById('btn-detalle-ndvi');
    if (btnDetalle) {
      btnDetalle.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.abrirDetallePanel();
      });
    }

    // Configurar botón "Volver"
    const btnVolver = document.getElementById('btn-volver-historico-ndvi');
    if (btnVolver) {
      btnVolver.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.cerrarDetallePanel();
      });
    }

    // Configurar botón "Cerrar" (X)
    const btnCerrar = document.getElementById('btn-cerrar-historico-ndvi');
    if (btnCerrar) {
      btnCerrar.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.cerrarDetallePanel();
        if (typeof closeSidePanel === 'function') {
          closeSidePanel();
        }
      });
    }
  }

  abrirDetallePanel() {
    const sidePanel = document.getElementById('side-panel');
    const overlayPanel = document.getElementById('ndvi-historico-panel');
    
    if (!sidePanel || !overlayPanel) return;

    sidePanel.classList.add('ndvi-historico-open');
    overlayPanel.classList.remove('d-none');
    overlayPanel.setAttribute('aria-hidden', 'false');

    this.cargarDetalleNDVI();
  }

  cerrarDetallePanel() {
    const sidePanel = document.getElementById('side-panel');
    const overlayPanel = document.getElementById('ndvi-historico-panel');
    
    if (!sidePanel || !overlayPanel) return;

    sidePanel.classList.remove('ndvi-historico-open');
    overlayPanel.classList.add('d-none');
    overlayPanel.setAttribute('aria-hidden', 'true');
  }

  async cargarDetalleNDVI() {
    const listEl = document.getElementById('ndvi-historico-list');
    if (!listEl) return;

    if (!this.recintoId) {
      listEl.innerHTML = '<p class="text-muted">No hay recinto seleccionado</p>';
      return;
    }

    listEl.innerHTML = '<div class="text-muted">Cargando histórico NDVI...</div>';

    try {
      const response = await fetch(`/api/indices-raster?id_recinto=${this.recintoId}&tipo_indice=NDVI`);
      
      if (!response.ok) {
        throw new Error('Error al cargar NDVI');
      }

      const indices = await response.json();
      
      if (!indices || indices.length === 0) {
        listEl.innerHTML = `
          <div class="text-muted text-center py-3">
            <i class="fa-solid fa-leaf mb-2" style="font-size: 2rem; opacity: 0.3;"></i>
            <p class="mb-0">No hay datos NDVI disponibles</p>
          </div>
        `;
        return;
      }

      this.todosLosIndices = indices;
      this.indiceActual = 0;

      this.renderizarDetalle(listEl);

    } catch (error) {
      console.error('Error al cargar detalle NDVI:', error);
      listEl.innerHTML = '<p class="text-danger">Error cargando el histórico NDVI</p>';
    }
  }

  renderizarDetalle(listEl) {
    const total = this.todosLosIndices.length;
    
    listEl.innerHTML = `
      <!-- Carrusel de imágenes -->
      <div class="mb-4">
        <h5 class="mb-3">
          <i class="bi bi-images me-2"></i>
          Imágenes NDVI
          <span class="badge bg-success ms-2">${total}</span>
        </h5>
        
        <div class="ndvi-carousel">
          <button id="btn-carousel-prev" class="carousel-btn carousel-btn-prev" ${this.indiceActual === 0 ? 'disabled' : ''}>
            <i class="bi bi-chevron-left"></i>
          </button>
          
          <div class="carousel-images" id="carousel-images">
            ${this.renderizarImagenes()}
          </div>
          
          <button id="btn-carousel-next" class="carousel-btn carousel-btn-next" ${this.indiceActual + 3 >= total ? 'disabled' : ''}>
            <i class="bi bi-chevron-right"></i>
          </button>
        </div>
        

      </div>

      <div class="side-divider"></div>

      <!-- Gráfica de evolución -->
      <div class="mb-3">
        <h5 class="mb-3">
          <i class="bi bi-graph-up me-2"></i>
          Evolución del NDVI
        </h5>
        <div id="ndvi-chart"></div>
      </div>
    `;

    // Event listeners para navegación
    const btnPrev = listEl.querySelector('#btn-carousel-prev');
    const btnNext = listEl.querySelector('#btn-carousel-next');

    if (btnPrev) {
      btnPrev.addEventListener('click', () => {
        if (this.indiceActual > 0) {
          this.indiceActual = Math.max(0, this.indiceActual - 3);
          this.actualizarCarousel();
        }
      });
    }

    if (btnNext) {
      btnNext.addEventListener('click', () => {
        if (this.indiceActual + 3 < total) {
          this.indiceActual = Math.min(total - 3, this.indiceActual + 3);
          this.actualizarCarousel();
        }
      });
    }

    // Renderizar gráfica
    this.renderizarGrafica();
  }

  renderizarImagenes() {
    const imagenes = this.todosLosIndices.slice(this.indiceActual, this.indiceActual + 3);
    
    return imagenes.map((indice, idx) => {
      let rutaImagen = indice.ruta_ndvi;
      
      if (rutaImagen) {
        rutaImagen = rutaImagen.replace(/^webapp\//, '');
        if (!rutaImagen.startsWith('/')) {
          rutaImagen = '/' + rutaImagen;
        }
      } else {
        rutaImagen = `/static/thumbnails/${indice.fecha_ndvi ? indice.fecha_ndvi.replace(/-/g, '').substring(0, 8) : 'unknown'}_${this.recintoId}.png`;
      }

      const fecha = indice.fecha_ndvi ? new Date(indice.fecha_ndvi).toLocaleDateString('es-ES') : 'N/A';
      
      return `
        <div class="carousel-item">
          <img src="${rutaImagen}" 
               alt="NDVI ${fecha}" 
               class="carousel-img"
               onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22><rect width=%22100%22 height=%22100%22 fill=%22%23e9ecef%22/><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%236c757d%22>Sin imagen</text></svg>'">
          <div class="carousel-item-info">
            <div class="fw-bold">${fecha}</div>
            <div class="text-muted" style="font-size: 0.75rem;">Media: ${indice.valor_medio.toFixed(4)}</div>
          </div>
        </div>
      `;
    }).join('');
  }

  actualizarCarousel() {
    const carouselEl = document.getElementById('carousel-images');
    const btnPrev = document.getElementById('btn-carousel-prev');
    const btnNext = document.getElementById('btn-carousel-next');
    const total = this.todosLosIndices.length;

    if (carouselEl) {
      carouselEl.innerHTML = this.renderizarImagenes();
    }

    if (btnPrev) {
      btnPrev.disabled = this.indiceActual === 0;
    }

    if (btnNext) {
      btnNext.disabled = this.indiceActual + 3 >= total;
    }

    // Actualizar contador
    const listEl = document.getElementById('ndvi-historico-list');
    const contador = listEl?.querySelector('.text-center.text-muted');
    if (contador) {
      contador.textContent = `Mostrando ${Math.min(this.indiceActual + 1, total)} - ${Math.min(this.indiceActual + 3, total)} de ${total}`;
    }
  }

async renderizarGrafica() {
    const container = document.getElementById('ndvi-chart');
    if (!container) return;

    container.innerHTML = '<div class="text-center text-muted py-3"><div class="spinner-border spinner-border-sm text-success me-2" role="status"></div>Generando gráfica...</div>';

    try {
      const response = await fetch(`/api/grafica-ndvi/${this.recintoId}`);
      
      if (!response.ok) {
        throw new Error('Error de servidor');
      }

      const data = await response.json();
      
      if (data.error) {
        container.innerHTML = `<p class="text-danger small text-center">${data.error}</p>`;
        return;
      }
      
      if (data.fechas && data.valores) {
        // Crear canvas para la gráfica
        container.innerHTML = '<canvas id="ndvi-chart-canvas"></canvas>';
        
        const ctx = document.getElementById('ndvi-chart-canvas').getContext('2d');
        
        // Destruir gráfica anterior si existe
        if (this.chartInstance) {
          this.chartInstance.destroy();
        }
        
        // Crear gráfica estilo Sativum
        this.chartInstance = new Chart(ctx, {
          type: 'line',
          data: {
            labels: data.fechas,
            datasets: [{
              label: 'Vegetación',
              data: data.valores,
              borderColor: '#4CAF50',
              backgroundColor: 'rgba(76, 175, 80, 0.1)',
              borderWidth: 3,
              fill: true,
              tension: 0.4, // Curvas suaves
              pointRadius: 4,
              pointHoverRadius: 6,
              pointBackgroundColor: '#4CAF50',
              pointBorderColor: '#fff',
              pointBorderWidth: 2
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
            },
            
            interaction: {
              intersect: false,
              mode: 'index'
            },
            plugins: {
              legend: {
                display: true,
                position: 'top',
                align: 'center',
                labels: {
                  usePointStyle: true,
                  padding: 25,
                  font: {
                    size: 13,
                    family: "'Inter', 'Segoe UI', sans-serif"
                  }
                }
              },
              tooltip: {
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                padding: 12,
                titleFont: {
                  size: 13,
                  weight: '600'
                },
                bodyFont: {
                  size: 12
                },
                displayColors: false,
                callbacks: {
                  title: function(context) {
                    return context[0].label;
                  },
                  label: function(context) {
                    return context.parsed.y.toFixed(2) + ' Veg. elevada';
                  }
                }
              }
            },
            scales: {
              x: {
                grid: {
                  display: true,
                  color: 'rgba(0, 0, 0, 0.05)',
                  drawBorder: false
                },
                ticks: {
                  font: {
                    size: 12,
                    family: "'Inter', 'Segoe UI', sans-serif"
                  },
                  color: '#666',
                  maxRotation: 0,
                  autoSkip: true,
                  maxTicksLimit: 8
                }
              },
              y: {
                beginAtZero: true,
                max: 1.0,
                grid: {
                  color: 'rgba(0, 0, 0, 0.05)',
                  drawBorder: false
                },
                ticks: {
                  font: {
                    size: 12,
                    family: "'Inter', 'Segoe UI', sans-serif"
                  },
                  color: '#666',
                  stepSize: 0.1
                }
              }
            }
          }
        });
        
      } else {
        container.innerHTML = '<p class="text-muted text-center">No se pudieron generar los datos visuales.</p>';
      }
    } catch (error) {
      console.error('Error al cargar gráfica:', error);
      container.innerHTML = '<p class="text-danger text-center small">No se pudo cargar la gráfica.</p>';
    }
  }
  async setRecintoId(recintoId) {
    this.recintoId = recintoId;
    await this.cargarYMostrar();
  }

  async cargarYMostrar() {
    if (!this.recintoId) {
      this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver NDVI</p>';
      return;
    }

    try {
      // Cargar datos del NDVI
      const response = await fetch(`/api/indices-raster?id_recinto=${this.recintoId}&tipo_indice=NDVI`);
      
      if (!response.ok) {
        throw new Error('Error al cargar NDVI');
      }

      const indices = await response.json();
      
      if (!indices || indices.length === 0) {
        this.container.innerHTML = `
          <div class="text-muted text-center py-3">
            <i class="fa-solid fa-leaf mb-2" style="font-size: 2rem; opacity: 0.3;"></i>
            <p class="mb-0">No hay datos NDVI disponibles</p>
          </div>
        `;
        return;
      }

      // Guardar todos los índices para el detalle
      this.todosLosIndices = indices;

      // Tomar el índice más reciente
      const ultimoIndice = indices[0];
      
      // Obtener ruta de la imagen desde la BD
      let rutaImagen = ultimoIndice.ruta_ndvi;
      
      // Limpiar la ruta: quitar prefijo 'webapp/' si existe
      if (rutaImagen) {
        rutaImagen = rutaImagen.replace(/^webapp\//, '');
        
        // Asegurar que la ruta empiece con /
        if (!rutaImagen.startsWith('/')) {
          rutaImagen = '/' + rutaImagen;
        }
      }
      
      // Si no hay ruta, usar fallback
      if (!rutaImagen) {
        rutaImagen = `/static/thumbnails/${ultimoIndice.fecha_ndvi ? ultimoIndice.fecha_ndvi.replace(/-/g, '').substring(0, 8) : 'unknown'}_${this.recintoId}.png`;
      }
      
      this.container.innerHTML = `
        <div class="ndvi-card">
          <img src="${rutaImagen}" 
               alt="NDVI Recinto ${this.recintoId}" 
               class="ndvi-imagen"
                onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22200%22><rect width=%22300%22 height=%22200%22 fill=%22%23e9ecef%22/><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%236c757d%22 font-size=%2214%22>Sin imagen NDVI</text></svg>'">
          
          <div class="ndvi-stats">
            <div class="stat-item">
              <span class="stat-label">Media</span>
              <span class="stat-value">${ultimoIndice.valor_medio.toFixed(4)}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Mín</span>
              <span class="stat-value">${ultimoIndice.valor_min.toFixed(4)}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Máx</span>
              <span class="stat-value">${ultimoIndice.valor_max.toFixed(4)}</span>
            </div>
          </div>
        </div>
      `;
      
    } catch (error) {
      console.error('Error:', error);
      this.container.innerHTML = '<p class="text-danger">Error cargando NDVI</p>';
    }
  }
}

// Inicializar
window.ndviManager = null;
document.addEventListener('DOMContentLoaded', () => {
  window.ndviManager = new NDVI('ndvi-container');
});