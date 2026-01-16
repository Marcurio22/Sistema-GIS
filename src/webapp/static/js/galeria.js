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
    this.initEdicion();
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
      this.container.innerHTML = '<p class="text-muted">No hay imágenes en este recinto. </p>';
      return;
    }

    const imagenesAMostrar = this.mostrandoTodas 
      ? this.imagenes 
      : this.imagenes.slice(0, this.maxVisibles);

    imagenesAMostrar.forEach((imagen, index) => {
      const item = document.createElement('div');
      item.className = 'galeria-item';
      
      item.innerHTML = `
      <img src="${imagen.thumb}" alt="${imagen.titulo}" loading="lazy">
      <div class="galeria-overlay">
        <h4>${imagen.titulo}</h4>
        <p>${imagen.descripcion || ''}</p>
      </div>
      <div class="galeria-actions">
        <button class="galeria-action-btn edit" data-id="${imagen.id}" data-index="${index}" title="Editar">
          <i class="bi bi-pencil-fill"></i>
        </button>
        <button class="galeria-action-btn delete" data-id="${imagen.id}" title="Eliminar">
          <i class="bi bi-trash-fill"></i>
        </button>
      </div>
    `;

      const imgElement = item.querySelector('img');
      const overlayElement = item.querySelector('.galeria-overlay');
      
      imgElement.onclick = () => this.openLightbox(index);
      overlayElement.onclick = () => this.openLightbox(index);

      const editBtn = item.querySelector('.edit');
      editBtn.onclick = (e) => {
        e.stopPropagation();
        this.abrirModalEditar(imagen);
      };

      const deleteBtn = item.querySelector('.delete');
      deleteBtn.onclick = (e) => {
        e.stopPropagation();
        this.confirmarEliminar(imagen);
      };

      this.container.appendChild(item);
    });

    // Botón toggle
    if (this.imagenes.length > this.maxVisibles) {
      const toggleBtn = document.createElement('div');
      toggleBtn.className = 'galeria-item galeria-ver-mas';
      
      if (this.mostrandoTodas) {
        toggleBtn.innerHTML = `
          <div class="ver-mas">
            <span>▲</span>
            <p>Mostrar menos</p>
          </div>
        `;
        toggleBtn.onclick = () => {
          this.contraerGaleria();
        };
      } else {
        toggleBtn.innerHTML = `
          <div class="ver-mas">
            <span>+${this.imagenes.length - this.maxVisibles}</span>
            <p>Ver todas</p>
          </div>
        `;
        toggleBtn.onclick = () => {
          this.expandirGaleria();
        };
      }
      
      this.container.appendChild(toggleBtn);
    }
  }

  expandirGaleria() {
  this.mostrandoTodas = true;
  this.modoExpandido = true;
  
  // Ocultar el resto del contenido del panel
  const sideHeader = document.querySelector('.side-header');
  const sideDividers = document.querySelectorAll('.side-divider');
  const sideRows = document.querySelectorAll('.side-row');
  const sideToggle = document.querySelector('.side-toggle');
  const cultivos = document.getElementById('cultivos-container');
  const cultivosSection = document.querySelector('.side-section');
  const galeriaContainer = document.getElementById('galeria-imagenes');
  
  // Ocultar también el título "Galería" y el botón "Añadir Imagen" original
  const galeriaTitulo = galeriaContainer?.querySelector('.side-section-title');
  const galeriaBotonAnadir = galeriaContainer?.querySelector('button[data-bs-target="#modalSubida"]');
  
  // Guardar elementos ocultos para restaurar
  this.elementosOcultos = [
    sideHeader,
    ...sideDividers,
    ...sideRows,
    sideToggle,
    cultivos,
    cultivosSection,
    galeriaTitulo,
    galeriaBotonAnadir
  ].filter(el => el && el !== null);
  
  // Ocultar elementos
  this.elementosOcultos.forEach(el => {
    el.style.display = 'none';
  });
  
  // Añadir header de galería expandida
  const galeriaHeader = document.createElement('div');
  galeriaHeader.id = 'galeria-header-expandido';
  galeriaHeader.className = 'galeria-header-expandido';
  galeriaHeader.innerHTML = `
    <div class="galeria-header-top">
      <button class="btn btn-sm btn-outline-secondary" id="btn-contraer-galeria">
        <i class="bi bi-arrow-left me-1"></i> Volver
      </button>
      <h2 class="galeria-titulo-principal">
        <i class="fa-solid fa-image me-2" style="color:#198754;"></i>
        Galería
      </h2>
    </div>
    <div class="galeria-header-divider"></div>
    <div class="galeria-header-bottom">
      <h3 class="galeria-subtitulo">
        Galería completa
        <span class="badge bg-success ms-2">${this.imagenes.length}</span>
      </h3>
      <button type="button" class="btn btn-success btn-sm" data-bs-toggle="modal" data-bs-target="#modalSubida">
        <i class="fa-solid fa-plus me-1"></i> Añadir Imagen
      </button>
    </div>
  `;
  
  // Insertar header antes del contenedor de galería
  if (galeriaContainer && galeriaContainer.parentNode) {
    galeriaContainer.parentNode.insertBefore(galeriaHeader, galeriaContainer);
  }
  
  // Evento para contraer
  document.getElementById('btn-contraer-galeria').onclick = () => {
    this.contraerGaleria();
  };
  
  // Re-renderizar con todas las imágenes
  this.renderizarGaleria();
  
  // Scroll al inicio del panel
  const sidePanel = document.getElementById('side-panel');
  if (sidePanel) {
    sidePanel.scrollTop = 0;
  }
}
  contraerGaleria() {
    this.mostrandoTodas = false;
    this.modoExpandido = false;
    
    // Eliminar header de galería expandida
    const galeriaHeader = document.getElementById('galeria-header-expandido');
    if (galeriaHeader) {
      galeriaHeader.remove();
    }
    
    // Restaurar elementos ocultos
    if (this.elementosOcultos) {
      this.elementosOcultos.forEach(el => {
        el.style.display = '';
      });
      this.elementosOcultos = null;
    }
    
    // Re-renderizar con imágenes limitadas
    this.renderizarGaleria();
    
    // Scroll a la galería
    const galeriaContainer = document.getElementById('galeria-imagenes');
    if (galeriaContainer) {
      galeriaContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  abrirModalEditar(imagen) {
    document.getElementById('editar-id-imagen').value = imagen.id;
    document.getElementById('editar-titulo').value = imagen.titulo;
    document.getElementById('editar-descripcion').value = imagen.descripcion || '';
    document.getElementById('editar-preview').src = imagen.thumb;

    const modal = new bootstrap.Modal(document.getElementById('modalEditar'));
    modal.show();
  }

   abrirModalEditar(imagen) {
    document.getElementById('editar-id-imagen').value = imagen.id;
    document.getElementById('editar-titulo').value = imagen.titulo;
    document.getElementById('editar-descripcion').value = imagen.descripcion || '';
    document.getElementById('editar-preview').src = imagen.thumb;

    const modal = new bootstrap.Modal(document.getElementById('modalEditar'));
    modal.show();
  }

  initEdicion() {
    const form = document.getElementById('form-editar');
    form.onsubmit = async (e) => {
      e.preventDefault();

      const idImagen = document.getElementById('editar-id-imagen').value;
      const titulo = document.getElementById('editar-titulo').value;
      const descripcion = document.getElementById('editar-descripcion').value;

      try {
        const res = await fetch(`/api/galeria/editar/${idImagen}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ titulo, descripcion })
        });

        if (!res.ok) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.error || "Error al editar la imagen");
        }

        await this.cargarImagenes();

        const modalEl = document.getElementById('modalEditar');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();

        NotificationSystem.show({
          type: "success",
          title: "¡Imagen actualizada!",
          message: `Los cambios en "${titulo}" se han guardado correctamente`
        });

      } catch (error) {
        console.error(error);
        NotificationSystem.show({
          type: "error",
          title: "Error al editar",
          message: error.message || "No se pudo editar la imagen"
        });
      }
    };
  }

  async confirmarEliminar(imagen) {
    // Usar el sistema de confirmación que ya tienes en visor.html
    const ok = await AppConfirm.open({
      title: "Eliminar imagen",
      message: `¿Estás seguro de que deseas eliminar "${imagen.titulo}"? Esta acción no se puede deshacer.`,
      okText: "Eliminar",
      cancelText: "Cancelar",
      okClass: "btn-danger"
    });

    if (!ok) return;

    try {
      const res = await fetch(`/api/galeria/eliminar/${imagen.id}`, {
        method: 'DELETE'
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.error || "Error al eliminar la imagen");
      }

      await this.cargarImagenes();

      NotificationSystem.show({
        type: "success",
        title: "Imagen eliminada",
        message: `"${imagen.titulo}" ha sido eliminada correctamente`
      });

    } catch (error) {
      console.error(error);
      NotificationSystem.show({
        type: "error",
        title: "Error al eliminar",
        message: error.message || "No se pudo eliminar la imagen"
      });
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