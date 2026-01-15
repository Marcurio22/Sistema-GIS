class GaleriaImagenes {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.imagenes = [];
    this.maxVisibles = 5;
    this.mostrandoTodas = false;
    this.recintoId = null;
    this.currentImageIndex = 0; // Para navegación en lightbox
    this.init();
  }

  init() {
    this.initSubida();
    this.initLightbox();
    this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver sus imágenes</p>';
  }

  initLightbox() {
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const lightboxCaption = document.getElementById('lightbox-caption');
    const closeBtn = document.querySelector('.lightbox-close');
    const prevBtn = document.getElementById('lightbox-prev');
    const nextBtn = document.getElementById('lightbox-next');

    // Cerrar con el botón X
    if (closeBtn) {
      closeBtn.onclick = () => this.closeLightbox();
    }

    // Cerrar al hacer clic fuera de la imagen
    if (lightbox) {
      lightbox.onclick = (e) => {
        if (e.target === lightbox) {
          this.closeLightbox();
        }
      };
    }

    // Cerrar con tecla ESC
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && lightbox.style.display === 'block') {
        this.closeLightbox();
      }
      // Navegación con flechas
      if (lightbox.style.display === 'block') {
        if (e.key === 'ArrowLeft') this.showPrevImage();
        if (e.key === 'ArrowRight') this.showNextImage();
      }
    });

    // Botones de navegación
    if (prevBtn) prevBtn.onclick = () => this.showPrevImage();
    if (nextBtn) nextBtn.onclick = () => this.showNextImage();
  }

  openLightbox(index) {
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const lightboxCaption = document.getElementById('lightbox-caption');

    this.currentImageIndex = index;
    const imagen = this.imagenes[index];

    lightbox.style.display = 'block';
    lightboxImg.src = imagen.thumb;
    lightboxCaption.innerHTML = `
      <strong>${imagen.titulo}</strong>
      ${imagen.descripcion ? '<br>' + imagen.descripcion : ''}
    `;

    // Deshabilitar scroll del body
    document.body.style.overflow = 'hidden';
  }

  closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    lightbox.style.display = 'none';
    document.body.style.overflow = '';
  }

  showPrevImage() {
    this.currentImageIndex = (this.currentImageIndex - 1 + this.imagenes.length) % this.imagenes.length;
    this.openLightbox(this.currentImageIndex);
  }

  showNextImage() {
    this.currentImageIndex = (this.currentImageIndex + 1) % this.imagenes.length;
    this.openLightbox(this.currentImageIndex);
  }

  async setRecintoId(recintoId) {
    this.recintoId = recintoId;
    await this.cargarImagenes();
  }

  async cargarImagenes() {
    if (!this.recintoId) {
      this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver sus imágenes</p>';
      return;
    }

    try {
      this.container.innerHTML = '<p>Cargando imágenes...</p>';

      const response = await fetch(`/api/galeria/listar/${this.recintoId}`);
      
      if (!response.ok) {
        throw new Error('Error al cargar imágenes');
      }

      this.imagenes = await response.json();
      this.renderizarGaleria();
      
    } catch (error) {
      console.error(error);
      this.container.innerHTML = '<p class="text-danger">Error cargando imágenes</p>';
    }
  }

  renderizarGaleria() {
    this.container.innerHTML = '';
    
    if (this.imagenes.length === 0) {
      this.container.innerHTML = '<p class="text-muted">No hay imágenes en este recinto. Añade una usando el botón de arriba.</p>';
      return;
    }

    const imagenesAMostrar = this.mostrandoTodas 
      ? this.imagenes 
      : this.imagenes.slice(0, this.maxVisibles);

    imagenesAMostrar.forEach((imagen, index) => {
      const item = document.createElement('div');
      item.className = 'galeria-item';
      
      // Añadir evento click para abrir lightbox
      item.onclick = () => {
        // Si estamos mostrando solo algunas, ajustar el índice
        const realIndex = this.mostrandoTodas ? index : index;
        this.openLightbox(realIndex);
      };

      item.innerHTML = `
        <img src="${imagen.thumb}" alt="${imagen.titulo}" loading="lazy">
        <div class="galeria-overlay">
          <h4>${imagen.titulo}</h4>
          <p>${imagen.descripcion || ''}</p>
        </div>
      `;

      this.container.appendChild(item);
    });

    if (!this.mostrandoTodas && this.imagenes.length > this.maxVisibles) {
      const verMas = document.createElement('div');
      verMas.className = 'galeria-item galeria-ver-mas';
      verMas.innerHTML = `
        <div class="ver-mas">
          <span>+${this.imagenes.length - this.maxVisibles}</span>
          <p>Ver todas</p>
        </div>
      `;
      verMas.onclick = () => {
        this.mostrandoTodas = true;
        this.renderizarGaleria();
      };
      this.container.appendChild(verMas);
    }
  }

  initSubida() {
    const form = document.getElementById('form-subida');
    form.onsubmit = async (e) => {
      e.preventDefault();

      const fileInput = document.getElementById('imagen-file');
      const titulo = document.getElementById('imagen-titulo').value;
      const descripcion = document.getElementById('imagen-descripcion').value;

      if (!fileInput.files.length) {
        NotificationSystem.show({
          type: "warning",
          title: "Falta imagen",
          message: "Por favor, selecciona una imagen antes de continuar"
        });
        return;
      }

      const recintoId = this.recintoId || window.currentSideRecintoId;

      if (!recintoId) {
        NotificationSystem.show({
          type: "warning",
          title: "Sin recinto",
          message: "Abre un recinto antes de subir imágenes"
        });
        return;
      }

      const file = fileInput.files[0];
      const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
      
      if (!allowedTypes.includes(file.type)) {
        NotificationSystem.show({
          type: "error",
          title: "Archivo no válido",
          message: "Solo se permiten imágenes (JPG, PNG, GIF, WEBP)"
        });
        return;
      }

      const maxSize = 5 * 1024 * 1024;
      if (file.size > maxSize) {
        NotificationSystem.show({
          type: "error",
          title: "Archivo muy grande",
          message: "La imagen no puede superar los 5MB"
        });
        return;
      }

      const formData = new FormData();
      formData.append('imagen', file);
      formData.append('titulo', titulo);
      formData.append('descripcion', descripcion);
      formData.append('recinto_id', recintoId);

      try {
        const res = await fetch('/api/galeria/subir', {
          method: 'POST',
          body: formData
        });

        if (!res.ok) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.error || "Error al subir la imagen");
        }

        const nuevaImagen = await res.json();
        
        await this.cargarImagenes();

        const modalEl = document.getElementById('modalSubida');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();

        form.reset();
        
        NotificationSystem.show({
          type: "success",
          title: "¡Imagen subida!",
          message: `"${titulo}" se ha añadido correctamente a la galería`
        });
        
      } catch (error) {
        console.error(error);
        
        NotificationSystem.show({
          type: "error",
          title: "Error al subir",
          message: error.message || "No se pudo subir la imagen. Intenta de nuevo."
        });
      }
    };
  }
}

window.galeria = null;
document.addEventListener('DOMContentLoaded', () => {
  window.galeria = new GaleriaImagenes('galeria-grid');
});