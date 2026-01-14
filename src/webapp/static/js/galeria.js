class GaleriaImagenes {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.modal = document.getElementById('modal-imagen');
    this.modalImg = document.getElementById('img-modal');
    this.caption = document.getElementById('caption');

    this.imagenes = [];
    this.maxVisibles = 5;
    this.mostrandoTodas = false;

    this.init();
  }

  init() {
    // Botón cerrar modal
    const closeBtn = document.querySelector('.modal-close');
    closeBtn.onclick = () => this.cerrarModal();

    // Cerrar al clicar fuera
    this.modal.onclick = (e) => {
      if (e.target === this.modal) {
        this.cerrarModal();
      }
    };

    // Cerrar con ESC
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.modal.style.display === 'block') {
        this.cerrarModal();
      }
    });

    this.cargarImagenes();
  }

  async cargarImagenes() {
    try {
      this.container.innerHTML = '<div class="galeria-loading">Cargando imágenes...</div>';

      // IMÁGENES DE EJEMPLO
      this.imagenes = [
        { id: 1, thumb: 'https://picsum.photos/400/300?1', full: 'https://picsum.photos/1600/1200?1', titulo: 'Imagen 1', descripcion: 'Descripción 1' },
        { id: 2, thumb: 'https://picsum.photos/400/300?2', full: 'https://picsum.photos/1600/1200?2', titulo: 'Imagen 2', descripcion: 'Descripción 2' },
        { id: 3, thumb: 'https://picsum.photos/400/300?3', full: 'https://picsum.photos/1600/1200?3', titulo: 'Imagen 3', descripcion: 'Descripción 3' },
        { id: 4, thumb: 'https://picsum.photos/400/300?4', full: 'https://picsum.photos/1600/1200?4', titulo: 'Imagen 4', descripcion: 'Descripción 4' },
        { id: 5, thumb: 'https://picsum.photos/400/300?5', full: 'https://picsum.photos/1600/1200?5', titulo: 'Imagen 5', descripcion: 'Descripción 5' },
        { id: 6, thumb: 'https://picsum.photos/400/300?6', full: 'https://picsum.photos/1600/1200?6', titulo: 'Imagen 6', descripcion: 'Descripción 6' },
      ];

      this.renderizarGaleria();
    } catch (error) {
      console.error(error);
      this.container.innerHTML = '<div>Error cargando imágenes</div>';
    }
  }

  renderizarGaleria() {
    this.container.innerHTML = '';

    const imagenesAMostrar = this.mostrandoTodas
      ? this.imagenes
      : this.imagenes.slice(0, this.maxVisibles);

    imagenesAMostrar.forEach(imagen => {
      const item = document.createElement('div');
      item.className = 'galeria-item';
      item.onclick = () => this.abrirModal(imagen);

      item.innerHTML = `
        <img src="${imagen.thumb}" alt="${imagen.titulo}" loading="lazy">
        <div class="galeria-overlay">
          <h4>${imagen.titulo}</h4>
          <p>${imagen.descripcion}</p>
        </div>
      `;

      this.container.appendChild(item);
    });

    // TARJETA "VER TODAS"
    if (!this.mostrandoTodas && this.imagenes.length > this.maxVisibles) {
      const verMas = document.createElement('div');
      verMas.className = 'galeria-item galeria-ver-mas';
      verMas.innerHTML = `
        <div class="ver-mas">
          <span>+${this.imagenes.length - this.maxVisibles}</span>
          <p>Ver todas / Subir imágenes</p>
        </div>
      `;
      verMas.onclick = () => {
        this.mostrandoTodas = true;
        this.renderizarGaleria();
      };
      this.container.appendChild(verMas);
    }
  }

  abrirModal(imagen) {
    this.modal.style.display = 'block';
    this.modalImg.src = imagen.full;
    this.caption.textContent = `${imagen.titulo} - ${imagen.descripcion}`;

    document.body.style.overflow = 'hidden';
    document.body.classList.add('modal-abierto');
  }

  cerrarModal() {
    this.modal.style.display = 'none';
    this.modalImg.src = '';
    document.body.style.overflow = 'auto';
    document.body.classList.remove('modal-abierto');
  }
}

// INICIAR
document.addEventListener('DOMContentLoaded', () => {
  new GaleriaImagenes('galeria-grid');
});
