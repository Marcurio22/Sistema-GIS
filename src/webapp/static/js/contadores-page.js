/**
 * Lecturas de contador desde la página /contadores (sin visor).
 * Detecta el recinto por GPS al tomar la foto.
 */
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('form-contador-page');
  if (!form) return;

  const fileInput = document.getElementById('contador-page-file');
  const recintoInfo = document.getElementById('contador-page-recinto');
  const gpsStatus = document.getElementById('contador-page-gps-status');
  const archivoEl = document.getElementById('contador-page-archivo');

  let ultimaUbicacion = null;
  let recintoDetectado = null;
  let gpsPromesa = null;

  function isMobile() {
    return /android|webos|iphone|ipod|blackberry|iemobile|opera mini/i.test(navigator.userAgent.toLowerCase())
      && window.innerWidth <= 768;
  }

  function setGpsStatus(tipo, html) {
    if (!gpsStatus) return;
    gpsStatus.classList.remove('d-none', 'text-success', 'text-warning', 'text-info', 'text-danger');
    gpsStatus.classList.add(`text-${tipo}`);
    gpsStatus.innerHTML = html;
  }

  function showModalAlert(tipo, html) {
    const box = document.getElementById('contador-page-modal-alert');
    if (!box) {
      window.mostrarFlashContador?.(tipo, html);
      return;
    }
    box.className = `alert alert-${tipo} small mb-3`;
    box.innerHTML = html;
    box.classList.remove('d-none');
  }

  function clearModalAlert() {
    const box = document.getElementById('contador-page-modal-alert');
    if (box) {
      box.classList.add('d-none');
      box.innerHTML = '';
    }
  }

  function setRecintoInfo(html, ok) {
    if (!recintoInfo) return;
    recintoInfo.classList.remove('alert-success', 'alert-warning', 'alert-secondary');
    recintoInfo.classList.add(ok ? 'alert-success' : 'alert-warning');
    recintoInfo.innerHTML = html;
    recintoInfo.classList.remove('d-none');
  }

  function solicitarGps() {
    if (gpsPromesa) return gpsPromesa;
    if (!navigator.geolocation) {
      setGpsStatus('warning', '<i class="bi bi-geo-alt"></i> GPS no disponible');
      return Promise.resolve(null);
    }

    setGpsStatus('info', '<i class="bi bi-geo-alt"></i> Obteniendo ubicación...');

    gpsPromesa = new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          ultimaUbicacion = {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            accuracy: pos.coords.accuracy,
          };
          gpsPromesa = null;
          setGpsStatus('success', `<i class="bi bi-geo-alt-fill"></i> GPS ✓ (±${Math.round(pos.coords.accuracy)} m)`);
          resolve(ultimaUbicacion);
        },
        (err) => {
          ultimaUbicacion = null;
          gpsPromesa = null;
          const msgs = { 1: 'Permiso GPS denegado', 2: 'GPS no disponible', 3: 'Timeout GPS' };
          setGpsStatus('warning', `<i class="bi bi-geo-alt"></i> ${msgs[err.code] || 'Error GPS'}`);
          resolve(null);
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 60000 }
      );
    });

    return gpsPromesa;
  }

  async function resolverRecintoPorGps() {
    if (!ultimaUbicacion) return null;
    try {
      const url = `/api/contadores/recinto-por-gps?lat=${ultimaUbicacion.lat}&lon=${ultimaUbicacion.lon}`;
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || 'Error al buscar recinto');

      if (!data.found) {
        recintoDetectado = null;
        setRecintoInfo(
          '<i class="bi bi-exclamation-triangle me-1"></i>No estás dentro de ninguno de tus recintos. Acércate a la parcela e inténtalo de nuevo.',
          false
        );
        return null;
      }

      recintoDetectado = data.recinto;
      const nombre = recintoDetectado.nombre || 'Sin nombre';
      setRecintoInfo(
        `<i class="bi bi-geo-alt-fill me-1"></i>Recinto detectado: <strong>${nombre}</strong> (pol. ${recintoDetectado.poligono} / parc. ${recintoDetectado.parcela})`,
        true
      );
      return recintoDetectado;
    } catch (e) {
      recintoDetectado = null;
      setRecintoInfo(`<i class="bi bi-x-circle me-1"></i>${e.message}`, false);
      return null;
    }
  }

  function setupCameraUi() {
    if (!fileInput || !isMobile()) return;

    fileInput.classList.add('d-none');
    const wrap = document.createElement('div');
    wrap.className = 'mb-3';
    wrap.innerHTML = `
      <label class="form-label">Foto del contador</label>
      <button type="button" class="btn btn-outline-success w-100" id="btn-contador-page-foto">
        <i class="bi bi-camera-fill me-2"></i>Tomar foto
      </button>
    `;
    fileInput.parentNode.insertBefore(wrap, fileInput);
    document.getElementById('btn-contador-page-foto').addEventListener('click', async () => {
      fileInput.setAttribute('capture', 'environment');
      await solicitarGps();
      fileInput.click();
    });
  }

  async function onArchivoSeleccionado() {
    if (!fileInput?.files?.length) return;
    if (archivoEl) {
      archivoEl.textContent = `📷 ${fileInput.files[0].name}`;
      archivoEl.classList.add('text-success', 'fw-semibold');
    }
    if (!ultimaUbicacion) await solicitarGps();
    await resolverRecintoPorGps();
  }

  setupCameraUi();

  fileInput?.addEventListener('change', onArchivoSeleccionado);

  document.getElementById('modalContadorPage')?.addEventListener('show.bs.modal', async () => {
    recintoDetectado = null;
    ultimaUbicacion = null;
    gpsPromesa = null;
    recintoInfo?.classList.add('d-none');
    clearModalAlert();
    setGpsStatus('info', '<i class="bi bi-geo-alt"></i> Obteniendo ubicación...');
    await solicitarGps();
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const titulo = document.getElementById('contador-page-titulo')?.value.trim();
    const lectura = document.getElementById('contador-page-lectura')?.value.trim();
    const descripcion = document.getElementById('contador-page-descripcion')?.value.trim();

    if (!fileInput?.files?.length) {
      showModalAlert('warning', 'Haz una foto del contador para continuar.');
      return;
    }
    if (!titulo) {
      showModalAlert('warning', 'El título es obligatorio.');
      return;
    }

    if (gpsPromesa) await gpsPromesa;
    if (!ultimaUbicacion) await solicitarGps();
    if (!recintoDetectado) await resolverRecintoPorGps();
    if (!recintoDetectado?.id_recinto) {
      showModalAlert('danger', '<i class="bi bi-exclamation-triangle me-1"></i>No se pudo asignar un recinto. Comprueba el GPS y que estés dentro de tu parcela.');
      return;
    }

    const btn = form.querySelector('button[type="submit"]');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Guardando...';

    const formData = new FormData();
    formData.append('imagen', fileInput.files[0]);
    formData.append('titulo', titulo);
    formData.append('lectura', lectura);
    formData.append('descripcion', descripcion);
    formData.append('recinto_id', recintoDetectado.id_recinto);
    formData.append('lat', ultimaUbicacion.lat.toString());
    formData.append('lon', ultimaUbicacion.lon.toString());

    try {
      const res = await fetch('/api/contadores/subir', { method: 'POST', body: formData });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || 'Error al guardar');

      bootstrap.Modal.getInstance(document.getElementById('modalContadorPage'))?.hide();
      window.mostrarFlashContador?.('success', `<i class="bi bi-check-circle me-1"></i>Lectura guardada en <strong>${recintoDetectado.nombre || 'recinto'}</strong>.`);
      setTimeout(() => window.location.reload(), 1200);
    } catch (err) {
      showModalAlert('danger', err.message);
      btn.disabled = false;
      btn.innerHTML = original;
    }
  });
});
