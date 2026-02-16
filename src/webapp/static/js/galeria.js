class GaleriaImagenes {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.imagenes = [];
    this.maxVisibles = 5;
    this.mostrandoTodas = false;
    this.recintoId = null;
    this.ultimaUbicacion = null;
    this.gpsYaSolicitado = false;
    this.archivoSeleccionado = false;
    this._modalListenersConfigured = false;
    this.init();
  }

  init() {
    this.initSubida();
    this.initEdicion();
    this.setupCameraOption();
    this.setupModalListeners();
    this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver sus imágenes</p>';
  }

  // ✅ Solo resetear al cerrar, NO pedir GPS al abrir
  setupModalListeners() {
    const modalSubida = document.getElementById('modalSubida');
    if (!modalSubida || this._modalListenersConfigured) return;
    
    modalSubida.addEventListener('hidden.bs.modal', () => {
      this.resetearEstadoCompleto();
    });

    this._modalListenersConfigured = true;
  }

  resetearEstadoCompleto() {
    this.ultimaUbicacion = null;
    this.gpsYaSolicitado = false;
    this.archivoSeleccionado = false;
    
    const gpsStatus = document.getElementById('gps-status');
    if (gpsStatus) {
      gpsStatus.classList.add('d-none');
      gpsStatus.classList.remove('text-success', 'text-warning', 'text-info');
      gpsStatus.innerHTML = '';
    }
    
    const archivoSeleccionado = document.getElementById('archivo-seleccionado');
    if (archivoSeleccionado) {
      archivoSeleccionado.textContent = 'Ningún archivo seleccionado';
      archivoSeleccionado.style.color = '';
      archivoSeleccionado.style.fontWeight = '';
    }
    
    const fileInput = document.getElementById('imagen-file');
    if (fileInput) {
      fileInput.value = '';
    }
  }

  setupCameraOption() {
    const fileInput = document.getElementById('imagen-file');
    if (!fileInput) return;
    
    if (this.isMobile()) {
      fileInput.style.display = 'none';
      
      const btnContainer = document.createElement('div');
      btnContainer.className = 'mb-3';
      btnContainer.innerHTML = `
        <label class="form-label">Selecciona Imagen</label>
        <div class="d-grid gap-2">
          <button type="button" class="btn btn-outline-success" id="btn-elegir-archivo">
            <i class="bi bi-folder2-open me-2"></i>Elegir desde Galería
          </button>
          <button type="button" class="btn btn-outline-success" id="btn-tomar-foto">
            <i class="bi bi-camera-fill me-2"></i>Tomar Foto
          </button>
        </div>
        <small class="text-muted d-block mt-2" id="archivo-seleccionado">Ningún archivo seleccionado</small>
        <small class="d-none mt-1 d-block" id="gps-status"></small>
      `;
      
      fileInput.parentNode.insertBefore(btnContainer, fileInput);
      
      // ✅ PEDIR GPS CUANDO HAGA CLIC EN GALERÍA
      document.getElementById('btn-elegir-archivo').addEventListener('click', async () => {
        await this.solicitarPermisoUbicacion(); // ← AQUÍ
        fileInput.removeAttribute('capture');
        fileInput.click();
      });
      
      // ✅ PEDIR GPS CUANDO HAGA CLIC EN TOMAR FOTO
      document.getElementById('btn-tomar-foto').addEventListener('click', async () => {
        await this.solicitarPermisoUbicacion(); // ← AQUÍ
        fileInput.setAttribute('capture', 'environment');
        fileInput.click();
      });
      
      fileInput.addEventListener('change', (e) => {
        const archivoSeleccionado = document.getElementById('archivo-seleccionado');
        if (e.target.files.length > 0) {
          this.archivoSeleccionado = true;
          archivoSeleccionado.textContent = `📷 ${e.target.files[0].name}`;
          archivoSeleccionado.style.color = '#198754';
          archivoSeleccionado.style.fontWeight = '600';
        } else {
          this.archivoSeleccionado = false;
          archivoSeleccionado.textContent = 'Ningún archivo seleccionado';
          archivoSeleccionado.style.color = '';
          archivoSeleccionado.style.fontWeight = '';
        }
      });
    } else {
      // ✅ En escritorio, pedir GPS cuando seleccione archivo
      fileInput.addEventListener('click', async () => {
        await this.solicitarPermisoUbicacion();
      });
      
      fileInput.addEventListener('change', (e) => {
        this.archivoSeleccionado = e.target.files.length > 0;
      });
    }
  }

  async solicitarPermisoUbicacion() {
    if (this.gpsYaSolicitado) {
      return this.ultimaUbicacion;
    }

    if (!navigator.geolocation) {
      this.gpsYaSolicitado = true;
      return null;
    }

    const gpsStatus = document.getElementById('gps-status');
    this.gpsYaSolicitado = true;
    
    if (gpsStatus) {
      gpsStatus.classList.remove('d-none', 'text-success', 'text-warning');
      gpsStatus.classList.add('text-info');
      gpsStatus.innerHTML = '<i class="bi bi-geo-alt"></i> Obteniendo ubicación...';
    }
    
    try {
      const position = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
          pos => resolve(pos),
          error => reject(error),
          {
            enableHighAccuracy: true,
            timeout: 20000,
            maximumAge: 0
          }
        );
      });

      this.ultimaUbicacion = {
        lat: position.coords.latitude,
        lon: position.coords.longitude,
        accuracy: position.coords.accuracy,
        timestamp: Date.now()
      };
      
      if (gpsStatus) {
        gpsStatus.classList.remove('d-none', 'text-warning', 'text-info');
        gpsStatus.classList.add('text-success');
        gpsStatus.innerHTML = `<i class="bi bi-geo-alt-fill"></i> GPS capturado ✓ (±${Math.round(position.coords.accuracy)}m)`;
      }
      
      return this.ultimaUbicacion;

    } catch (error) {
      this.ultimaUbicacion = null;
      
      if (gpsStatus) {
        gpsStatus.classList.remove('d-none', 'text-success', 'text-info');
        gpsStatus.classList.add('text-warning');
        
        switch (error.code) {
          case 1:
            gpsStatus.innerHTML = '<i class="bi bi-geo-alt"></i> Permiso GPS denegado';
            break;
          case 2:
            gpsStatus.innerHTML = '<i class="bi bi-geo-alt"></i> GPS no disponible';
            break;
          case 3:
            gpsStatus.innerHTML = '<i class="bi bi-geo-alt"></i> Timeout GPS';
            break;
          default:
            gpsStatus.innerHTML = '<i class="bi bi-geo-alt"></i> Error GPS';
        }
      }
      
      return null;
    }
  }

  isMobile() {
    const userAgent = navigator.userAgent.toLowerCase();
    const isMobileDevice = /android|webos|iphone|ipod|blackberry|iemobile|opera mini/i.test(userAgent);
    const isSmallScreen = window.innerWidth <= 576;
    return isMobileDevice && isSmallScreen;
  }

  extraerCoordenadas(geom) {
    if (!geom) return null;
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
      
      if (window.lightboxManager) {
        window.lightboxManager.updateImages(this.imagenes, this.recintoId);
      }
      
      this.renderizarGaleria();
      
    } catch (error) {
      console.error(error);
      this.container.innerHTML = '<p class="text-danger">Error cargando imágenes</p>';
      if (window.lightboxManager) {
        window.lightboxManager.updateImages([], null);
      }
    }
  }

  renderizarGaleria() {
    if (!this.container) return;

    const countEl = document.getElementById('galeria-count');
    if (countEl) countEl.textContent = String(this.imagenes.length || 0);

    if (this.imagenes.length === 0) {
      this.container.innerHTML = '<p class="text-muted">No hay imágenes en este recinto.</p>';
      return;
    }

    const imagenesAMostrar = this.mostrandoTodas 
      ? this.imagenes 
      : this.imagenes.slice(0, this.maxVisibles);

    const fragment = document.createDocumentFragment();

    imagenesAMostrar.forEach((imagen, localIndex) => {
        const item = document.createElement('div');
        item.className = 'galeria-item';

        const coords = this.extraerCoordenadas(imagen.geom);
        const coordsHTML = coords ? `<small class="d-block mt-1" style="color: #17a2b8; font-weight: 500;">${this.formatearCoordenadas(coords)}</small>` : '';

        item.innerHTML = `
            <img src="${imagen.thumb}" alt="${imagen.titulo}" loading="lazy" width="200" height="150">
            <div class="galeria-overlay">
                <h4>${imagen.titulo}</h4>
                <p>${imagen.descripcion || ''}</p>
                ${coordsHTML}
            </div>
            <div class="galeria-actions">
                <button class="galeria-action-btn edit" data-id="${imagen.id}" data-index="${localIndex}" title="Editar">
                    <i class="bi bi-pencil-fill"></i>
                </button>
                <button class="galeria-action-btn delete" data-id="${imagen.id}" title="Eliminar">
                    <i class="bi bi-trash-fill"></i>
                </button>
            </div>
        `;

        const imgElement = item.querySelector('img');
        const overlayElement = item.querySelector('.galeria-overlay');

        imgElement.onload = () => imgElement.classList.add('loaded');

        const indiceReal = this.imagenes.findIndex(img => img.id === imagen.id);
        
        const abrirLightbox = () => {
            if (window.lightboxManager) {
                window.lightboxManager.updateImages(this.imagenes, this.recintoId);
                window.lightboxManager.open(indiceReal);
            }
        };
        
        imgElement.onclick = abrirLightbox;
        overlayElement.onclick = abrirLightbox;

        const editBtn = item.querySelector('.edit');
        editBtn.onclick = (e) => { e.stopPropagation(); this.abrirModalEditar(imagen); };
        const deleteBtn = item.querySelector('.delete');
        deleteBtn.onclick = (e) => { e.stopPropagation(); this.confirmarEliminar(imagen); };

        fragment.appendChild(item);
    });

    if (this.imagenes.length > this.maxVisibles) {
        const toggleBtn = document.createElement('div');
        toggleBtn.className = 'galeria-item galeria-ver-mas';

        if (this.mostrandoTodas) {
            toggleBtn.innerHTML = `<div class="ver-mas"><span>▲</span><p>Mostrar menos</p></div>`;
            toggleBtn.onclick = () => this.contraerGaleria();
        } else {
            toggleBtn.innerHTML = `<div class="ver-mas"><span>+${this.imagenes.length - this.maxVisibles}</span><p>Ver todas</p></div>`;
            toggleBtn.onclick = () => this.expandirGaleria();
        }

        fragment.appendChild(toggleBtn);
    }

    this.container.innerHTML = '';
    this.container.appendChild(fragment);
  }

  expandirGaleria() {
    if (typeof window.openGaleriaPanel === "function") {
      window.openGaleriaPanel();
    }

    this.mostrandoTodas = true;
    this.renderizarGaleria();

    const overlay = document.getElementById("galeria-panel");
    if (overlay) overlay.scrollTop = 0;
  }

  contraerGaleria() {
    this.mostrandoTodas = false;
    this.renderizarGaleria();

    if (typeof window.closeGaleriaPanel === "function") {
      window.closeGaleriaPanel();
    }

    const galeriaContainer = document.getElementById("galeria-imagenes");
    if (galeriaContainer) {
      galeriaContainer.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  async confirmarEliminar(imagen) {
    const confirmar = await AppConfirm.open({
      title: '¿Eliminar imagen?',
      message: `¿Estás seguro de que quieres eliminar la imagen "${imagen.titulo}"?`,
      confirmText: 'Eliminar',
      cancelText: 'Cancelar',
      type: 'danger'
    });

    if (!confirmar) return;

    try {
      const res = await fetch(`/api/galeria/eliminar/${imagen.id}`, {
        method: 'DELETE'
      });

      if (!res.ok) {
        throw new Error('Error al eliminar la imagen');
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
        title: "Error",
        message: "No se pudo eliminar la imagen. Intenta de nuevo."
      });
    }
  }

  initEdicion() {
    const form = document.getElementById('form-editar');
    if (!form) return;

    form.onsubmit = async (e) => {
      e.preventDefault();

      const imagenId = document.getElementById('editar-imagen-id').value;
      const titulo = document.getElementById('editar-titulo').value.trim();
      const descripcion = document.getElementById('editar-descripcion').value.trim();

      if (!titulo) {
        NotificationSystem.show({
          type: "warning",
          title: "Campo requerido",
          message: "El título es obligatorio"
        });
        return;
      }

      try {
        const res = await fetch(`/api/galeria/editar/${imagenId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ titulo, descripcion })
        });

        if (!res.ok) {
          throw new Error('Error al actualizar la imagen');
        }

        await this.cargarImagenes();

        const modalEl = document.getElementById('modalEditar');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();

        NotificationSystem.show({
          type: "success",
          title: "Imagen actualizada",
          message: `"${titulo}" ha sido actualizada correctamente`
        });
        
      } catch (error) {
        console.error(error);
        NotificationSystem.show({
          type: "error",
          title: "Error",
          message: "No se pudo actualizar la imagen. Intenta de nuevo."
        });
      }
    };
  }

  abrirModalEditar(imagen) {
    document.getElementById('editar-imagen-id').value = imagen.id;
    document.getElementById('editar-titulo').value = imagen.titulo;
    document.getElementById('editar-descripcion').value = imagen.descripcion || '';
    document.getElementById('editar-preview').src = imagen.thumb;

    const modalEl = document.getElementById('modalEditar');
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
  }

  initSubida() {
    const form = document.getElementById('form-subida');
    if (!form) return;

    form.onsubmit = async (e) => {
      e.preventDefault();

      const fileInput = document.getElementById('imagen-file');
      const titulo = document.getElementById('imagen-titulo').value.trim();
      const descripcion = document.getElementById('imagen-descripcion').value.trim();

      if (!fileInput || !fileInput.files.length) {
        NotificationSystem.show({
          type: "warning",
          title: "Imagen requerida",
          message: "Selecciona una imagen para subir"
        });
        return;
      }

      if (!titulo) {
        NotificationSystem.show({
          type: "warning",
          title: "Campo requerido",
          message: "El título es obligatorio"
        });
        return;
      }

      const file = fileInput.files[0];
      const recintoId = this.recintoId;

      if (!recintoId) {
        NotificationSystem.show({
          type: "error",
          title: "Error",
          message: "No hay recinto seleccionado"
        });
        return;
      }

      const btnSubir = form.querySelector('button[type="submit"]');
      this.animarSubida(btnSubir, true);

      const formData = new FormData();
      formData.append('imagen', file);
      formData.append('titulo', titulo);
      formData.append('descripcion', descripcion);
      formData.append('recinto_id', recintoId);

      if (this.ultimaUbicacion) {
        formData.append('lat', this.ultimaUbicacion.lat.toString());
        formData.append('lon', this.ultimaUbicacion.lon.toString());
      }

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
        this.resetearEstadoCompleto();
        this.animarSubida(btnSubir, false);
        
        NotificationSystem.show({
          type: "success",
          title: "¡Imagen subida!",
          message: `"${titulo}" añadida correctamente${nuevaImagen.tiene_ubicacion ? ' con GPS ✓' : ''}`
        });
        
      } catch (error) {
        console.error(error);
        this.animarSubida(btnSubir, false);
        NotificationSystem.show({
          type: "error",
          title: "Error al subir",
          message: error.message || "No se pudo subir la imagen"
        });
      }
    };
  }

  animarSubida(boton, activar) {
    if (!boton) return;

    if (activar) {
      boton.setAttribute('data-original-html', boton.innerHTML);
      boton.setAttribute('data-original-class', boton.className);
      boton.disabled = true;
      boton.style.position = 'relative';
      boton.style.overflow = 'hidden';
      
      const container = document.createElement('div');
      container.style.display = 'flex';
      container.style.alignItems = 'center';
      container.style.justifyContent = 'center';
      container.style.gap = '8px';
      
      const spinnerContainer = document.createElement('div');
      spinnerContainer.style.display = 'flex';
      spinnerContainer.style.gap = '4px';
      
      for (let i = 0; i < 3; i++) {
        const dot = document.createElement('div');
        dot.style.width = '8px';
        dot.style.height = '8px';
        dot.style.backgroundColor = 'currentColor';
        dot.style.borderRadius = '50%';
        dot.style.animation = `bounce 0.6s ease-in-out ${i * 0.15}s infinite`;
        spinnerContainer.appendChild(dot);
      }
      
      const texto = document.createElement('span');
      texto.textContent = 'Subiendo imagen';
      texto.style.fontWeight = '500';
      
      let puntosCount = 0;
      const puntosInterval = setInterval(() => {
        puntosCount = (puntosCount + 1) % 4;
        texto.textContent = 'Subiendo imagen' + '.'.repeat(puntosCount);
      }, 400);
      
      boton.setAttribute('data-puntos-interval', puntosInterval);
      
      container.appendChild(spinnerContainer);
      container.appendChild(texto);
      
      boton.innerHTML = '';
      boton.appendChild(container);
      
      const wave = document.createElement('div');
      wave.style.position = 'absolute';
      wave.style.top = '0';
      wave.style.left = '0';
      wave.style.width = '0%';
      wave.style.height = '100%';
      wave.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
      wave.style.transition = 'width 0.3s ease-out';
      wave.style.zIndex = '0';
      boton.appendChild(wave);
      
      container.style.position = 'relative';
      container.style.zIndex = '1';
      
      let waveWidth = 0;
      let waveDirection = 1;
      const waveInterval = setInterval(() => {
        waveWidth += waveDirection * 10;
        if (waveWidth >= 100) {
          waveWidth = 100;
          waveDirection = -1;
        } else if (waveWidth <= 0) {
          waveWidth = 0;
          waveDirection = 1;
        }
        wave.style.width = waveWidth + '%';
      }, 50);
      
      boton.setAttribute('data-wave-interval', waveInterval);
      
      if (!document.getElementById('bounce-animation-style')) {
        const style = document.createElement('style');
        style.id = 'bounce-animation-style';
        style.textContent = `
          @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-10px); }
          }
        `;
        document.head.appendChild(style);
      }
      
    } else {
      const puntosInterval = boton.getAttribute('data-puntos-interval');
      const waveInterval = boton.getAttribute('data-wave-interval');
      
      if (puntosInterval) clearInterval(parseInt(puntosInterval));
      if (waveInterval) clearInterval(parseInt(waveInterval));
      
      const originalClass = boton.getAttribute('data-original-class');
      const originalHtml = boton.getAttribute('data-original-html');
      
      if (originalClass) boton.className = originalClass;
      
      boton.innerHTML = '<span style="font-size: 20px;">✓</span> ¡Listo!';
      boton.style.backgroundColor = '#28a745';
      boton.style.borderColor = '#28a745';
      boton.style.color = 'white';
      
      setTimeout(() => {
        boton.disabled = false;
        boton.style.position = '';
        boton.style.overflow = '';
        boton.style.backgroundColor = '';
        boton.style.borderColor = '';
        boton.style.color = '';
        
        if (originalHtml) {
          boton.innerHTML = originalHtml;
        }
      }, 800);
    }
  }
}

window.galeria = null;
document.addEventListener('DOMContentLoaded', () => {
  window.galeria = new GaleriaImagenes('galeria-grid');
});