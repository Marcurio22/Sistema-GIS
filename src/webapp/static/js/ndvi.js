class NDVI {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.recintoId = null;
        this.todosLosIndices = [];
        this.indiceActual = 0;
        this.imagenZoomActual = 0;
        this.init();
        this.setupDetallePanel();
        this.setupLightbox();
    }

    init() {
        this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver NDVI</p>';
    }

    setupDetallePanel() {
        const btnDetalle = document.getElementById('btn-detalle-ndvi');
        if (btnDetalle) {
            btnDetalle.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.abrirDetallePanel();
            });
        }

        const btnVolver = document.getElementById('btn-volver-historico-ndvi');
        if (btnVolver) {
            btnVolver.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.cerrarDetallePanel();
            });
        }

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

    setupLightbox() {
        // Usar el lightbox existente del visor
        this.lightbox = document.getElementById('lightbox');
        this.lightboxImg = document.getElementById('lightbox-img');
        this.lightboxCaption = document.getElementById('lightbox-caption');
        this.lightboxClose = document.querySelector('.lightbox-close');
        this.lightboxPrev = document.getElementById('lightbox-prev');
        this.lightboxNext = document.getElementById('lightbox-next');

        if (!this.lightbox) {
            console.error('Lightbox no encontrado en el DOM');
            return;
        }

        // Event listener para cerrar
        if (this.lightboxClose) {
            this.lightboxClose.addEventListener('click', () => this.cerrarZoom());
        }

        // Event listeners para navegación
        if (this.lightboxPrev) {
            this.lightboxPrev.addEventListener('click', (e) => {
                e.stopPropagation();
                this.navegarZoom(-1);
            });
        }

        if (this.lightboxNext) {
            this.lightboxNext.addEventListener('click', (e) => {
                e.stopPropagation();
                this.navegarZoom(1);
            });
        }

        // Cerrar con ESC y navegar con flechas
        document.addEventListener('keydown', (e) => {
            if (this.lightbox && this.lightbox.style.display === 'block') {
                if (e.key === 'Escape') {
                    this.cerrarZoom();
                } else if (e.key === 'ArrowLeft') {
                    this.navegarZoom(-1);
                } else if (e.key === 'ArrowRight') {
                    this.navegarZoom(1);
                }
            }
        });

        // Cerrar al hacer click en el fondo
        if (this.lightbox) {
            this.lightbox.addEventListener('click', (e) => {
                if (e.target === this.lightbox) {
                    this.cerrarZoom();
                }
            });
        }
    }

    abrirZoom(indiceGlobal) {
        if (!this.lightbox) {
            console.error('Lightbox no disponible');
            return;
        }

        this.imagenZoomActual = indiceGlobal;
        const indice = this.todosLosIndices[indiceGlobal];
        
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

        // Configurar imagen y caption
        this.lightboxImg.src = rutaImagen;
        this.lightboxImg.alt = `NDVI ${fecha}`;
        
        this.lightboxCaption.innerHTML = `
            <div style="text-align: center; padding: 10px;">
                <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 8px;">${fecha}</div>
                <div style="display: flex; gap: 20px; justify-content: center; font-size: 0.95rem;">
                    <span>Media: <strong>${indice.valor_medio.toFixed(4)}</strong></span>
                    <span>Mín: <strong>${indice.valor_min.toFixed(4)}</strong></span>
                    <span>Máx: <strong>${indice.valor_max.toFixed(4)}</strong></span>
                </div>
            </div>
        `;

        // Mostrar/ocultar botones según posición
        if (this.lightboxPrev) {
            this.lightboxPrev.style.display = indiceGlobal > 0 ? 'block' : 'none';
        }
        if (this.lightboxNext) {
            this.lightboxNext.style.display = indiceGlobal < this.todosLosIndices.length - 1 ? 'block' : 'none';
        }

        // Mostrar lightbox
        this.lightbox.style.display = 'block';
        document.body.style.overflow = 'hidden'; // Prevenir scroll
    }

    navegarZoom(direccion) {
        const nuevoIndice = this.imagenZoomActual + direccion;
        if (nuevoIndice >= 0 && nuevoIndice < this.todosLosIndices.length) {
            this.abrirZoom(nuevoIndice);
        }
    }

    cerrarZoom() {
        if (this.lightbox) {
            this.lightbox.style.display = 'none';
            document.body.style.overflow = ''; // Restaurar scroll
        }
    }

    abrirDetallePanel() {
        const sidePanel = document.getElementById('side-panel');
        const overlayPanel = document.getElementById('ndvi-historico-panel');

        if (!sidePanel || !overlayPanel) return;

        sidePanel.classList.add('ndvi-historico-open');
        overlayPanel.classList.remove('d-none');
        overlayPanel.setAttribute('aria-hidden', 'false');

        this.panelDetalleAbierto = true;
        this.cargarDetalleNDVI();
    }

    cerrarDetallePanel() {
        const sidePanel = document.getElementById('side-panel');
        const overlayPanel = document.getElementById('ndvi-historico-panel');

        if (!sidePanel || !overlayPanel) return;

        sidePanel.classList.remove('ndvi-historico-open');
        overlayPanel.classList.add('d-none');
        overlayPanel.setAttribute('aria-hidden', 'true');

        this.panelDetalleAbierto = false;
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
                listEl.innerHTML = `<div class="text-muted text-center py-3">
                    <i class="fa-solid fa-leaf mb-2" style="font-size: 2rem; opacity: 0.3;"></i>
                    <p class="mb-0">No hay datos NDVI disponibles</p>
                </div>`;
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

        listEl.innerHTML = `<!-- Carrusel de imágenes -->
        <div class="mb-4">
            <h5 class="mb-3">
                <i class="bi bi-images me-2"></i>
                Imágenes NDVI
                <span class="badge bg-success ms-2">${total}</span>
            </h5>

            <div class="ndvi-carousel">
                <button id="btn-carousel-prev" class="carousel-btn carousel-btn-prev">
                    <i class="bi bi-chevron-left"></i>
                </button>

                <div class="carousel-images" id="carousel-images">
                    ${this.renderizarImagenes()}
                </div>

                <button id="btn-carousel-next" class="carousel-btn carousel-btn-next">
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
        </div>`;

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
                const total = this.todosLosIndices.length;
                if (this.indiceActual + 3 < total) {
                    this.indiceActual = this.indiceActual + 3;
                    this.actualizarCarousel();
                }
            });
        }

        this.actualizarEstadoBotones();
        this.renderizarGrafica();
        this.agregarEventosZoom();
    }

    agregarEventosZoom() {
        // Agregar eventos click a todas las imágenes del carrusel
        const imagenes = document.querySelectorAll('.carousel-img');
        imagenes.forEach((img, idx) => {
            img.style.cursor = 'pointer';
            img.addEventListener('click', () => {
                const indiceGlobal = this.indiceActual + idx;
                this.abrirZoom(indiceGlobal);
            });
        });
    }

    renderizarImagenes() {
        const total = this.todosLosIndices.length;
        const inicio = this.indiceActual;
        const fin = Math.min(inicio + 3, total);
        const imagenes = this.todosLosIndices.slice(inicio, fin);

        if (imagenes.length === 0) {
            return '<p class="text-muted">No hay imágenes para mostrar</p>';
        }

        return imagenes.map((indice) => {
            let rutaImagen = indice.ruta_ndvi;

            if (rutaImagen) {
                rutaImagen = rutaImagen.replace(/^webapp\//, '');
                if (!rutaImagen.startsWith('/')) {
                    rutaImagen = '/' + rutaImagen;
                }
            } else {
                rutaImagen = `/static/thumbnails/${indice.fecha_ndvi ? indice.fecha_ndvi.replace(/-/g, '').substring(0, 8) : 'unknown'}_${this.recintoId}.png`;
            }

            const fecha = indice.fecha_ndvi_formateada || 'N/A';

            return `<div class="carousel-item" style="margin-right: 8px;">
                <img src="${rutaImagen}"
                    alt="NDVI ${fecha}"
                    class="carousel-img"
                    style="object-fit: contain; background: #f8f9fa;"
                    onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22110%22 height=%22110%22><rect width=%22110%22 height=%22110%22 fill=%22%23e9ecef%22/><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%236c757d%22 font-size=%2212%22>Sin imagen</text></svg>'">
                <div class="carousel-item-info">
                    <div class="fw-bold">${fecha}</div>
                    <div class="text-muted" style="font-size: 0.75rem;">Media: ${indice.valor_medio.toFixed(4)}</div>
                </div>
            </div>`;
        }).join('');
    }

    actualizarEstadoBotones() {
        const btnPrev = document.getElementById('btn-carousel-prev');
        const btnNext = document.getElementById('btn-carousel-next');
        const total = this.todosLosIndices.length;

        if (btnPrev) {
            btnPrev.disabled = this.indiceActual === 0;
        }

        if (btnNext) {
            btnNext.disabled = (this.indiceActual + 3) >= total;
        }
    }

    actualizarCarousel() {
        const carouselEl = document.getElementById('carousel-images');
        const total = this.todosLosIndices.length;

        if (carouselEl) {
            carouselEl.innerHTML = this.renderizarImagenes();
        }

        this.actualizarEstadoBotones();
        this.agregarEventosZoom();

        const contador = document.getElementById('contador-carousel');
        if (contador) {
            contador.textContent = `Mostrando ${this.indiceActual + 1} - ${Math.min(this.indiceActual + 3, total)} de ${total}`;
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
                container.innerHTML = '<canvas id="ndvi-chart-canvas"></canvas>';

                const ctx = document.getElementById('ndvi-chart-canvas').getContext('2d');

                if (this.chartInstance) {
                    this.chartInstance.destroy();
                }



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
                            tension: 0.4,
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
                        layout: {},
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

        if (this.panelDetalleAbierto) {
            await this.cargarDetalleNDVI();
        }
        
        await this.cargarYMostrar();
    }

    async cargarYMostrar() {
        if (!this.recintoId) {
            this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver NDVI</p>';
            return;
        }

        try {
            const response = await fetch(`/api/indices-raster?id_recinto=${this.recintoId}&tipo_indice=NDVI`);

            if (!response.ok) {
                throw new Error('Error al cargar NDVI');
            }

            const indices = await response.json();

            if (!indices || indices.length === 0) {
                this.container.innerHTML = `<div class="text-muted text-center py-3">
                    <i class="fa-solid fa-leaf mb-2" style="font-size: 2rem; opacity: 0.3;"></i>
                    <p class="mb-0">No hay datos NDVI disponibles</p>
                </div>`;
                return;
            }

            this.todosLosIndices = indices;
            const ultimoIndice = indices[0];

            let rutaImagen = ultimoIndice.ruta_ndvi;

            if (rutaImagen) {
                rutaImagen = rutaImagen.replace(/^webapp\//, '');
                if (!rutaImagen.startsWith('/')) {
                    rutaImagen = '/' + rutaImagen;
                }
            }

            if (!rutaImagen) {
                rutaImagen = `/static/thumbnails/${ultimoIndice.fecha_ndvi ? ultimoIndice.fecha_ndvi.replace(/-/g, '').substring(0, 8) : 'unknown'}_${this.recintoId}.png`;
            }

            this.container.innerHTML = `<div class="ndvi-card">
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
            </div>`;
        } catch (error) {
            console.error('Error:', error);
            this.container.innerHTML = '<p class="text-danger">Error cargando NDVI</p>';
        }
    }
}

window.ndviManager = null;
document.addEventListener('DOMContentLoaded', () => {
    window.ndviManager = new NDVI('ndvi-container');
});