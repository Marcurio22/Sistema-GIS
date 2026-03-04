class GaleriaImagenes {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.imagenes = [];
    this.maxVisibles = 5;
    this.mostrandoTodas = false;
    this.recintoId = null;
    this.ultimaUbicacion = null;
    this.gpsYaSolicitado = false;
    this.gpsPromesa = null; // ← guardamos la promesa en curso
    this.archivoSeleccionado = false;
    this._modalListenersConfigured = false;
    this._puntosInterval = null; // ← intervals en this, no en data-*
    this._waveInterval = null;
    this.init();
  }

  init() {
    this.initSubida();
    this.initEdicion();
    this.setupCameraOption();
    this.setupModalListeners();
    this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver sus imágenes</p>';
  }

  setupModalListeners() {
    const modalSubida = document.getElementById('modalSubida');
    if (!modalSubida || this._modalListenersConfigured) return;

    // ✅ Solo resetear al cerrar, GPS se pide únicamente en "Tomar Foto"
    modalSubida.addEventListener('hidden.bs.modal', () => {
      this.resetearEstadoCompleto();
    });

    this._modalListenersConfigured = true;
  }

  resetearEstadoCompleto() {
    this.ultimaUbicacion = null;
    this.gpsYaSolicitado = false;
    this.gpsPromesa = null;
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
    if (fileInput) fileInput.value = '';
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

        // Sin GPS, solo abrir galería
      document.getElementById('btn-elegir-archivo').addEventListener('click', () => {
        fileInput.removeAttribute('capture');
        fileInput.click();
      });

      // ✅ Primero GPS, luego cámara
      document.getElementById('btn-tomar-foto').addEventListener('click', async () => {
        fileInput.setAttribute('capture', 'environment');
        await this.solicitarPermisoUbicacion(); // ← espera respuesta (acepta o deniega)
        fileInput.click();                      // ← luego abre la cámara
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
      // Escritorio: GPS al cambiar archivo
      fileInput.addEventListener('change', (e) => {
        this.archivoSeleccionado = e.target.files.length > 0;
      });
    }
  }

  solicitarPermisoUbicacion() {
    // Si ya hay una promesa en curso, devolver la misma
    if (this.gpsPromesa) return this.gpsPromesa;
    // Si ya tenemos ubicación, no volver a pedir
    if (this.gpsYaSolicitado) return Promise.resolve(this.ultimaUbicacion);
    // Si no hay geolocation disponible
    if (!navigator.geolocation) {
      this.gpsYaSolicitado = true;
      return Promise.resolve(null);
    }

    this.gpsYaSolicitado = true;

    const gpsStatus = document.getElementById('gps-status');
    if (gpsStatus) {
      gpsStatus.classList.remove('d-none', 'text-success', 'text-warning');
      gpsStatus.classList.add('text-info');
      gpsStatus.innerHTML = '<i class="bi bi-geo-alt"></i> Obteniendo ubicación...';
    }

    this.gpsPromesa = new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          this.ultimaUbicacion = {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            accuracy: pos.coords.accuracy,
            timestamp: Date.now()
          };
          this.gpsPromesa = null;

          if (gpsStatus) {
            gpsStatus.classList.remove('d-none', 'text-warning', 'text-info');
            gpsStatus.classList.add('text-success');
            gpsStatus.innerHTML = `<i class="bi bi-geo-alt-fill"></i> GPS ✓ (±${Math.round(pos.coords.accuracy)}m)`;
          }

          resolve(this.ultimaUbicacion);
        },
        (error) => {
          this.ultimaUbicacion = null;
          this.gpsPromesa = null;

          if (gpsStatus) {
            gpsStatus.classList.remove('d-none', 'text-success', 'text-info');
            gpsStatus.classList.add('text-warning');
            const msgs = { 1: 'Permiso GPS denegado', 2: 'GPS no disponible', 3: 'Timeout GPS' };
            gpsStatus.innerHTML = `<i class="bi bi-geo-alt"></i> ${msgs[error.code] || 'Error GPS'}`;
          }

          resolve(null);
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 120000 }
      );
    });

    return this.gpsPromesa;
  }

  isMobile() {
    const isMobileDevice = /android|webos|iphone|ipod|blackberry|iemobile|opera mini/i.test(navigator.userAgent.toLowerCase());
    const isSmallScreen = window.innerWidth <= 576;
    return isMobileDevice && isSmallScreen;
  }

  extraerCoordenadas(geom) {
    if (!geom) return null;
    const match = geom.match(/POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)/i);
    if (match) return { lon: parseFloat(match[1]), lat: parseFloat(match[2]) };
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
      if (window.lightboxManager) window.lightboxManager.updateImages([], null);
      return;
    }

    try {
      // ✅ NO limpiamos el contenedor aquí → las imágenes viejas se quedan
      // visibles mientras carga, sin parpadeo negro
      const response = await fetch(`/api/galeria/listar/${this.recintoId}`);
      if (!response.ok) throw new Error('Error al cargar imágenes');

      this.imagenes = await response.json();

      if (window.lightboxManager) {
        window.lightboxManager.updateImages(this.imagenes, this.recintoId);
      }

      this.renderizarGaleria();

    } catch (error) {
      console.error(error);
      this.container.innerHTML = '<p class="text-danger">Error cargando imágenes</p>';
      if (window.lightboxManager) window.lightboxManager.updateImages([], null);
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

    imagenesAMostrar.forEach((imagen) => {
      const item = document.createElement('div');
      item.className = 'galeria-item';

      const coords = this.extraerCoordenadas(imagen.geom);
      const coordsHTML = coords
        ? `<small class="d-block mt-1" style="color:#17a2b8;font-weight:500;">${this.formatearCoordenadas(coords)}</small>`
        : '';

      item.innerHTML = `
        <img src="${imagen.thumb}" alt="${imagen.titulo}" loading="lazy" width="200" height="150">
        <div class="galeria-overlay">
          <h4>${imagen.titulo}</h4>
          <p>${imagen.descripcion || ''}</p>
          ${coordsHTML}
        </div>
        <div class="galeria-actions">
          <button class="galeria-action-btn edit" data-id="${imagen.id}" title="Editar">
            <i class="bi bi-pencil-fill"></i>
          </button>
          <button class="galeria-action-btn delete" data-id="${imagen.id}" title="Eliminar">
            <i class="bi bi-trash-fill"></i>
          </button>
        </div>
      `;

      const imgEl = item.querySelector('img');
      const overlayEl = item.querySelector('.galeria-overlay');

      // Doble rAF: espera a que Chrome haya pintado la imagen antes de hacer el fade.
      // Sin esto, Android Chrome crea la capa GPU con la imagen negra y luego la pinta.
      imgEl.onload = () => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            imgEl.classList.add('loaded');
          });
        });
      };
      // Si la imagen ya estaba en caché y onload no dispara
      if (imgEl.complete && imgEl.naturalWidth > 0) {
        requestAnimationFrame(() => requestAnimationFrame(() => imgEl.classList.add('loaded')));
      }

      const indiceReal = this.imagenes.findIndex(img => img.id === imagen.id);

      const abrirLightbox = () => {
        if (window.lightboxManager) {
          window.lightboxManager.updateImages(this.imagenes, this.recintoId);
          window.lightboxManager.open(indiceReal);
        }
      };

      imgEl.onclick = abrirLightbox;
      overlayEl.onclick = abrirLightbox;

      item.querySelector('.edit').onclick = (e) => {
        e.stopPropagation();
        this.abrirModalEditar(imagen);
      };
      item.querySelector('.delete').onclick = (e) => {
        e.stopPropagation();
        this.confirmarEliminar(imagen);
      };

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

    // ✅ Swap atómico: reemplazamos el contenido de golpe
    this.container.innerHTML = '';
    this.container.appendChild(fragment);
  }

  expandirGaleria() {
    if (typeof window.openGaleriaPanel === 'function') window.openGaleriaPanel();
    this.mostrandoTodas = true;
    this.renderizarGaleria();
    const overlay = document.getElementById('galeria-panel');
    if (overlay) overlay.scrollTop = 0;
  }

  contraerGaleria() {
    this.mostrandoTodas = false;
    this.renderizarGaleria();
    if (typeof window.closeGaleriaPanel === 'function') window.closeGaleriaPanel();
    const galeriaContainer = document.getElementById('galeria-imagenes');
    if (galeriaContainer) galeriaContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
      const res = await fetch(`/api/galeria/eliminar/${imagen.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Error al eliminar la imagen');

      await this.cargarImagenes();
      NotificationSystem.show({ type: 'success', title: 'Imagen eliminada', message: `"${imagen.titulo}" ha sido eliminada correctamente` });

    } catch (error) {
      console.error(error);
      NotificationSystem.show({ type: 'error', title: 'Error', message: 'No se pudo eliminar la imagen. Intenta de nuevo.' });
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
        NotificationSystem.show({ type: 'warning', title: 'Campo requerido', message: 'El título es obligatorio' });
        return;
      }

      try {
        const res = await fetch(`/api/galeria/editar/${imagenId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ titulo, descripcion })
        });

        if (!res.ok) throw new Error('Error al actualizar la imagen');

        await this.cargarImagenes();

        const modalEl = document.getElementById('modalEditar');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();

        NotificationSystem.show({ type: 'success', title: 'Imagen actualizada', message: `"${titulo}" ha sido actualizada correctamente` });

      } catch (error) {
        console.error(error);
        NotificationSystem.show({ type: 'error', title: 'Error', message: 'No se pudo actualizar la imagen. Intenta de nuevo.' });
      }
    };
  }

  abrirModalEditar(imagen) {
    document.getElementById('editar-imagen-id').value = imagen.id;
    document.getElementById('editar-titulo').value = imagen.titulo;
    document.getElementById('editar-descripcion').value = imagen.descripcion || '';
    document.getElementById('editar-preview').src = imagen.thumb;

    const modal = new bootstrap.Modal(document.getElementById('modalEditar'));
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
        NotificationSystem.show({ type: 'warning', title: 'Imagen requerida', message: 'Selecciona una imagen para subir' });
        return;
      }

      if (!titulo) {
        NotificationSystem.show({ type: 'warning', title: 'Campo requerido', message: 'El título es obligatorio' });
        return;
      }

      if (!this.recintoId) {
        NotificationSystem.show({ type: 'error', title: 'Error', message: 'No hay recinto seleccionado' });
        return;
      }

      const btnSubir = form.querySelector('button[type="submit"]');
      this.animarSubida(btnSubir, true);

      // ✅ Si el GPS aún está en curso, esperamos máximo 3s antes de enviar
      if (this.gpsPromesa) {
        await Promise.race([
          this.gpsPromesa,
          new Promise(resolve => setTimeout(resolve, 3000))
        ]);
      }

      const formData = new FormData();
      formData.append('imagen', fileInput.files[0]);
      formData.append('titulo', titulo);
      formData.append('descripcion', descripcion);
      formData.append('recinto_id', this.recintoId);

      if (this.ultimaUbicacion) {
        formData.append('lat', this.ultimaUbicacion.lat.toString());
        formData.append('lon', this.ultimaUbicacion.lon.toString());
      }

      try {
        const res = await fetch('/api/galeria/subir', { method: 'POST', body: formData });

        if (!res.ok) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.error || 'Error al subir la imagen');
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
          type: 'success',
          title: '¡Imagen subida!',
          message: `"${titulo}" añadida correctamente${nuevaImagen.tiene_ubicacion ? ' con GPS ✓' : ''}`
        });

      } catch (error) {
        console.error(error);
        this.animarSubida(btnSubir, false);
        NotificationSystem.show({ type: 'error', title: 'Error al subir', message: error.message || 'No se pudo subir la imagen' });
      }
    };
  }

  animarSubida(boton, activar) {
    if (!boton) return;

    if (activar) {
      boton.setAttribute('data-original-html', boton.innerHTML);
      boton.setAttribute('data-original-class', boton.className);
      boton.style.minHeight = boton.offsetHeight + 'px';
      boton.disabled = true;
      boton.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Subiendo imagen...
      `;

    } else {
      boton.style.minHeight = '';

      const originalClass = boton.getAttribute('data-original-class');
      const originalHtml  = boton.getAttribute('data-original-html');

      if (originalClass) boton.className = originalClass;
      boton.innerHTML = '<span style="font-size:20px;">✓</span> ¡Listo!';
      boton.style.cssText += 'background-color:#28a745;border-color:#28a745;color:white;';

      setTimeout(() => {
        boton.disabled = false;
        boton.style.backgroundColor = '';
        boton.style.borderColor = '';
        boton.style.color = '';
        boton.style.minHeight = '';
        if (originalHtml) boton.innerHTML = originalHtml;
      }, 800);
    }
  }
}

window.galeria = null;
document.addEventListener('DOMContentLoaded', () => {
  window.galeria = new GaleriaImagenes('galeria-grid');
});