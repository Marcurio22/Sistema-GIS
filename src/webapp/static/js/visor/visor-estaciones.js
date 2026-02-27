/**
 * visor-estaciones.js
 */

window.estacionesActivas = true;
window.estacionesLayer = null;

// ─── Helper responsive ────────────────────────────────────────────────────────
const isMobile = () => window.innerWidth < 600;

(function inyectarEstilos() {
  if (document.getElementById('estacion-styles')) return;
  const s = document.createElement('style');
  s.id = 'estacion-styles';
  s.textContent = `
    #estacion-cal {
      position: fixed;
      background: white;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.15);
      border: 1px solid #e9ecef;
      padding: 12px;
      z-index: 10001;
      width: 240px;
      user-select: none;
    }
    #estacion-cal .cal-header {
      display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;
    }
    #estacion-cal .cal-nav {
      background: none; border: none; cursor: pointer;
      width: 28px; height: 28px; border-radius: 6px;
      font-size: 1rem; color: #868e96;
      display: flex; align-items: center; justify-content: center;
      transition: background 0.15s;
    }
    #estacion-cal .cal-nav:hover { background: #f1f3f5; color: #212529; }
    #estacion-cal .cal-nav:disabled { opacity: 0.25; cursor: default; background: none; }
    #estacion-cal .cal-title-btn {
      background: none; border: none; cursor: pointer;
      font-size: 0.85rem; font-weight: 700; color: #212529;
      border-radius: 6px; padding: 3px 8px; transition: background 0.15s;
    }
    #estacion-cal .cal-title-btn:hover { background: #f1f3f5; color: #0d6efd; }
    #estacion-cal .cal-weekdays {
      display: grid; grid-template-columns: repeat(7, 1fr); margin-bottom: 4px;
    }
    #estacion-cal .cal-weekdays span {
      text-align: center; font-size: 0.65rem; font-weight: 700;
      color: #adb5bd; text-transform: uppercase; padding: 2px 0;
    }
    #estacion-cal .cal-days {
      display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px;
    }
    #estacion-cal .cal-day {
      aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
      border-radius: 6px; font-size: 0.78rem; cursor: pointer;
      color: #212529; transition: background 0.12s; border: none; background: none;
    }
    #estacion-cal .cal-day:hover:not(.disabled):not(.selected) { background: #e7f1ff; color: #0d6efd; }
    #estacion-cal .cal-day.selected { background: #0d6efd; color: white; font-weight: 700; }
    #estacion-cal .cal-day.disabled { color: #dee2e6; cursor: default; }
    #estacion-cal .cal-day.empty { cursor: default; }
    #estacion-cal .cal-grid-meses {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-top: 4px;
    }
    #estacion-cal .cal-mes {
      padding: 7px 4px; border-radius: 6px; border: none; background: none;
      font-size: 0.8rem; font-weight: 600; color: #212529; cursor: pointer;
      transition: background 0.12s; text-align: center;
    }
    #estacion-cal .cal-mes:hover:not(.disabled) { background: #e7f1ff; color: #0d6efd; }
    #estacion-cal .cal-mes.selected { background: #0d6efd; color: white; }
    #estacion-cal .cal-mes.disabled { color: #dee2e6; cursor: default; }
    #estacion-cal .cal-grid-anios {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-top: 4px;
    }
    #estacion-cal .cal-anio {
      padding: 7px 4px; border-radius: 6px; border: none; background: none;
      font-size: 0.8rem; font-weight: 600; color: #212529; cursor: pointer;
      transition: background 0.12s; text-align: center;
    }
    #estacion-cal .cal-anio:hover:not(.disabled) { background: #e7f1ff; color: #0d6efd; }
    #estacion-cal .cal-anio.selected { background: #0d6efd; color: white; }
    #estacion-cal .cal-anio.disabled { color: #dee2e6; cursor: default; }
    #estacion-display {
      flex: 1; padding: 4px 10px; border: 1px solid #dee2e6; border-radius: 6px;
      font-size: 0.82rem; cursor: pointer; background: white; color: #212529;
      display: flex; align-items: center; justify-content: space-between; gap: 6px;
    }
    #estacion-display:hover { border-color: #adb5bd; }
    #estacion-display .cal-icon { color: #adb5bd; font-size: 0.9rem; }
    #estacion-dia-prev:hover:not(:disabled),
    #estacion-dia-next:hover:not(:disabled) { background: #f1f3f5 !important; color: #212529 !important; }
    #estacion-dia-prev:disabled,
    #estacion-dia-next:disabled { opacity: 0.25; cursor: default; }
  `;
  document.head.appendChild(s);
})();

// ─── Calendario custom ────────────────────────────────────────────────────────
let calFechasSet = new Set();
let calFechaMin = '';
let calFechaMax = '';
let calFechaSeleccionada = '';
let calOnChange = null;
let calYear = 0;
let calMonth = 0;
let calVista = 'dias';
let calDecada = 0;

function mesesConDatosEnAnio(y) {
  const meses = new Set();
  for (const f of calFechasSet) {
    const [fy, fm] = f.split('-').map(Number);
    if (fy === y) meses.add(fm - 1);
  }
  return meses;
}
function aniosConDatos() {
  const anios = new Set();
  for (const f of calFechasSet) anios.add(parseInt(f.split('-')[0]));
  return anios;
}

function renderCal() {
  const cal = document.getElementById('estacion-cal');
  if (!cal) return;
  if (calVista === 'dias')  renderCalDias(cal);
  if (calVista === 'meses') renderCalMeses(cal);
  if (calVista === 'años')  renderCalAnios(cal);
}

function renderCalDias(cal) {
  const MESES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                 'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const DIAS  = ['L','M','X','J','V','S','D'];
  const hayAnterior = [...calFechasSet].some(f => {
    const [y, m] = f.split('-').map(Number);
    return y < calYear || (y === calYear && m < calMonth + 1);
  });
  const haySiguiente = [...calFechasSet].some(f => {
    const [y, m] = f.split('-').map(Number);
    return y > calYear || (y === calYear && m > calMonth + 1);
  });
  const primerDia = new Date(calYear, calMonth, 1).getDay();
  const diasMes   = new Date(calYear, calMonth + 1, 0).getDate();
  const offset    = (primerDia + 6) % 7;
  let celdas = '';
  for (let i = 0; i < offset; i++) celdas += `<div class="cal-day empty"></div>`;
  for (let d = 1; d <= diasMes; d++) {
    const fecha = `${calYear}-${String(calMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const activo = calFechasSet.has(fecha);
    const selec  = fecha === calFechaSeleccionada ? ' selected' : '';
    const dis    = activo ? '' : ' disabled';
    celdas += `<button class="cal-day${dis}${selec}" data-fecha="${fecha}">${d}</button>`;
  }
  cal.innerHTML = `
    <div class="cal-header">
      <button class="cal-nav" id="cal-prev" ${!hayAnterior ? 'disabled' : ''}>‹</button>
      <button class="cal-title-btn">${MESES[calMonth]} ${calYear}</button>
      <button class="cal-nav" id="cal-next" ${!haySiguiente ? 'disabled' : ''}>›</button>
    </div>
    <div class="cal-weekdays">${DIAS.map(d => `<span>${d}</span>`).join('')}</div>
    <div class="cal-days">${celdas}</div>`;

  cal.querySelector('#cal-prev')?.addEventListener('click', e => {
    e.stopPropagation();
    let y = calYear, m = calMonth - 1;
    if (m < 0) { m = 11; y--; }
    while (![...calFechasSet].some(f => { const [fy,fm] = f.split('-').map(Number); return fy===y && fm===m+1; })) {
      m--; if (m < 0) { m = 11; y--; }
    }
    calYear = y; calMonth = m; renderCal();
  });
  cal.querySelector('#cal-next')?.addEventListener('click', e => {
    e.stopPropagation();
    let y = calYear, m = calMonth + 1;
    if (m > 11) { m = 0; y++; }
    while (![...calFechasSet].some(f => { const [fy,fm] = f.split('-').map(Number); return fy===y && fm===m+1; })) {
      m++; if (m > 11) { m = 0; y++; }
    }
    calYear = y; calMonth = m; renderCal();
  });
  cal.querySelector('.cal-title-btn')?.addEventListener('click', e => {
    e.stopPropagation(); calVista = 'meses'; renderCal();
  });
  cal.querySelectorAll('.cal-day:not(.disabled):not(.empty)').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const fecha = btn.dataset.fecha;
      calFechaSeleccionada = fecha;
      actualizarDisplay(fecha);
      cerrarCal();
      actualizarBotonesDia();
      if (calOnChange) calOnChange(fecha);
    });
  });
}

function renderCalMeses(cal) {
  const MESES_CORTOS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
  const mesesActivos = mesesConDatosEnAnio(calYear);
  const anios = aniosConDatos();
  const hayAnioAnterior  = [...anios].some(y => y < calYear);
  const hayAnioSiguiente = [...anios].some(y => y > calYear);
  let celdas = '';
  for (let m = 0; m < 12; m++) {
    const activo = mesesActivos.has(m);
    const selec  = (calYear === parseInt(calFechaSeleccionada?.split('-')[0]) &&
                    m === parseInt(calFechaSeleccionada?.split('-')[1]) - 1) ? ' selected' : '';
    const dis    = activo ? '' : ' disabled';
    celdas += `<button class="cal-mes${dis}${selec}" data-mes="${m}">${MESES_CORTOS[m]}</button>`;
  }
  cal.innerHTML = `
    <div class="cal-header">
      <button class="cal-nav" id="cal-prev" ${!hayAnioAnterior ? 'disabled' : ''}>‹</button>
      <button class="cal-title-btn">${calYear}</button>
      <button class="cal-nav" id="cal-next" ${!hayAnioSiguiente ? 'disabled' : ''}>›</button>
    </div>
    <div class="cal-grid-meses">${celdas}</div>`;

  cal.querySelector('#cal-prev')?.addEventListener('click', e => {
    e.stopPropagation();
    let y = calYear - 1;
    while (!aniosConDatos().has(y) && y > 1900) y--;
    calYear = y; renderCal();
  });
  cal.querySelector('#cal-next')?.addEventListener('click', e => {
    e.stopPropagation();
    let y = calYear + 1;
    while (!aniosConDatos().has(y) && y < 2100) y++;
    calYear = y; renderCal();
  });
  cal.querySelector('.cal-title-btn')?.addEventListener('click', e => {
    e.stopPropagation();
    calDecada = Math.floor(calYear / 10) * 10; calVista = 'años'; renderCal();
  });
  cal.querySelectorAll('.cal-mes:not(.disabled)').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      calMonth = parseInt(btn.dataset.mes); calVista = 'dias'; renderCal();
    });
  });
}

function renderCalAnios(cal) {
  const anios = aniosConDatos();
  const inicio = calDecada, fin = calDecada + 11;
  const hayAnterior  = [...anios].some(y => y < inicio);
  const haySiguiente = [...anios].some(y => y > fin);
  let celdas = '';
  for (let y = inicio; y <= fin; y++) {
    const activo = anios.has(y);
    const selec  = y === calYear ? ' selected' : '';
    const dis    = activo ? '' : ' disabled';
    celdas += `<button class="cal-anio${dis}${selec}" data-anio="${y}">${y}</button>`;
  }
  cal.innerHTML = `
    <div class="cal-header">
      <button class="cal-nav" id="cal-prev" ${!hayAnterior ? 'disabled' : ''}>‹</button>
      <button class="cal-title-btn">${inicio} – ${fin}</button>
      <button class="cal-nav" id="cal-next" ${!haySiguiente ? 'disabled' : ''}>›</button>
    </div>
    <div class="cal-grid-anios">${celdas}</div>`;

  cal.querySelector('#cal-prev')?.addEventListener('click', e => {
    e.stopPropagation(); calDecada -= 12; renderCal();
  });
  cal.querySelector('#cal-next')?.addEventListener('click', e => {
    e.stopPropagation(); calDecada += 12; renderCal();
  });
  cal.querySelector('.cal-title-btn')?.addEventListener('click', e => { e.stopPropagation(); });
  cal.querySelectorAll('.cal-anio:not(.disabled)').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      calYear = parseInt(btn.dataset.anio); calVista = 'meses'; renderCal();
    });
  });
}

function actualizarDisplay(fecha) {
  const disp = document.getElementById('estacion-display');
  if (!disp) return;
  const [y, m, d] = fecha.split('-');
  disp.querySelector('span').textContent = `${d}/${m}/${y}`;
}

function actualizarBotonesDia() {
  const fechasArr = [...calFechasSet].sort().reverse();
  const idx = fechasArr.indexOf(calFechaSeleccionada);
  const prevBtn = document.getElementById('estacion-dia-prev');
  const nextBtn = document.getElementById('estacion-dia-next');
  if (prevBtn) prevBtn.disabled = idx >= fechasArr.length - 1;
  if (nextBtn) nextBtn.disabled = idx <= 0;
}

function abrirCal(anchorEl) {
  let cal = document.getElementById('estacion-cal');
  if (!cal) {
    cal = document.createElement('div');
    cal.id = 'estacion-cal';
    document.body.appendChild(cal);
  }
  renderCal();
  if (isMobile()) {
    const vw = window.innerWidth;
    const calW = Math.min(240, vw - 24);
    cal.style.width = calW + 'px';
    cal.style.left  = Math.round((vw - calW) / 2) + 'px';
    const rect = anchorEl.getBoundingClientRect();
    cal.style.top = (rect.bottom + 6) + 'px';
  } else {
    cal.style.width = '240px';
    const rect = anchorEl.getBoundingClientRect();
    cal.style.top  = `${rect.bottom + 6}px`;
    cal.style.left = `${rect.left}px`;
  }
  cal.style.display = 'block';
}

function cerrarCal() {
  const cal = document.getElementById('estacion-cal');
  if (cal) cal.style.display = 'none';
}

document.addEventListener('click', e => {
  const cal  = document.getElementById('estacion-cal');
  const disp = document.getElementById('estacion-display');
  if (cal && !cal.contains(e.target) && e.target !== disp && !disp?.contains(e.target)) {
    cerrarCal();
  }
});

function iniciarCalendario(fechas, onChangeCb) {
  calFechasSet = new Set(fechas);
  calFechaMin  = fechas[fechas.length - 1];
  calFechaMax  = fechas[0];
  calFechaSeleccionada = fechas[0];
  calOnChange  = onChangeCb;
  calVista = 'dias';
  const [y, m] = fechas[0].split('-').map(Number);
  calYear = y; calMonth = m - 1;

  const disp = document.getElementById('estacion-display');
  if (disp) {
    const [yr, mo, da] = fechas[0].split('-');
    disp.querySelector('span').textContent = `${da}/${mo}/${yr}`;
    const nuevo = disp.cloneNode(true);
    disp.parentNode.replaceChild(nuevo, disp);
    nuevo.addEventListener('click', e => {
      e.stopPropagation();
      const cal = document.getElementById('estacion-cal');
      if (cal && cal.style.display !== 'none') { cerrarCal(); return; }
      abrirCal(nuevo);
    });
  }

  const fechasArr = [...calFechasSet].sort().reverse();
  const prevBtn = document.getElementById('estacion-dia-prev');
  const nextBtn = document.getElementById('estacion-dia-next');
  const newPrev = prevBtn.cloneNode(true);
  const newNext = nextBtn.cloneNode(true);
  prevBtn.parentNode.replaceChild(newPrev, prevBtn);
  nextBtn.parentNode.replaceChild(newNext, nextBtn);

  newPrev.addEventListener('click', e => {
    e.stopPropagation();
    const idx = fechasArr.indexOf(calFechaSeleccionada);
    if (idx < fechasArr.length - 1) {
      const fecha = fechasArr[idx + 1];
      calFechaSeleccionada = fecha;
      const [y, m] = fecha.split('-').map(Number);
      calYear = y; calMonth = m - 1;
      actualizarDisplay(fecha);
      actualizarBotonesDia();
      if (calOnChange) calOnChange(fecha);
    }
  });

  newNext.addEventListener('click', e => {
    e.stopPropagation();
    const idx = fechasArr.indexOf(calFechaSeleccionada);
    if (idx > 0) {
      const fecha = fechasArr[idx - 1];
      calFechaSeleccionada = fecha;
      const [y, m] = fecha.split('-').map(Number);
      calYear = y; calMonth = m - 1;
      actualizarDisplay(fecha);
      actualizarBotonesDia();
      if (calOnChange) calOnChange(fecha);
    }
  });

  actualizarBotonesDia();
}

// ─── Inyectar modal ───────────────────────────────────────────────────────────
(function crearModal() {
  if (document.getElementById('modal-estacion')) return;
  document.body.insertAdjacentHTML('beforeend', `
    <div id="modal-estacion" style="
        display:none; position:fixed; inset:0; z-index:9999;
        background:rgba(0,0,0,0.35); backdrop-filter:blur(2px);
        align-items:center; justify-content:center;">
      <div id="modal-estacion-inner" style="
          background:#f8f9fa; border-radius:14px;
          box-shadow:0 8px 40px rgba(0,0,0,0.22);
          width:680px; max-width:96vw;
          display:flex; flex-direction:column; overflow:hidden;">

        <!-- Cabecera -->
        <div style="
            background:white; padding:14px 16px 10px; border-bottom:1px solid #e9ecef;
            display:flex; justify-content:space-between; align-items:flex-start; flex-shrink:0;">
          <div>
            <div id="modal-estacion-nombre" style="font-weight:700; font-size:1rem; color:#212529;"></div>
            <div id="modal-estacion-meta" style="font-size:0.72rem; color:#adb5bd; margin-top:1px;"></div>
          </div>
          <button id="modal-estacion-close" style="
              background:none; border:none; cursor:pointer; padding:2px 4px;
              font-size:1.2rem; color:#adb5bd; line-height:1; margin-left:8px;">✕</button>
        </div>

        <!-- Selector de fecha -->
        <div style="background:white; padding:10px 16px; border-bottom:1px solid #e9ecef; flex-shrink:0;
                    display:flex; align-items:center; gap:8px;">
          <label style="font-size:0.72rem; font-weight:700; text-transform:uppercase;
                        letter-spacing:0.05em; color:#adb5bd; white-space:nowrap;">Fecha</label>
          <button id="estacion-dia-prev" style="
              background:none; border:1px solid #dee2e6; border-radius:6px;
              width:28px; height:28px; cursor:pointer; font-size:1rem; color:#868e96;
              display:flex; align-items:center; justify-content:center; flex-shrink:0;
              transition:background 0.15s;">‹</button>
          <div id="estacion-display">
            <span style="font-size:0.82rem; color:#212529;">—</span>
            <span class="cal-icon">📅</span>
          </div>
          <button id="estacion-dia-next" style="
              background:none; border:1px solid #dee2e6; border-radius:6px;
              width:28px; height:28px; cursor:pointer; font-size:1rem; color:#868e96;
              display:flex; align-items:center; justify-content:center; flex-shrink:0;
              transition:background 0.15s;">›</button>
        </div>

        <!-- Contenido -->
        <div id="modal-estacion-body" style="padding:12px 14px; overflow-y:auto; overscroll-behavior:contain;"></div>

      </div>
    </div>
  `);

  document.getElementById('modal-estacion-close').addEventListener('click', () => {
    cerrarCal(); cerrarModal();
  });
  document.getElementById('modal-estacion').addEventListener('click', e => {
    if (e.target === document.getElementById('modal-estacion')) { cerrarCal(); cerrarModal(); }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { cerrarCal(); cerrarModal(); }
  });
})();

function cerrarModal() {
  document.getElementById('modal-estacion').style.display = 'none';
}

function abrirModal() {
  const modal = document.getElementById('modal-estacion');
  const inner = document.getElementById('modal-estacion-inner');
  const body  = document.getElementById('modal-estacion-body');
  modal.style.display = 'flex';
  if (isMobile()) {
    inner.style.width        = '100%';
    inner.style.maxWidth     = '100%';
    inner.style.borderRadius = '14px 14px 0 0';
    inner.style.maxHeight    = '90vh';
    modal.style.alignItems   = 'flex-end';
    body.style.maxHeight     = '60vh';
  } else {
    inner.style.width        = '680px';
    inner.style.maxWidth     = '96vw';
    inner.style.borderRadius = '14px';
    inner.style.maxHeight    = '95vh';
    modal.style.alignItems   = 'center';
    body.style.maxHeight     = '';
  }
}

// ─── Cargar datos de una fecha ────────────────────────────────────────────────
window.cargarDatosEstacion = async function(estacionId, fecha) {
  const cont = document.getElementById('modal-estacion-body');
  if (!cont || !fecha) return;

  cont.innerHTML = `
    <div style="text-align:center; color:#adb5bd; padding:30px 0;">
      <div class="spinner-border spinner-border-sm" role="status"></div>
      <span class="ms-2" style="font-size:0.78rem;">Cargando...</span>
    </div>`;

  try {
    const resp = await fetch(`/api/estaciones/${estacionId}/datos/${fecha}`);
    if (!resp.ok) throw new Error();
    const d = await resp.json();

    const fmt  = (v, dec = 1) => (v !== null && v !== undefined) ? parseFloat(v).toFixed(dec) : '—';
    const fmtH = v => {
      if (v === null || v === undefined) return '';
      const s = String(Math.round(v)).padStart(4, '0');
      return `${s.slice(0, 2)}:${s.slice(2)}`;
    };
    const fmtDir = v => {
      if (!v && v !== 0) return '—';
      const dirs = ['N','NE','E','SE','S','SO','O','NO'];
      return `${dirs[Math.round(v / 45) % 8]} (${fmt(v, 0)}°)`;
    };

    // Celda individual dentro de una tarjeta
    const cel = (label, valor, hora = '') => `
      <div style="padding:10px 14px; border-bottom:1px solid #f1f3f5;">
        <div style="font-size:0.7rem; color:#868e96; font-weight:600;
                    margin-bottom:4px;">${label}</div>
        <div style="font-weight:700; font-size:1rem; color:#212529;">
          ${valor}
          ${hora ? `<span style="font-weight:500; font-size:0.75rem; color:#868e96; margin-left:5px;">${hora}</span>` : ''}
        </div>
      </div>`;

    // Colores por sección
    const COLORES = {
      '🌡️': { bg: '#fff5f5', border: '#ffc9c9', text: '#c92a2a' },
      '💧': { bg: '#e7f5ff', border: '#a5d8ff', text: '#1971c2' },
      '💨': { bg: '#f3f0ff', border: '#d0bfff', text: '#6741d9' },
      '🌧️': { bg: '#e6fcf5', border: '#96f2d7', text: '#0ca678' },
      '📊': { bg: '#fff9db', border: '#ffec99', text: '#e67700' },
      '🌱': { bg: '#ebfbee', border: '#b2f2bb', text: '#2f9e44' },
    };

    // Tarjeta con cabecera coloreada y grid de 2 columnas
    const card = (emoji, titulo, items) => {
      const c = COLORES[emoji] || { bg: '#f8f9fa', border: '#e9ecef', text: '#495057' };
      return `
        <div style="background:white; border:1px solid ${c.border}; border-radius:10px;
                    overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <div style="padding:8px 12px; border-bottom:1px solid ${c.border};
                      display:flex; align-items:center; gap:6px; background:${c.bg};">
            <span style="font-size:0.9rem;">${emoji}</span>
            <span style="font-size:0.68rem; font-weight:700; text-transform:uppercase;
                         letter-spacing:0.06em; color:${c.text};">${titulo}</span>
          </div>
          <div style="display:grid; grid-template-columns:1fr 1fr;">
            ${items}
          </div>
        </div>`;
    };

    // En móvil las tarjetas ocupan todo el ancho, en desktop 2 columnas
    const gridStyle = isMobile()
      ? 'display:grid; grid-template-columns:1fr; gap:10px; padding:2px 0 8px;'
      : 'display:grid; grid-template-columns:1fr 1fr; gap:10px; padding:2px 0 8px;';

    cont.innerHTML = `<div style="${gridStyle}">

      ${card('🌡️', 'Temperatura',
        cel('Máxima',     `${fmt(d.tempmax)} °C`,  fmtH(d.hormintempmax)) +
        cel('Mínima',     `${fmt(d.tempmin)} °C`,  fmtH(d.hormintempmin)) +
        cel('Media',      `${fmt(d.tempmedia)} °C`) +
        cel('Oscilación', `${fmt(d.tempd)} °C`)
      )}

      ${card('💧', 'Humedad',
        cel('Máxima',  `${fmt(d.humedadmax)} %`,  fmtH(d.horminhummax)) +
        cel('Mínima',  `${fmt(d.humedadmin)} %`,  fmtH(d.horminhummin)) +
        cel('Media',   `${fmt(d.humedadmedia)} %`) +
        cel('Déficit', `${fmt(d.humedadd)} %`)
      )}

      ${card('💨', 'Viento',
        cel('Vel. media',     `${fmt(d.velviento)} m/s`) +
        cel('Vel. máxima',    `${fmt(d.velvientomax)} m/s`, fmtH(d.horminvelmax)) +
        cel('Dir. media',     fmtDir(d.dirviento)) +
        cel('Dir. vel. máx.', fmtDir(d.dirvientovelmax)) +
        cel('Recorrido',      `${fmt(d.recorrido, 0)} km`) +
        cel('Viento día',     `${fmt(d.vd)} m/s`) +
        `<div style="grid-column:1/-1">` + cel('Viento noche', `${fmt(d.vn)} m/s`) + `</div>`
      )}

      ${card('🌧️', 'Precipitación y Radiación',
        cel('Precipitación', `${fmt(d.precipitacion)} mm`) +
        cel('Radiación',     `${fmt(d.radiacion)} MJ/m²`) +
        cel('Insolación',    `${fmt(d.n)} h`) +
        cel('Rn',            `${fmt(d.rn)}`) +
        `<div style="grid-column:1/-1">` + cel('Rmax', `${fmt(d.rmax)}`) + `</div>`
      )}

      ${card('📊', 'Evapotranspiración',
        cel('B-Criddle',  `${fmt(d.etbc)} mm`) +
        cel('Hargreaves', `${fmt(d.etharg)} mm`) +
        cel('P-Monteith', `${fmt(d.etpmon)} mm`) +
        cel('Radiación',  `${fmt(d.etrad)} mm`)
      )}

      ${card('🌱', 'Precipitación efectiva',
        cel('B-Criddle',  `${fmt(d.pebc)} mm`) +
        cel('Hargreaves', `${fmt(d.peharg)} mm`) +
        cel('P-Monteith', `${fmt(d.pepmon)} mm`) +
        cel('Radiación',  `${fmt(d.perad)} mm`)
      )}

    </div>`;

  } catch {
    cont.innerHTML = `
      <div style="text-align:center; color:#adb5bd; padding:30px 0; font-size:0.78rem;">
        Sin datos para esta fecha
      </div>`;
  }
};

// ─── Cargar capa ──────────────────────────────────────────────────────────────
async function cargarEstaciones() {
  try {
    const resp = await fetch('/api/estaciones');
    if (!resp.ok) throw new Error();
    const geojson = await resp.json();
    if (!geojson.features?.length) return;

    const icono = L.divIcon({
      className: '',
      html: `<div style="
        background:#0d6efd; border:3px solid white; border-radius:50%;
        width:18px; height:18px; box-shadow:0 2px 8px rgba(0,0,0,0.5);
        cursor:pointer;">
      </div>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    });

    window.estacionesLayer = L.geoJSON(geojson, {
      pane: 'estacionesPane',
      pointToLayer: (feature, latlng) => L.marker(latlng, {
        icon: icono,
        pane: 'estacionesPane',
        interactive: true,
        bubblingMouseEvents: false
      }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties;

        layer.on('click', async () => {
          document.getElementById('modal-estacion-nombre').textContent = p.nombre;
          document.getElementById('modal-estacion-meta').textContent =
            `${p.codigo} · ${p.altitud ?? '—'} m`;

          cerrarCal();
          abrirModal();

          const body = document.getElementById('modal-estacion-body');
          body.innerHTML = `
            <div style="text-align:center; color:#adb5bd; padding:30px 0;">
              <div class="spinner-border spinner-border-sm" role="status"></div>
              <span class="ms-2" style="font-size:0.78rem;">Cargando...</span>
            </div>`;

          try {
            // p.id es la PK interna — coincide con datos_diarios.estacion_id
            const r = await fetch(`/api/estaciones/${p.id}/fechas`);
            if (!r.ok) throw new Error();
            const fechas = await r.json();

            if (!fechas.length) {
              body.innerHTML = `<div style="text-align:center; color:#adb5bd; padding:30px 0; font-size:0.78rem;">Sin datos disponibles</div>`;
              return;
            }

            iniciarCalendario(fechas, async (fecha) => {
              await cargarDatosEstacion(p.id, fecha);
            });

            await cargarDatosEstacion(p.id, fechas[0]);

          } catch (err) {
            console.error('Error estación:', err);
            body.innerHTML = `<div style="text-align:center; color:#dc3545; padding:30px 0; font-size:0.78rem;">Error cargando datos</div>`;
          }
        });

        layer.bindTooltip(p.nombre, {
          permanent: false,
          direction: 'top',
          offset: [0, -12],
        });
      }
    }).addTo(map);

  } catch (err) {
    console.error('Error cargando capa estaciones:', err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setTimeout(cargarEstaciones, 500);
});