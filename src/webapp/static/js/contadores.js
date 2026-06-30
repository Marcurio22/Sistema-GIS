class ContadoresManager {
  constructor() {
    this.recintoId = null;
    this.ultimaUbicacion = null;
    this.gpsYaSolicitado = false;
    this.gpsPromesa = null;
    this.archivoSeleccionado = false;
    this._modalListenersConfigured = false;
    this.init();
  }

  init() {
    this.setupCameraOption();
    this.setupModalListeners();
    this.initSubida();
  }

  setRecintoId(recintoId) {
    this.recintoId = recintoId;
  }

  // ── Modal reset al cerrar ──────────────────────────────────────────
  setupModalListeners() {
    const modal = document.getElementById('modalContador');
    if (!modal || this._modalListenersConfigured) return;
    modal.addEventListener('hidden.bs.modal', () => this.resetearEstadoCompleto());
    this._modalListenersConfigured = true;
  }

  resetearEstadoCompleto() {
    this.ultimaUbicacion = null;
    this.gpsYaSolicitado = false;
    this.gpsPromesa = null;
    this.archivoSeleccionado = false;

    const gpsEl = document.getElementById('contador-gps-status');
    if (gpsEl) {
      gpsEl.classList.add('d-none');
      gpsEl.classList.remove('text-success', 'text-warning', 'text-info');
      gpsEl.innerHTML = '';
    }

    const archivoEl = document.getElementById('contador-archivo-seleccionado');
    if (archivoEl) {
      archivoEl.textContent = 'Ningún archivo seleccionado';
      archivoEl.style.color = '';
      archivoEl.style.fontWeight = '';
    }

    const fileInput = document.getElementById('contador-file');
    if (fileInput) fileInput.value = '';

    const form = document.getElementById('form-contador');
    if (form) form.reset();
  }

  // ── Detección móvil (igual que GaleriaImagenes) ───────────────────
  isMobile() {
    const ua = /android|webos|iphone|ipod|blackberry|iemobile|opera mini/i.test(navigator.userAgent.toLowerCase());
    return ua && window.innerWidth <= 576;
  }

  // ── Botones cámara / galería en móvil ─────────────────────────────
  setupCameraOption() {
    const fileInput = document.getElementById('contador-file');
    if (!fileInput) return;

    if (this.isMobile()) {
      fileInput.style.display = 'none';

      const wrap = document.createElement('div');
      wrap.className = 'mb-3';
      wrap.innerHTML = `
        <label class="form-label">Foto del contador</label>
        <div class="d-grid gap-2">
          <button type="button" class="btn btn-outline-success" id="btn-contador-tomar-foto">
            <i class="bi bi-camera-fill me-2"></i>Tomar Foto
          </button>
        </div>
        <small class="text-muted d-block mt-2" id="contador-archivo-seleccionado">Ningún archivo seleccionado</small>
        <small class="d-none mt-1 d-block" id="contador-gps-status"></small>
      `;
      fileInput.parentNode.insertBefore(wrap, fileInput);

      // GPS primero, cámara trasera después
      document.getElementById('btn-contador-tomar-foto').addEventListener('click', async () => {
        fileInput.setAttribute('capture', 'environment');
        await this.solicitarPermisoUbicacion();
        fileInput.click();
      });

      fileInput.addEventListener('change', (e) => this._onArchivoChange(e));

    } else {
      // Escritorio: pedir GPS al elegir archivo
      fileInput.insertAdjacentHTML('afterend',
        '<small class="d-none mt-1 d-block" id="contador-gps-status"></small>'
      );
      fileInput.addEventListener('change', async (e) => {
        if (e.target.files.length > 0 && !this.gpsYaSolicitado) {
          await this.solicitarPermisoUbicacion();
        }
        this._onArchivoChange(e);
      });
    }
  }

  _onArchivoChange(e) {
    const archivoEl = document.getElementById('contador-archivo-seleccionado');
    if (e.target.files.length > 0) {
      this.archivoSeleccionado = true;
      if (archivoEl) {
        archivoEl.textContent = `📷 ${e.target.files[0].name}`;
        archivoEl.style.color = '#90bc05';
        archivoEl.style.fontWeight = '600';
      }
    } else {
      this.archivoSeleccionado = false;
      if (archivoEl) {
        archivoEl.textContent = 'Ningún archivo seleccionado';
        archivoEl.style.color = '';
        archivoEl.style.fontWeight = '';
      }
    }
  }

  // ── GPS (mismo patrón que GaleriaImagenes) ────────────────────────
  solicitarPermisoUbicacion() {
    if (this.gpsPromesa) return this.gpsPromesa;
    if (this.gpsYaSolicitado && this.ultimaUbicacion) return Promise.resolve(this.ultimaUbicacion);

    if (!navigator.geolocation) {
      this.gpsYaSolicitado = true;
      this._setGpsStatus('warning', '<i class="bi bi-geo-alt"></i> GPS no disponible en este dispositivo');
      return Promise.resolve(null);
    }

    this.gpsYaSolicitado = true;
    this._setGpsStatus('info', '<i class="bi bi-geo-alt"></i> Obteniendo ubicación...');

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
          this._setGpsStatus('success', `<i class="bi bi-geo-alt-fill"></i> GPS ✓ (±${Math.round(pos.coords.accuracy)}m)`);
          resolve(this.ultimaUbicacion);
        },
        (error) => {
          this.ultimaUbicacion = null;
          this.gpsPromesa = null;
          const msgs = { 1: 'Permiso GPS denegado', 2: 'GPS no disponible', 3: 'Timeout GPS' };
          this._setGpsStatus('warning', `<i class="bi bi-geo-alt"></i> ${msgs[error.code] || 'Error GPS'}`);
          resolve(null);
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 120000 }
      );
    });

    return this.gpsPromesa;
  }

  _setGpsStatus(tipo, html) {
    const el = document.getElementById('contador-gps-status');
    if (!el) return;
    el.classList.remove('d-none', 'text-success', 'text-warning', 'text-info');
    el.classList.add(`text-${tipo}`);
    el.innerHTML = html;
  }

  // ── Envío del formulario ──────────────────────────────────────────
  initSubida() {
    const form = document.getElementById('form-contador');
    if (!form) return;

    form.onsubmit = async (e) => {
      e.preventDefault();

      const fileInput   = document.getElementById('contador-file');
      const titulo      = document.getElementById('contador-titulo').value.trim();
      const lectura     = document.getElementById('contador-lectura').value.trim();
      const descripcion = document.getElementById('contador-descripcion').value.trim();

      if (!fileInput?.files.length) {
        NotificationSystem.show({ type: 'warning', title: 'Foto requerida', message: 'Haz una foto del contador para continuar' });
        return;
      }
      if (!titulo) {
        NotificationSystem.show({ type: 'warning', title: 'Campo requerido', message: 'El título es obligatorio' });
        return;
      }
      if (!this.recintoId) {
        NotificationSystem.show({ type: 'error', title: 'Sin recinto', message: 'Selecciona un recinto antes de añadir un contador' });
        return;
      }

      // Esperar GPS si sigue en curso
      if (this.gpsPromesa) {
        await Promise.race([this.gpsPromesa, new Promise(r => setTimeout(r, 5000))]);
      }

      // GPS obligatorio: si no hay ubicación, intentarlo una vez más
      if (!this.ultimaUbicacion) {
        this.gpsYaSolicitado = false; // permitir reintento
        await this.solicitarPermisoUbicacion();
      }

    if (!this.ultimaUbicacion && !this.gpsYaSolicitado) {
        await this.solicitarPermisoUbicacion();
        }

      const btnGuardar = form.querySelector('button[type="submit"]');
      this._animarSubida(btnGuardar, true);

      const formData = new FormData();
      formData.append('imagen',       fileInput.files[0]);
      formData.append('titulo',       titulo);
      formData.append('lectura',      lectura);
      formData.append('descripcion',  descripcion);
      formData.append('recinto_id',   this.recintoId);
      
      if (this.ultimaUbicacion) {
        formData.append('lat', this.ultimaUbicacion.lat.toString());
        formData.append('lon', this.ultimaUbicacion.lon.toString());
        }

      try {
        const res = await fetch('/api/contadores/subir', { method: 'POST', body: formData });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || 'Error al subir la lectura');
        }

        const datos = await res.json();

        const modalEl = document.getElementById('modalContador');
        bootstrap.Modal.getInstance(modalEl)?.hide();

        this._animarSubida(btnGuardar, false);
        NotificationSystem.show({
          type: 'success',
          title: '¡Lectura guardada!',
          message: `"${titulo}" guardada con GPS ✓`
        });

      } catch (error) {
        console.error(error);
        this._animarSubida(btnGuardar, false);
        NotificationSystem.show({ type: 'error', title: 'Error al subir', message: error.message });
      }
    };
  }

  // ── Animación del botón (igual que GaleriaImagenes.animarSubida) ──
  _animarSubida(boton, activar) {
    if (!boton) return;
    if (activar) {
      boton.setAttribute('data-original-html', boton.innerHTML);
      boton.setAttribute('data-original-class', boton.className);
      boton.style.minHeight = boton.offsetHeight + 'px';
      boton.disabled = true;
      boton.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Guardando lectura...
      `;
    } else {
      boton.style.minHeight = '';
      const oc = boton.getAttribute('data-original-class');
      const oh = boton.getAttribute('data-original-html');
      if (oc) boton.className = oc;
      boton.innerHTML = '<span style="font-size:20px;">✓</span> ¡Listo!';
      boton.style.cssText += 'background-color:#28a745;border-color:#28a745;color:white;';
      setTimeout(() => {
        boton.disabled = false;
        boton.style.backgroundColor = '';
        boton.style.borderColor    = '';
        boton.style.color          = '';
        boton.style.minHeight      = '';
        if (oh) boton.innerHTML = oh;
      }, 800);
    }
  }
}

window.contadoresManager = null;
document.addEventListener('DOMContentLoaded', () => {
  window.contadoresManager = new ContadoresManager();
});