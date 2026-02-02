class GaleriaImagenes {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.imagenes = [];
    this.maxVisibles = 5;
    this.mostrandoTodas = false;
    this.recintoId = null;
    this.init();
  }

  init() {
    this.initSubida();
    this.initEdicion();
    this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver sus imágenes</p>';
  }

  // Extraer coordenadas de geometría WKT (ej: "POINT(lon lat)")
  extraerCoordenadas(geom) {
    if (!geom) return null;
    
    // Si es string WKT: "POINT(-3.12345 42.67890)"
    const match = geom.match(/POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)/i);
    if (match) {
      return {
        lon: parseFloat(match[1]),
        lat: parseFloat(match[2])
      };
    }
    
    return null;
  }

  formatearCoordenadas(coords) {
    if (!coords) return '';
    return `Lat: ${coords.lat.toFixed(6)}, Lon: ${coords.lon.toFixed(6)}`;
  }

  async setRecintoId(recintoId) {
    this.recintoId = recintoId;
    await this.cargarImagenes();
  }

  async cargarImagenes() {
    if (!this.recintoId) {
      this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver sus imágenes</p>';
      
      // Actualizar lightbox manager con array vacío
      if (window.lightboxManager) {
        window.lightboxManager.updateImages([], null);
      }
      
      return;
    }

    try {
      this.container.innerHTML = '<p>Cargando imágenes...</p>';

      const response = await fetch(`/api/galeria/listar/${this.recintoId}`);
      
      if (!response.ok) {
        throw new Error('Error al cargar imágenes');
      }

      this.imagenes = await response.json();
      
      console.log(`Galería: Cargadas ${this.imagenes.length} imágenes para recinto ${this.recintoId}`);
      console.log('Galería: Primeras 3 imágenes:', this.imagenes.slice(0, 3).map(img => img.titulo));
      
      // ✅ ACTUALIZAR LIGHTBOX MANAGER CON LAS NUEVAS IMÁGENES
      if (window.lightboxManager) {
        console.log('Galería: Actualizando lightboxManager...');
        window.lightboxManager.updateImages(this.imagenes, this.recintoId);
      } else {
        console.error('Galería: lightboxManager no está disponible!');
      }
      
      this.renderizarGaleria();
      
    } catch (error) {
      console.error(error);
      this.container.innerHTML = '<p class="text-danger">Error cargando imágenes</p>';
      
      // Limpiar lightbox manager en caso de error
      if (window.lightboxManager) {
        window.lightboxManager.updateImages([], null);
      }
    }
  }

renderizarGaleria() {
    this.container.innerHTML = '';
    
    // Actualizar contador de imágenes
    const countEl = document.getElementById('galeria-count');
    if (countEl) countEl.textContent = String(this.imagenes.length || 0);
    
    if (this.imagenes.length === 0) {
      this.container.innerHTML = '<p class="text-muted">No hay imágenes en este recinto. </p>';
      return;
    }

    const imagenesAMostrar = this.mostrandoTodas 
      ? this.imagenes 
      : this.imagenes.slice(0, this.maxVisibles);

    imagenesAMostrar.forEach((imagen, localIndex) => {
      const item = document.createElement('div');
      item.className = 'galeria-item';
      
      // Encontrar el índice real en el array completo
      const indiceReal = this.imagenes.findIndex(img => img.id === imagen.id);
      
      const coords = this.extraerCoordenadas(imagen.geom);
      const coordsHTML = coords ? `<small class="d-block mt-1" style="color: #17a2b8; font-weight: 500;">${this.formatearCoordenadas(coords)}</small>` : '';
      
      item.innerHTML = `
      <img src="${imagen.thumb}" alt="${imagen.titulo}" loading="lazy">
      <div class="galeria-overlay">
        <h4>${imagen.titulo}</h4>
        <p>${imagen.descripcion || ''}</p>
        ${coordsHTML}
      </div>
      <div class="galeria-actions">
        <button class="galeria-action-btn edit" data-id="${imagen.id}" data-index="${indiceReal}" title="Editar">
          <i class="bi bi-pencil-fill"></i>
        </button>
        <button class="galeria-action-btn delete" data-id="${imagen.id}" title="Eliminar">
          <i class="bi bi-trash-fill"></i>
        </button>
      </div>
    `;

      const imgElement = item.querySelector('img');
      const overlayElement = item.querySelector('.galeria-overlay');
      
      // ✅ USAR LIGHTBOX MANAGER PARA ABRIR CON EL ÍNDICE REAL
      imgElement.onclick = () => {
        console.log(`Galería: Click en imagen. Local index: ${localIndex}, Índice real: ${indiceReal}`);
        console.log(`Galería: Imagen clickeada:`, imagen.titulo);
        if (window.lightboxManager) {
          window.lightboxManager.open(indiceReal);
        } else {
          console.error('Galería: lightboxManager no disponible al hacer click');
        }
      };
      
      overlayElement.onclick = () => {
        console.log(`Galería: Click en overlay. Local index: ${localIndex}, Índice real: ${indiceReal}`);
        if (window.lightboxManager) {
          window.lightboxManager.open(indiceReal);
        }
      };

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
    // Abrir overlay (lo maneja visor.html)
    if (typeof window.openGaleriaPanel === "function") {
      window.openGaleriaPanel();
    }

    // En overlay mostramos todas
    this.mostrandoTodas = true;
    this.renderizarGaleria();

    // Scroll arriba del overlay
    const overlay = document.getElementById("galeria-panel");
    if (overlay) overlay.scrollTop = 0;
  }

  contraerGaleria() {
    // Volver al modo normal (panel general)
    this.mostrandoTodas = false;
    this.renderizarGaleria();

    // Cerrar overlay y devolver el DOM a su sitio
    if (typeof window.closeGaleriaPanel === "function") {
      window.closeGaleriaPanel();
    }

    // Scroll a la sección galería en el panel general
    const galeriaContainer = document.getElementById("galeria-imagenes");
    if (galeriaContainer) {
      galeriaContainer.scrollIntoView({ behavior: "smooth", block: "nearest" });
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

      const maxSize = 12 * 1024 * 1024;
      if (file.size > maxSize) {
        NotificationSystem.show({
          type: "error",
          title: "Archivo muy grande",
          message: "La imagen no puede superar los 12MB"
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