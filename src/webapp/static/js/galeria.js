class GaleriaImagenes {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.imagenes = [];
    this.maxVisibles = 5;
    this.mostrandoTodas = false;
    this.recintoId = null;
    this.ultimaUbicacion = null; // Guardar última ubicación capturada
    this.init();
  }

  init() {
    this.initSubida();
    this.initEdicion();
    this.setupCameraOption(); // Nueva función para manejar la opción de cámara
    this.setupModalListeners(); // Listener para resetear GPS al cerrar modal
    this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver sus imágenes</p>';
  }

  // Configurar listeners para el modal de subida
  setupModalListeners() {
    const modalSubida = document.getElementById('modalSubida');
    if (modalSubida) {
      modalSubida.addEventListener('hidden.bs.modal', () => {
        console.log('🔄 Modal cerrado - reseteando GPS');
        this.ultimaUbicacion = null;
        
        // Resetear indicador GPS
        const gpsStatus = document.getElementById('gps-status');
        if (gpsStatus) {
          gpsStatus.classList.add('d-none');
          gpsStatus.classList.remove('text-success', 'text-warning');
        }
      });
    }
  }

  // Nueva función para detectar móvil y añadir botones de opción
  setupCameraOption() {
    const fileInput = document.getElementById('imagen-file');
    const modalBody = fileInput.closest('.modal-body');
    
    // Solo en dispositivos móviles
    if (this.isMobile()) {
      // Ocultar el input file original
      fileInput.style.display = 'none';
      
      // Crear contenedor de botones
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
        <small class="text-success d-none" id="gps-status"><i class="bi bi-geo-alt-fill"></i> GPS activado</small>
      `;
      
      // Insertar antes del input file original
      fileInput.parentNode.insertBefore(btnContainer, fileInput);
      
      // Eventos de los botones SIN solicitud de GPS (se pedirá al subir)
      document.getElementById('btn-elegir-archivo').addEventListener('click', () => {
        fileInput.removeAttribute('capture');
        fileInput.click();
      });
      
      document.getElementById('btn-tomar-foto').addEventListener('click', () => {
        fileInput.setAttribute('capture', 'environment');
        fileInput.click();
      });
      
      // Mostrar nombre del archivo seleccionado Y PEDIR GPS
      fileInput.addEventListener('change', async (e) => {
        const archivoSeleccionado = document.getElementById('archivo-seleccionado');
        if (e.target.files.length > 0) {
          archivoSeleccionado.textContent = `📷 ${e.target.files[0].name}`;
          archivoSeleccionado.style.color = '#198754';
          archivoSeleccionado.style.fontWeight = '600';
          
          // 🔥 PEDIR GPS JUSTO DESPUÉS DE SELECCIONAR/TOMAR FOTO
          console.log('📸 Archivo seleccionado, solicitando GPS...');
          await this.solicitarPermisoUbicacion();
        } else {
          archivoSeleccionado.textContent = 'Ningún archivo seleccionado';
          archivoSeleccionado.style.color = '';
          archivoSeleccionado.style.fontWeight = '';
        }
      });
    } else {
      // Para dispositivos de escritorio, también pedir GPS al seleccionar archivo
      fileInput.addEventListener('change', async (e) => {
        if (e.target.files.length > 0) {
          console.log('📸 Archivo seleccionado (escritorio), solicitando GPS...');
          await this.solicitarPermisoUbicacion();
        }
      });
    }
  }

  // ✅ FUNCIÓN: Solicitar permiso de ubicación GPS
  async solicitarPermisoUbicacion() {
    if (!navigator.geolocation) {
      console.warn('⚠️ Geolocalización no disponible en este navegador');
      return null;
    }

    const gpsStatus = document.getElementById('gps-status');
    

    
    try {
      const position = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
          pos => {
            resolve(pos);
          },
          error => {
            reject(error);
          },
          {
            enableHighAccuracy: true,
            timeout: 15000, // 15 segundos de timeout
            maximumAge: 0   // No usar caché
          }
        );
      });

      // ✅ ÉXITO - GPS capturado
      console.log('✅ GPS capturado exitosamente:', position.coords.latitude, position.coords.longitude);
      
      // Guardar ubicación en la instancia
      this.ultimaUbicacion = {
        lat: position.coords.latitude,
        lon: position.coords.longitude,
        timestamp: Date.now()
      };
      
      // Actualizar UI de éxito
      if (gpsStatus) {
        gpsStatus.classList.remove('d-none', 'text-warning', 'text-info');
        gpsStatus.classList.add('text-success');
        gpsStatus.innerHTML = '<i class="bi bi-geo-alt-fill"></i> Ubicación capturada ✓';
      }
      
      return position;

    } catch (error) {
     
      
      this.ultimaUbicacion = null;
      
      
      // Solo mostrar notificación si el usuario denegó explícitamente
      if (error.code === 1) { // PERMISSION_DENIED
        console.log('🚫 Usuario denegó el permiso de ubicación');
        // NO mostrar notificación aquí, solo en consola
      } else if (error.code === 2) { // POSITION_UNAVAILABLE
        console.log('📍 Ubicación no disponible (GPS desactivado o sin señal)');
      } else if (error.code === 3) { // TIMEOUT
        console.log('⏱️ Timeout al obtener ubicación');
      }
      
      return null;
    }
  }


  // Detectar si es móvil
  isMobile() {
    // Detectar solo dispositivos móviles reales, no tablets ni PCs
    const userAgent = navigator.userAgent.toLowerCase();
    const isMobileDevice = /android|webos|iphone|ipod|blackberry|iemobile|opera mini/i.test(userAgent);
    const isSmallScreen = window.innerWidth <= 576; // Cambio de 768 a 576
    
    return isMobileDevice && isSmallScreen;
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

      // ✅ INICIAR ANIMACIÓN DE SUBIDA
      const btnSubir = form.querySelector('button[type="submit"]');
      this.animarSubida(btnSubir, true);

      const formData = new FormData();
      formData.append('imagen', file);
      formData.append('titulo', titulo);
      formData.append('descripcion', descripcion);
      formData.append('recinto_id', recintoId);

      // ✅ USAR UBICACIÓN GPS GUARDADA
      if (this.ultimaUbicacion) {
        console.log('📍 Usando ubicación GPS guardada:', this.ultimaUbicacion);
        formData.append('lat', this.ultimaUbicacion.lat);
        formData.append('lon', this.ultimaUbicacion.lon);
      } else {
        console.warn('⚠️ No hay ubicación GPS disponible');
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
        
        // Resetear ubicación GPS guardada para que pida una nueva la próxima vez
        this.ultimaUbicacion = null;
        
        // Resetear el mensaje de archivo seleccionado si existe
        const archivoSeleccionado = document.getElementById('archivo-seleccionado');
        if (archivoSeleccionado) {
          archivoSeleccionado.textContent = 'Ningún archivo seleccionado';
          archivoSeleccionado.style.color = '';
          archivoSeleccionado.style.fontWeight = '';
        }
        
        // Resetear indicador GPS
        const gpsStatus = document.getElementById('gps-status');
        if (gpsStatus) {
          gpsStatus.classList.add('d-none');
          gpsStatus.classList.remove('text-success', 'text-warning');
        }
        
        // ✅ DETENER ANIMACIÓN
        this.animarSubida(btnSubir, false);
        
        NotificationSystem.show({
          type: "success",
          title: "¡Imagen subida!",
          message: `"${titulo}" se ha añadido correctamente a la galería`
        });
        
      } catch (error) {
        console.error(error);
        
        // ✅ DETENER ANIMACIÓN EN CASO DE ERROR
        this.animarSubida(btnSubir, false);
        
        // Resetear ubicación GPS en caso de error
        this.ultimaUbicacion = null;
        
        NotificationSystem.show({
          type: "error",
          title: "Error al subir",
          message: error.message || "No se pudo subir la imagen. Intenta de nuevo."
        });
      }
    };
  }

  // ✅ FUNCIÓN DE ANIMACIÓN MEJORADA Y MÁS BONITA
  animarSubida(boton, activar) {
    if (!boton) return;

    if (activar) {
      // Guardar contenido original
      boton.setAttribute('data-original-html', boton.innerHTML);
      boton.setAttribute('data-original-class', boton.className);
      boton.disabled = true;
      
      // Cambiar estilo del botón
      boton.style.position = 'relative';
      boton.style.overflow = 'hidden';
      
      // Crear contenedor de la animación
      const container = document.createElement('div');
      container.style.display = 'flex';
      container.style.alignItems = 'center';
      container.style.justifyContent = 'center';
      container.style.gap = '8px';
      
      // Crear spinner con puntos animados
      const spinnerContainer = document.createElement('div');
      spinnerContainer.style.display = 'flex';
      spinnerContainer.style.gap = '4px';
      
      // Crear 3 puntos que se animan
      for (let i = 0; i < 3; i++) {
        const dot = document.createElement('div');
        dot.style.width = '8px';
        dot.style.height = '8px';
        dot.style.backgroundColor = 'currentColor';
        dot.style.borderRadius = '50%';
        dot.style.animation = `bounce 0.6s ease-in-out ${i * 0.15}s infinite`;
        spinnerContainer.appendChild(dot);
      }
      
      // Crear texto
      const texto = document.createElement('span');
      texto.textContent = 'Subiendo imagen';
      texto.style.fontWeight = '500';
      
      // Añadir puntos animados al texto
      let puntosCount = 0;
      const puntosInterval = setInterval(() => {
        puntosCount = (puntosCount + 1) % 4;
        texto.textContent = 'Subiendo imagen' + '.'.repeat(puntosCount);
      }, 400);
      
      boton.setAttribute('data-puntos-interval', puntosInterval);
      
      container.appendChild(spinnerContainer);
      container.appendChild(texto);
      
      // Actualizar botón
      boton.innerHTML = '';
      boton.appendChild(container);
      
      // Añadir animación de onda de fondo
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
      
      // Animar la onda
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
      
      // Añadir estilos de animación bounce si no existen
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
      // Detener todas las animaciones
      const puntosInterval = boton.getAttribute('data-puntos-interval');
      const waveInterval = boton.getAttribute('data-wave-interval');
      
      if (puntosInterval) clearInterval(parseInt(puntosInterval));
      if (waveInterval) clearInterval(parseInt(waveInterval));
      
      // Restaurar botón con animación de éxito
      const originalClass = boton.getAttribute('data-original-class');
      const originalHtml = boton.getAttribute('data-original-html');
      
      if (originalClass) boton.className = originalClass;
      
      // Mostrar checkmark brevemente antes de restaurar
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