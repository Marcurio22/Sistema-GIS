/**
 * visor-subparcelas.js
 * ─────────────────────────────────────────────────────────────
 * División de un recinto en subparcelas con asignación de cultivo.
 *
 * Sigue exactamente el mismo patrón que visor-dibujos.js:
 *  • DOMContentLoaded
 *  • Dibujo de líneas divisorias por 2 clics (sin Leaflet.Draw)
 *  • toggleInteraccionRecintos() con los mismos panes
 *  • window.modoSubparcelas = true/false  →  visor-dibujos.js
 *
 * Globals requeridos (todos disponibles cuando DOMContentLoaded dispara):
 *   window.map, window.modoEdicion, window.recintosLayer,
 *   window.recintoResaltado, window.currentRecintoData,
 *   window.currentSideRecintoId, NotificationSystem, AppConfirm, turf, L
 */
document.addEventListener('DOMContentLoaded', function () {

  const map = window.map;
  if (!map || !window.L) {
    console.error('[subparcelas] map o Leaflet no disponibles');
    return;
  }

  /* ─────────────────────────────────────────────
     Estado
  ───────────────────────────────────────────── */
  let _recintoId      = null;   // id_recinto activo
  let _recintoFeature = null;   // Feature GeoJSON del recinto (para turf.intersect)
  let _borradores     = [];     // [{nombre, ha, feature, mapLayer}]
  let _drawnLayer     = null;   // L.FeatureGroup — polígonos en edición
  let _linesLayer     = null;   // L.FeatureGroup — líneas divisorias dibujadas
  let _savedLayer     = null;   // L.FeatureGroup — subparcelas guardadas en mapa
  let _maskLayer      = null;   // L.GeoJSON    — máscara gris fuera del recinto
  let _captureLayer   = null;   // L.GeoJSON    — captura de clics dentro del recinto al dibujar
  let _catalogoCache  = null;
  let _enModoEdicion  = false;
  let _habiaSubparcelas = false;  // ¿el recinto ya tenía subparcelas al abrir el editor?
  let _savedMaxBounds = null;
  let _fusionSel      = new Set();
  let _borradorFusionSel = new Set();
  let _savedLayerById = new Map();   // id_subparcela → layer (mapa, guardadas)
  let _selectedSavedId = null;       // subparcela resaltada desde el panel

  // Dibujo de línea por 2 toques/clics
  let _dibujando      = false;
  let _lineStart      = null;        // L.LatLng del primer toque
  let _previewLine    = null;        // L.Polyline de previsualización
  let _firstPointMarker = null;      // Marcador visual del primer punto (móvil)
  let _drawMoveHandler  = null;
  let _drawKeyHandler   = null;
  let _drawTouchMoveHandler = null;
  let _docTouchEndHandler = null;    // listener a nivel document para touch
  let _savedMapDragging = true;
  let _savedTouchZoom = true;
  // Bloquea el inicio de edición durante 400ms tras abrir (evita que el tap
  // que abrió el panel también dispare el primer punto de dibujo).
  let _editOpenedAt = 0;

  const $ = id => document.getElementById(id);
  const _isTouchUi = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);

  function lockMobileDrawScroll(lock) {
    if (!window.matchMedia('(max-width: 768px)').matches) return;
    document.documentElement.style.overflow = lock ? 'hidden' : '';
    document.body.style.overflow = lock ? 'hidden' : '';
  }

  function pointerToLatLng(clientX, clientY) {
    const rect = map.getContainer().getBoundingClientRect();
    return map.containerPointToLatLng(L.point(clientX - rect.left, clientY - rect.top));
  }

  function isOnMapArea(clientX, clientY) {
    const rect = map.getContainer().getBoundingClientRect();
    return clientX >= rect.left && clientX <= rect.right &&
           clientY >= rect.top  && clientY <= rect.bottom;
  }

  /* ─────────────────────────────────────────────
     Notificaciones / confirmación  (mismos helpers que visor-dibujos.js)
  ───────────────────────────────────────────── */
  function notifError(msg) {
    NotificationSystem.show({ type: 'error', title: 'Error', message: msg });
  }
  function notifOk(msg) {
    NotificationSystem.show({ type: 'success', title: 'Hecho', message: msg });
  }
  async function confirmar(titulo, texto) {
    return AppConfirm.open({
      title: titulo,
      message: texto,
      okText: 'Sí, continuar',
      cancelText: 'Cancelar',
      okClass: 'btn-danger'
    });
  }

  function esc(s) {
    const d = document.createElement('div');
    d.appendChild(document.createTextNode(String(s)));
    return d.innerHTML;
  }
  function haStr(ha) {
    return Number(ha).toFixed(2).replace('.', ',') + ' ha';
  }

  /* ─────────────────────────────────────────────
     Geometría: dividir polígono con una línea
  ───────────────────────────────────────────── */
  function normalizePolygonFeature(feat) {
    if (!feat?.geometry) return feat;
    if (feat.geometry.type === 'Polygon') return feat;
    if (feat.geometry.type === 'MultiPolygon') {
      let best = null;
      let maxA = -1;
      feat.geometry.coordinates.forEach(coords => {
        const a = turf.area(turf.polygon(coords));
        if (a > maxA) { maxA = a; best = coords; }
      });
      if (best) return turf.polygon(best);
    }
    return feat;
  }

  // Devuelve un array de Features Polygon a partir de un Polygon o MultiPolygon.
  function polygonPartsOf(feat) {
    const parts = [];
    const g = feat && feat.geometry;
    if (!g) return parts;
    try {
      if (g.type === 'Polygon') {
        parts.push(turf.polygon(g.coordinates));
      } else if (g.type === 'MultiPolygon') {
        g.coordinates.forEach(c => parts.push(turf.polygon(c)));
      }
    } catch (_) { /* ignora partes inválidas */ }
    return parts;
  }

  function extendLineAcrossPolygon(lineFeat, polyFeat) {
    const coords = lineFeat.geometry?.coordinates;
    if (!coords || coords.length < 2) return lineFeat;

    const bbox = turf.bbox(polyFeat);
    const diag = Math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 3;
    const a = coords[0];
    const b = coords[coords.length - 1];
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len = Math.hypot(dx, dy);
    if (len < 1e-12) return lineFeat;

    const scale = diag / len;
    const start = [a[0] - dx * scale, a[1] - dy * scale];
    const end = [b[0] + dx * scale, b[1] + dy * scale];
    const newCoords = coords.length > 2
      ? [start, ...coords.slice(1, -1), end]
      : [start, end];
    return turf.lineString(newCoords);
  }

  function lineDividesPolygon(polyFeat, lineFeat) {
    try {
      const ext = extendLineAcrossPolygon(lineFeat, polyFeat);
      const boundary = turf.polygonToLine(polyFeat);
      const hits = turf.lineIntersect(ext, boundary);
      return hits.features.length >= 2;
    } catch (_) {
      return false;
    }
  }

  // Nº de muestras del trazo REAL (sin extender) que caen dentro de polyFeat.
  // Sirve para saber qué pieza ha querido cortar el usuario (sin depender de lineSplit).
  function muestrasDentroDePieza(lineFeat, polyFeat) {
    try {
      const cs = lineFeat.geometry.coordinates;
      const a = cs[0];
      const b = cs[cs.length - 1];
      const N = 20;
      let dentro = 0;
      for (let k = 0; k <= N; k++) {
        const t = k / N;
        const lng = a[0] + (b[0] - a[0]) * t;
        const lat = a[1] + (b[1] - a[1]) * t;
        if (turf.booleanPointInPolygon(turf.point([lng, lat]), polyFeat)) dentro++;
      }
      return dentro;
    } catch (_) {
      return 0;
    }
  }

  function polygonsFromGeometry(geom) {
    const list = [];
    if (!geom) return list;
    if (geom.type === 'Polygon') {
      list.push(geom.coordinates);
    } else if (geom.type === 'MultiPolygon') {
      geom.coordinates.forEach(c => list.push(c));
    }
    return list;
  }

  // Divide el polígono con la línea usando dos semiplanos.
  // Las dos piezas comparten exactamente la línea de corte → SIN hueco,
  // de modo que luego se pueden volver a fusionar perfectamente.
  function splitPolygonByLine(polyFeat, lineFeat) {
    const extended = extendLineAcrossPolygon(lineFeat, polyFeat);
    const cs = extended.geometry.coordinates;
    const a = cs[0];
    const b = cs[cs.length - 1];
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len = Math.hypot(dx, dy);
    if (len < 1e-12) return null;

    // Normal a la línea, escalada bien grande para cubrir todo el polígono
    const bbox = turf.bbox(polyFeat);
    const big = Math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 3 + 0.01;
    const nx = (-dy / len) * big;
    const ny = (dx / len) * big;

    let semiA, semiB;
    try {
      semiA = turf.polygon([[
        [a[0], a[1]], [b[0], b[1]],
        [b[0] + nx, b[1] + ny], [a[0] + nx, a[1] + ny],
        [a[0], a[1]],
      ]]);
      semiB = turf.polygon([[
        [a[0], a[1]], [b[0], b[1]],
        [b[0] - nx, b[1] - ny], [a[0] - nx, a[1] - ny],
        [a[0], a[1]],
      ]]);
    } catch (_) {
      return null;
    }

    const parts = [];
    [semiA, semiB].forEach(half => {
      try {
        const inter = turf.intersect(polyFeat, half);
        if (!inter) return;
        polygonsFromGeometry(inter.geometry).forEach(coords => {
          const p = turf.polygon(coords);
          if (turf.area(p) / 10000 >= 0.0001) parts.push(p);
        });
      } catch (_) { /* omitir semiplano inválido */ }
    });

    return parts.length >= 2 ? parts : null;
  }

  /* Garantiza que feat sea un Feature{Polygon} clipeado al recinto.
     Si turf devuelve MultiPolygon, nos quedamos con la parte más grande. */
  function clipToRecintoPolygon(feat) {
    if (!feat?.geometry) return feat;
    try {
      const clipped = turf.intersect(feat, _recintoFeature);
      if (!clipped) return feat;
      if (clipped.geometry.type === 'Polygon') return clipped;
      if (clipped.geometry.type === 'MultiPolygon') {
        let best = null, maxA = -1;
        clipped.geometry.coordinates.forEach(coords => {
          const a = turf.area(turf.polygon(coords));
          if (a > maxA) { maxA = a; best = coords; }
        });
        return best ? turf.polygon(best) : feat;
      }
    } catch (_) {}
    return feat;
  }

  function ensureSubparcelasDraftPane() {
    if (!map.getPane('subparcelasDraftPane')) {
      map.createPane('subparcelasDraftPane');
    }
    const pane = map.getPane('subparcelasDraftPane');
    // Por encima de la máscara (650) y visible durante la edición
    pane.style.zIndex = '720';
    pane.style.pointerEvents = 'none';
  }

  function createBorrador(feat, nombre) {
    ensureSubparcelasDraftPane();
    const safe = clipToRecintoPolygon(feat);
    const ha = turf.area(safe) / 10000;
    const mapLayer = L.geoJSON(safe, {
      pane: 'subparcelasDraftPane',
      style: { color: '#90bc05', weight: 2, fillColor: '#90bc05', fillOpacity: 0.45 },
    });
    return { nombre, ha, feature: safe, mapLayer };
  }

  function renumerarBorradores() {
    _borradores.forEach((b, i) => {
      if (/^Subparcela (\d+)$/.test(b.nombre)) b.nombre = String(i + 1);
      else if (/^\d+$/.test(b.nombre)) b.nombre = String(i + 1);
      const col = COLS[i % COLS.length];
      if (b.mapLayer) {
        b.mapLayer.setStyle({ color: col, fillColor: col, fillOpacity: 0.45 });
      }
    });
  }

  // Vuelve a pintar todas las piezas de borrador en el mapa (sin duplicados)
  function repintarBorradoresEnMapa() {
    if (!_drawnLayer) return;
    _drawnLayer.clearLayers();
    _borradores.forEach((b, i) => {
      const col = COLS[i % COLS.length];
      if (b.mapLayer) {
        b.mapLayer.setStyle({ color: col, weight: 2, fillColor: col, fillOpacity: 0.45 });
        b.mapLayer.eachLayer(l => _drawnLayer.addLayer(l));
      }
    });
  }

  // Índice de la pieza que comparte mayor frontera con la pieza idx
  function vecinoMasCercano(idx) {
    const target = _borradores[idx];
    if (!target) return -1;
    let grown;
    try { grown = turf.buffer(target.feature, 1, { units: 'meters' }); }
    catch (_) { grown = target.feature; }

    let best = -1, bestScore = 0;
    for (let j = 0; j < _borradores.length; j++) {
      if (j === idx) continue;
      try {
        const inter = turf.intersect(grown, _borradores[j].feature);
        if (inter) {
          const a = turf.area(inter);
          if (a > bestScore) { bestScore = a; best = j; }
        }
      } catch (_) {}
    }
    return best;
  }

  // Borra una pieza fusionando su área con la vecina (evita dejar huecos).
  // Si es la única, simplemente se elimina (queda el recinto sin dividir).
  function eliminarBorrador(idx) {
    if (idx < 0 || idx >= _borradores.length) return;

    // Única pieza → eliminar sin más
    if (_borradores.length <= 1) {
      const b = _borradores[idx];
      if (b?.mapLayer) b.mapLayer.eachLayer(l => _drawnLayer.removeLayer(l));
      _borradores = [];
      _borradorFusionSel.clear();
      repintarBorradoresEnMapa();
      actualizarBorradores();
      actualizarBtnGuardar();
      return;
    }

    const vecino = vecinoMasCercano(idx);
    const target = _borradores[idx];

    if (vecino >= 0) {
      const v = _borradores[vecino];
      const union = unionPolygonFeatures([v.feature, target.feature]);
      if (union) {
        _borradores[vecino] = createBorrador(clipToRecintoPolygon(union), v.nombre);
      }
    }

    _borradores.splice(idx, 1);
    _borradorFusionSel.clear();
    renumerarBorradores();
    repintarBorradoresEnMapa();
    actualizarBorradores();
    actualizarBtnGuardar();
  }

  function aplicarDivisionPorLinea(lineaFeature) {
    const targets = _borradores.length > 0
      ? _borradores.map((b, i) => ({ ...b, index: i, virtual: false }))
      : [{ feature: _recintoFeature, nombre: 'Recinto', ha: 0, mapLayer: null, virtual: true }];

    const resultado = [];
    let huboDivision = false;

    // Solo se considera "objetivo" la(s) pieza(s) que el TRAZO real atraviesa.
    // Así, una línea corta dentro de una zona no corta también las vecinas.
    const MIN_MUESTRAS = 2;   // de 21 muestras a lo largo del trazo

    for (const t of targets) {
      // Si la pieza no es virtual (recinto entero) y el trazo apenas la toca, se ignora.
      if (!t.virtual && muestrasDentroDePieza(lineaFeature, t.feature) < MIN_MUESTRAS) {
        resultado.push(t);
        continue;
      }

      if (!lineDividesPolygon(t.feature, lineaFeature)) {
        if (!t.virtual) resultado.push(t);
        continue;
      }

      const parts = splitPolygonByLine(t.feature, lineaFeature);
      if (!parts || parts.length < 2) {
        if (!t.virtual) resultado.push(t);
        continue;
      }

      huboDivision = true;
      if (t.mapLayer) t.mapLayer.eachLayer(l => _drawnLayer.removeLayer(l));
      parts.forEach(part => resultado.push(createBorrador(part, String(resultado.length + 1))));
    }

    if (!huboDivision) return false;

    _borradores = resultado;
    renumerarBorradores();
    _borradores.forEach(b => {
      if (b.mapLayer) b.mapLayer.eachLayer(l => _drawnLayer.addLayer(l));
    });
    return true;
  }

  function puntoDentroRecinto(lng, lat) {
    if (!_recintoFeature) return false;
    try {
      return turf.booleanPointInPolygon(turf.point([lng, lat]), _recintoFeature);
    } catch (_) {
      return false;
    }
  }

  function unionPolygonFeatures(features) {
    if (!features.length) return null;
    const norm = features.map(normalizePolygonFeature);
    const sumA = norm.reduce((s, f) => { try { return s + turf.area(f); } catch (_) { return s; } }, 0);

    // 1) Intento directo (piezas contiguas sin hueco → un solo polígono)
    let u = norm[0];
    let ok = true;
    for (let i = 1; i < norm.length; i++) {
      try {
        const r = turf.union(u, norm[i]);
        if (!r) { ok = false; break; }
        u = r;
      } catch (_) { ok = false; break; }
    }
    if (ok && u && u.geometry?.type === 'Polygon') return u;

    // 2) Cierre morfológico: dilatar, unir y erosionar para puentear
    //    huecos de cortes antiguos (cuando la división dejaba separación).
    try {
      const EPS = 3; // metros
      let g = turf.buffer(norm[0], EPS, { units: 'meters' });
      for (let i = 1; i < norm.length; i++) {
        const r = turf.union(g, turf.buffer(norm[i], EPS, { units: 'meters' }));
        if (!r) return null;
        g = r;
      }
      let shr = turf.buffer(g, -EPS, { units: 'meters' });
      shr = normalizePolygonFeature(shr);
      // Solo válido si cubre prácticamente toda el área (→ eran contiguas)
      if (shr && shr.geometry?.type === 'Polygon' && turf.area(shr) >= sumA * 0.85) {
        return shr;
      }
    } catch (_) { /* cae a null */ }

    return null;
  }

  function fusionarBorradoresPorIndices(indices) {
    if (indices.length < 2) return false;

    const sorted = [...indices].sort((a, b) => a - b);
    const selected = sorted.map(i => _borradores[i]).filter(Boolean);
    if (selected.length < 2) return false;

    const unionFeat = unionPolygonFeatures(selected.map(b => b.feature));
    if (!unionFeat) {
      notifError('No se pudieron fusionar. Solo puedes unir subparcelas que estén juntas.');
      return false;
    }

    sorted.forEach(i => {
      const b = _borradores[i];
      if (b?.mapLayer) b.mapLayer.eachLayer(l => _drawnLayer.removeLayer(l));
    });

    const nombres = selected.map(b => b.nombre).filter(Boolean);
    const nombre = nombres.length ? nombres.join(' + ') : 'Subparcela fusionada';
    const safeUnion = clipToRecintoPolygon(unionFeat);
    const nuevo = createBorrador(safeUnion, nombre);
    nuevo.mapLayer.eachLayer(l => _drawnLayer.addLayer(l));

    const rest = _borradores.filter((_, i) => !sorted.includes(i));
    _borradores = [...rest, nuevo];
    renumerarBorradores();
    _borradorFusionSel.clear();
    return true;
  }

  function pintarLineaDivisoria(lineaFeature) {
    if (!_linesLayer) return;
    ensureSubparcelasDraftPane();
    L.geoJSON(lineaFeature, {
      pane: 'subparcelasDraftPane',
      style: { color: '#dc3545', weight: 3, dashArray: '8 6', opacity: 0.95 },
    }).eachLayer(l => _linesLayer.addLayer(l));
  }

  function ensureSubparcelasBlockPane() {
    if (!map.getPane('subparcelasBlockPane')) {
      map.createPane('subparcelasBlockPane');
    }
    const pane = map.getPane('subparcelasBlockPane');
    pane.style.zIndex = '650';
    pane.style.pointerEvents = 'auto';
  }

  function ensureSubparcelasSavedPane() {
    if (!map.getPane('subparcelasSavedPane')) {
      map.createPane('subparcelasSavedPane');
    }
    const pane = map.getPane('subparcelasSavedPane');
    // Por encima de "misPane" y de recintos, pero por debajo de overlays modales
    pane.style.zIndex = '850';
    pane.style.pointerEvents = 'auto';
  }

  function setSavedPaneInteractive(interactive) {
    try {
      const p = map.getPane('subparcelasSavedPane');
      if (p) p.style.pointerEvents = interactive ? 'auto' : 'none';
    } catch (_) {}
  }

  function restrictMapToRecinto() {
    try {
      _savedMaxBounds = map.getMaxBounds();
      const b = L.geoJSON(_recintoFeature).getBounds().pad(0.02);
      map.setMaxBounds(b);
    } catch (_) {}
  }

  function restoreMapBounds() {
    try {
      if (_savedMaxBounds) map.setMaxBounds(_savedMaxBounds);
    } catch (_) {}
    _savedMaxBounds = null;
  }

  let _ultimoAvisoFuera = 0;

  // Handler a nivel document captura touchend ANTES de que llegue a Leaflet
  function _crearDocTouchHandler() {
    return function(e) {
      if (!_dibujando) return;
      if (Date.now() - _editOpenedAt < 200) return; // ignora tap residual de apertura

      const touch = e.changedTouches?.[0];
      if (!touch) return;

      // Solo actuar si el toque fue sobre el área del mapa
      if (!isOnMapArea(touch.clientX, touch.clientY)) return;

      // Ignorar si el toque fue sobre controles UI
      if (e.target?.closest?.(
        '#subparcelas-mobile-draw-bar, #side-panel, .leaflet-control, ' +
        '#notification-container, .notification, .basemap-panel-container'
      )) return;

      e.preventDefault();
      e.stopPropagation();

      const latlng = pointerToLatLng(touch.clientX, touch.clientY);
      onDrawClick({ latlng });
    };
  }

  function _crearDocTouchMoveHandler() {
    return function(e) {
      if (!_dibujando || !_lineStart) return;
      const touch = e.touches?.[0];
      if (!touch || !isOnMapArea(touch.clientX, touch.clientY)) return;
      onDrawMove({ latlng: pointerToLatLng(touch.clientX, touch.clientY) });
    };
  }

  /* ─────────────────────────────────────────────
     Interacción recintos — EXACTAMENTE igual que visor-dibujos.js
     Leaflet.Draw usa overlayPane (z-index ~400).
     Bajamos sigpacPane, misPane y highlightPane por debajo de 400
     para que sus polígonos SVG no intercepten los clics del dibujador.
  ───────────────────────────────────────────── */
  function toggleInteraccionRecintos(enabled) {
    const sigpacP    = map.getPane('sigpacPane');
    const misP       = map.getPane('misPane');
    const highlightP = map.getPane('highlightPane');

    if (enabled) {
      // Restaurar z-indexes originales
      if (sigpacP) {
        sigpacP.style.zIndex = '700';
        sigpacP.style.pointerEvents = '';
      }
      if (misP) {
        misP.style.zIndex = '800';
        misP.style.pointerEvents = '';
      }
      if (highlightP) {
        highlightP.style.zIndex = '900';
        highlightP.style.pointerEvents = '';
      }

      // Restaurar popups en la capa SIGPAC
      if (window.recintosLayer) {
        window.recintosLayer.eachLayer(layer => {
          if (layer._savedPopup) {
            layer.bindPopup(layer._savedPopup);
            delete layer._savedPopup;
          }
        });
      }
      // Restaurar popup del recinto resaltado
      if (window.recintoResaltado && window._savedHighlightPopup) {
        window.recintoResaltado.eachLayer(l => {
          if (l.bindPopup) l.bindPopup(window._savedHighlightPopup);
        });
        delete window._savedHighlightPopup;
      }

      // Avisar al resto del visor de que ya no estamos en modo subparcelas
      window.modoEdicion    = false;
      window.modoSubparcelas = false;

    } else {
      // Bajar z-index y desactivar clics en recintos durante edición de subparcelas
      if (sigpacP) {
        sigpacP.style.zIndex = '200';
        sigpacP.style.pointerEvents = 'none';
      }
      if (misP) {
        misP.style.zIndex = '200';
        misP.style.pointerEvents = 'none';
      }
      if (highlightP) {
        highlightP.style.zIndex = '200';
        highlightP.style.pointerEvents = 'none';
      }

      // Quitar popups de la capa SIGPAC
      if (window.recintosLayer) {
        window.recintosLayer.eachLayer(layer => {
          if (layer._popup) {
            layer._savedPopup = layer._popup;
          }
          layer.unbindPopup();
        });
      }
      // Quitar popup del recinto resaltado (evita el popup al clicar en él)
      if (window.recintoResaltado) {
        window.recintoResaltado.eachLayer(l => {
          if (l.getPopup && l.getPopup()) {
            window._savedHighlightPopup = l.getPopup();
            l.unbindPopup();
          }
        });
      }

      // Bloquear los handlers de click en mis-recintos y SIGPAC
      window.modoEdicion    = true;
      window.modoSubparcelas = true;
    }
  }

  /* ─────────────────────────────────────────────
     Máscara visual fuera del recinto
     Usa turf.difference: bbox_grande - recinto = zona gris
  ───────────────────────────────────────────── */
  function mostrarMascara(recintoFeature) {
    quitarMascara();
    try {
      ensureSubparcelasBlockPane();
      const bbox = turf.bboxPolygon([-10, 35, 5, 44]); // cubre España
      const mask = turf.difference(bbox, recintoFeature);
      if (!mask) return;
      // Solo visual — sin handlers; los eventos se gestionan por document listener
      _maskLayer = L.geoJSON(mask, {
        style: {
          color: 'transparent',
          fillColor: '#000',
          fillOpacity: 0.45,
          interactive: false,
        },
        pane: 'subparcelasBlockPane',
      });
      _maskLayer.addTo(map);
    } catch (_) { /* turf puede fallar con MultiPolygon complejos — no crítico */ }
  }

  function quitarMascara() {
    if (_maskLayer) { map.removeLayer(_maskLayer); _maskLayer = null; }
  }

  function ensureSubparcelasEditPane() {
    if (!map.getPane('subparcelasEditPane')) {
      map.createPane('subparcelasEditPane');
    }
    const pane = map.getPane('subparcelasEditPane');
    pane.style.zIndex = '680';
    pane.style.pointerEvents = 'auto';
  }

  // Capa transparente sobre el INTERIOR del recinto: bloquea popups del recinto.
  // Si estamos dibujando, reenvía clic/movimiento al trazado (sin borradores no hay
  // otra capa encima que deje pasar el evento al mapa).
  function activarCapaCapturaEdicion() {
    quitarCapaCapturaEdicion();
    if (!_recintoFeature || !_enModoEdicion) return;
    try {
      ensureSubparcelasEditPane();
      _captureLayer = L.geoJSON(_recintoFeature, {
        style: { color: 'transparent', weight: 0, fillColor: '#fff', fillOpacity: 0.01, interactive: true },
        pane: 'subparcelasEditPane',
      });
      _captureLayer.eachLayer(layer => {
        layer.on('click', (e) => {
          L.DomEvent.stopPropagation(e);
          if (_dibujando) onDrawClick(e);
        });
        layer.on('mousemove', (e) => {
          if (_dibujando && _lineStart) onDrawMove(e);
        });
        layer.on('touchend', (e) => L.DomEvent.stopPropagation(e));
      });
      _captureLayer.addTo(map);
    } catch (_) { /* no crítico */ }
  }

  function quitarCapaCapturaEdicion() {
    if (_captureLayer) { map.removeLayer(_captureLayer); _captureLayer = null; }
  }

  /* ─────────────────────────────────────────────
     Obtener Feature GeoJSON del recinto activo
     window.currentRecintoData lo guarda renderSidePanelFromProps
     (visor.html, línea ~1383: window.currentRecintoData = p)
  ───────────────────────────────────────────── */
  function getRecintoFeature(recintoId) {
    const d = window.currentRecintoData;
    if (!d) return null;

    const dId = String(d.id || d.id_recinto || '');
    if (dId !== String(recintoId)) return null;

    let geom = d.geojson;
    if (!geom) return null;

    try {
      if (typeof geom === 'string') geom = JSON.parse(geom);
      // geom puede ser Geometry o Feature o FeatureCollection
      if (geom.type === 'FeatureCollection' && geom.features?.length) {
        geom = geom.features[0].geometry || geom.features[0];
      }
      if (geom.type === 'Feature') return geom;
      return { type: 'Feature', geometry: geom, properties: {} };
    } catch (_) { return null; }
  }

  async function ensureRecintoFeature(recintoId) {
    let feat = getRecintoFeature(recintoId);
    if (feat) return feat;

    try {
      const r = await fetch(`/api/mis-recinto/${recintoId}`);
      if (!r.ok) return null;
      const d = await r.json();
      window.currentRecintoData = d;
      return getRecintoFeature(recintoId);
    } catch (_) {
      return null;
    }
  }

  function openOverlay() {
    const sp = document.getElementById('side-panel');
    const ov = $('subparcelas-overlay');
    if (!sp || !ov) return;

    window.closeHistoricoPanel?.();
    window.closeGaleriaPanel?.();
    window.closeOperacionesPanel?.();

    sp.classList.add('subparcelas-open');
    document.body.classList.add('subparcelas-editing');
    ov.classList.remove('d-none');
    ov.setAttribute('aria-hidden', 'false');
    if (_isTouchUi) {
      const bar = $('subparcelas-mobile-draw-bar');
      if (bar) bar.setAttribute('aria-hidden', 'false');
    }
  }

  function closeOverlay() {
    const sp = document.getElementById('side-panel');
    const ov = $('subparcelas-overlay');
    if (sp) sp.classList.remove('subparcelas-open');
    document.body.classList.remove('subparcelas-editing');
    document.body.classList.remove('subparcelas-drawing');
    if (ov) {
      ov.classList.add('d-none');
      ov.setAttribute('aria-hidden', 'true');
    }
  }

  /* ─────────────────────────────────────────────
     API
  ───────────────────────────────────────────── */
  async function apiGet(id) {
    const r = await fetch(`/api/mis-recinto/${id}/subparcelas`);
    return r.ok ? r.json() : [];
  }
  async function apiPost(id, features) {
    const r = await fetch(`/api/mis-recinto/${id}/subparcelas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ features }),
    });
    return r.json();
  }
  async function apiDelete(id) {
    const r = await fetch(`/api/mis-recinto/${id}/subparcelas`, { method: 'DELETE' });
    return r.json();
  }
  async function apiPatchCultivo(idSub, cod) {
    const r = await fetch(`/api/subparcelas/${idSub}/cultivo`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cod_producto: cod }),
    });
    return r.json();
  }

  /* ─────────────────────────────────────────────
     Catálogo productos_fega
  ───────────────────────────────────────────── */
  async function getCatalogo() {
    if (_catalogoCache) return _catalogoCache;
    try {
      const r = await fetch('/api/catalogos/productos-fega');
      _catalogoCache = r.ok ? await r.json() : [];
    } catch (_) { _catalogoCache = []; }
    return _catalogoCache;
  }

  /* ─────────────────────────────────────────────
     Panel lateral — sección subparcelas
  ───────────────────────────────────────────── */
  async function renderPanel(subs) {
    const divSec  = $('divide-section');
    const subSec  = $('subparcelas-section');
    const listEl  = $('subparcelas-list-container');
    if (!subSec || !listEl) return;

    const hay = subs && subs.length > 0;
    if (divSec) divSec.classList.toggle('d-none', hay);
    subSec.classList.toggle('d-none', !hay);
    pintarEnMapa(subs || []);

    if (!hay) {
      listEl.innerHTML = '';
      _fusionSel.clear();
      actualizarBtnFusionar();
      return;
    }

    await getCatalogo();
    listEl.innerHTML = '';
    _fusionSel.clear();

    subs.forEach((sp, i) => {
      const col = colorDeSub(i);

      const card = document.createElement('div');
      card.className = 'card mb-2 border bg-light subparcela-card';
      card.setAttribute('data-sub-id', String(sp.id_subparcela));
      card.style.borderLeft = `5px solid ${col}`;
      card.style.cursor = 'pointer';
      if (_fusionSel.has(sp.id_subparcela)) {
        card.classList.add('border-primary');
      }

      // Clic en la tarjeta (no en checkbox/select) → resaltar en el mapa
      card.addEventListener('click', (ev) => {
        if (ev.target.closest('input, select, button, label')) return;
        seleccionarSubparcelaPanel(sp.id_subparcela);
      });

      const body = document.createElement('div');
      body.className = 'card-body py-2 px-3';

      const head = document.createElement('div');
      head.className = 'd-flex align-items-center gap-2 mb-2';

      const chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.className = 'form-check-input flex-shrink-0 mt-0';
      chk.title = 'Seleccionar para fusionar';
      chk.addEventListener('change', () => {
        if (chk.checked) {
          _fusionSel.add(sp.id_subparcela);
          card.classList.add('border-primary');
        } else {
          _fusionSel.delete(sp.id_subparcela);
          card.classList.remove('border-primary');
        }
        actualizarBtnFusionar();
      });

      const dot = document.createElement('span');
      dot.style.cssText = `display:inline-block;width:14px;height:14px;border-radius:50%;background:${col};flex-shrink:0;border:1px solid rgba(0,0,0,.2)`;

      const titleWrap = document.createElement('div');
      titleWrap.className = 'd-flex justify-content-between align-items-center flex-grow-1';
      titleWrap.innerHTML = `
        <strong class="small">${esc(sp.nombre || String(i + 1))}</strong>
        <span class="badge bg-success">${haStr(sp.superficie_ha)}</span>`;

      head.append(chk, dot, titleWrap);
      body.appendChild(head);

      // Selector cultivo (buscable)
      body.appendChild(crearSelectorCultivo(sp));
      card.appendChild(body);
      listEl.appendChild(card);
    });
    actualizarBtnFusionar();
  }

  // Texto normalizado (sin acentos, minúsculas) para el buscador
  function normTxt(s) {
    return String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  // Selector de cultivo con buscador para una subparcela guardada
  function crearSelectorCultivo(sp) {
    const wrap = document.createElement('div');
    wrap.className = 'sub-cultivo-buscable position-relative';

    const lbl = document.createElement('label');
    lbl.className = 'form-label small text-muted mb-1';
    lbl.textContent = 'Cultivo';

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-control form-control-sm';
    input.placeholder = 'Buscar cultivo…';
    input.autocomplete = 'off';

    const actual = (_catalogoCache || []).find(p => p.codigo === sp.cod_producto);
    input.value = actual ? actual.descripcion : '';

    const menu = document.createElement('div');
    menu.className = 'list-group position-absolute w-100 shadow-sm';
    menu.style.cssText = 'z-index:1050;max-height:220px;overflow-y:auto;display:none;';

    let codActual = sp.cod_producto ?? null;

    function aplicar(cod, desc) {
      input.value = desc;
      menu.style.display = 'none';
      if (cod === codActual) return;
      apiPatchCultivo(sp.id_subparcela, cod)
        .then(res => {
          if (!res || !res.ok) throw new Error(res && res.error);
          codActual = cod;
          sp.cod_producto = cod;
          notifOk('Cultivo actualizado');
        })
        .catch(e => {
          notifError((e && e.message) || 'Error al actualizar el cultivo');
          const prev = (_catalogoCache || []).find(p => p.codigo === codActual);
          input.value = prev ? prev.descripcion : '';
        });
    }

    function render(filtro) {
      const q = normTxt(filtro);
      menu.innerHTML = '';
      const items = [{ codigo: null, descripcion: '— Sin cultivo —' }, ...(_catalogoCache || [])];
      const filtrados = items.filter(p => {
        if (!q) return true;
        return normTxt(p.descripcion).includes(q) || String(p.codigo ?? '').includes(q);
      }).slice(0, 200);

      if (!filtrados.length) {
        const d = document.createElement('div');
        d.className = 'list-group-item small text-muted py-1';
        d.textContent = 'Sin resultados';
        menu.appendChild(d);
        return;
      }
      filtrados.forEach(p => {
        const it = document.createElement('button');
        it.type = 'button';
        it.className = 'list-group-item list-group-item-action small py-1';
        it.textContent = (p.codigo === null) ? p.descripcion : `${p.codigo} · ${p.descripcion}`;
        it.addEventListener('mousedown', (ev) => {
          ev.preventDefault();
          aplicar(p.codigo === null ? null : p.codigo, p.codigo === null ? '' : p.descripcion);
        });
        menu.appendChild(it);
      });
    }

    input.addEventListener('focus', () => { render(''); menu.style.display = 'block'; });
    input.addEventListener('input', () => { render(input.value); menu.style.display = 'block'; });
    input.addEventListener('keydown', (e) => { if (e.key === 'Escape') menu.style.display = 'none'; });
    document.addEventListener('click', (e) => { if (!wrap.contains(e.target)) menu.style.display = 'none'; });

    wrap.append(lbl, input, menu);
    return wrap;
  }

  function actualizarBtnFusionar() {
    const btn = $('btn-fusionar-subparcelas');
    if (btn) btn.disabled = _fusionSel.size < 2;
  }

  function actualizarBtnFusionarBorradores() {
    const btn = $('btn-fusionar-borradores');
    if (btn) btn.disabled = _borradorFusionSel.size < 2;
  }

  /* ─────────────────────────────────────────────
     Pintar subparcelas guardadas en el mapa
  ───────────────────────────────────────────── */
  const COLS = ['#e67e22','#9b59b6','#3498db','#e91e63','#00bcd4','#ff9800','#2ecc71'];

  function colorDeSub(i) {
    return COLS[i % COLS.length];
  }

  const ESTILO_NORMAL = (col) => ({
    color: col,
    weight: _isTouchUi ? 3 : 2,
    fillColor: col,
    fillOpacity: _isTouchUi ? 0.32 : 0.25,
    dashArray: '4 3',
  });
  const ESTILO_RESALTADO = (col) => ({
    color: col,
    weight: _isTouchUi ? 6 : 5,
    fillColor: col,
    fillOpacity: 0.55,
    dashArray: null,
  });

  function pintarEnMapa(subs) {
    ensureSubparcelasSavedPane();
    if (_savedLayer) { _savedLayer.clearLayers(); }
    else             { _savedLayer = L.featureGroup().addTo(map); }
    _savedLayerById.clear();
    _selectedSavedId = null;
    if (!subs.length) return;

    subs.forEach((sp, i) => {
      const col = colorDeSub(i);
      const layer = L.geoJSON(sp.geom, {
        style: ESTILO_NORMAL(col),
        pane: 'subparcelasSavedPane',
      })
        .bindTooltip(
          `<strong>${esc(sp.nombre || String(i + 1))}</strong><br>${haStr(sp.superficie_ha)}`,
          { sticky: true }
        )
        .addTo(_savedLayer);

      layer._baseColor = col;
      _savedLayerById.set(sp.id_subparcela, layer);

      layer.on('click', () => seleccionarSubparcelaPanel(sp.id_subparcela));
    });
  }

  // Resalta en el mapa la subparcela indicada (y atenúa las demás)
  function resaltarSubparcela(id) {
    _selectedSavedId = id;
    _savedLayerById.forEach((layer, sid) => {
      const col = layer._baseColor || '#90bc05';
      if (sid === id) {
        layer.setStyle(ESTILO_RESALTADO(col));
        layer.bringToFront();
      } else {
        layer.setStyle(ESTILO_NORMAL(col));
      }
    });
  }

  function quitarResaltadoSubparcela() {
    _selectedSavedId = null;
    _savedLayerById.forEach(layer => {
      const col = layer._baseColor || '#90bc05';
      layer.setStyle(ESTILO_NORMAL(col));
    });
  }

  // Selecciona desde el panel o el mapa, sincronizando ambos
  function seleccionarSubparcelaPanel(id) {
    const next = (_selectedSavedId === id) ? null : id;
    if (next === null) {
      quitarResaltadoSubparcela();
    } else {
      resaltarSubparcela(next);
    }
    // Sincronizar tarjetas del panel
    document.querySelectorAll('#subparcelas-list-container [data-sub-id]').forEach(card => {
      const cid = card.getAttribute('data-sub-id');
      card.classList.toggle('subparcela-card-activa', String(next) === cid);
    });
  }

  /* ─────────────────────────────────────────────
     Punto de entrada público — llamado desde renderSidePanelFromProps
  ───────────────────────────────────────────── */
  async function renderSubparcelasForRecinto(recintoId) {
    _recintoId = recintoId;
    if (_enModoEdicion) cerrarEdicion();
    if (_savedLayer) _savedLayer.clearLayers();

    if (!recintoId) {
      $('subparcelas-section')?.classList.add('d-none');
      $('divide-section')?.classList.remove('d-none');
      return;
    }
    try {
      const subs = await apiGet(recintoId);
      await renderPanel(subs);
    } catch (e) {
      console.error('[subparcelas] Error cargando:', e);
    }
  }
  window.renderSubparcelasForRecinto = renderSubparcelasForRecinto;

  /* ─────────────────────────────────────────────
     MODO EDICIÓN — abrir
  ───────────────────────────────────────────── */
  async function abrirEdicion(borradoresIniciales) {
    if (_enModoEdicion) return;

    // Obtener geometría del recinto
    _recintoFeature = await ensureRecintoFeature(_recintoId);
    if (!_recintoFeature) {
      notifError('No se pudo obtener la geometría del recinto. Cierra el panel y vuelve a abrirlo.');
      return;
    }
    // Asegurar Feature simple (no FeatureCollection)
    if (_recintoFeature.type !== 'Feature') {
      _recintoFeature = { type: 'Feature', geometry: _recintoFeature, properties: {} };
    }
    // OJO: NO colapsar MultiPolygon a su parte mayor; se perdería superficie.
    // Se conserva la geometría completa (Polygon o MultiPolygon) para máscara,
    // captura de clics y validación; las partes se gestionan como piezas.

    _enModoEdicion = true;
    _editOpenedAt  = Date.now();   // debounce inicial — ignora tap residual
    _borradores    = borradoresIniciales || [];
    _habiaSubparcelas = !!(borradoresIniciales && borradoresIniciales.length > 0);

    // Partes del recinto (1 si es Polygon simple, varias si es MultiPolygon).
    const _parts = polygonPartsOf(_recintoFeature);
    if (_parts.length === 1) {
      // Una sola parte → trabajar con un Polygon simple (división/recorte directos)
      _recintoFeature = _parts[0];
    } else if (_parts.length > 1 && !_borradores.length) {
      // Varias partes y división NUEVA → una pieza por parte para que las
      // subparcelas cubran TODO el recinto (si no, solo se dividiría la mayor).
      _borradores = _parts.map((p, i) => createBorrador(p, String(i + 1)));
    }

    // Deshabilitar interacción con recintos (mismo patrón visor-dibujos.js)
    toggleInteraccionRecintos(false);

    // Capas de dibujo
    ensureSubparcelasDraftPane();
    if (_drawnLayer) { _drawnLayer.clearLayers(); map.removeLayer(_drawnLayer); }
    if (_linesLayer) { _linesLayer.clearLayers(); map.removeLayer(_linesLayer); }
    _drawnLayer = new L.FeatureGroup();
    _linesLayer = new L.FeatureGroup();
    map.addLayer(_drawnLayer);
    map.addLayer(_linesLayer);

    // Pre-cargar borradores existentes en la capa
    _borradores.forEach(b => {
      if (b.mapLayer) b.mapLayer.eachLayer(l => _drawnLayer.addLayer(l));
    });

    // Esconder subparcelas guardadas
    if (_savedLayer) _savedLayer.clearLayers();

    // Máscara visual + limitar mapa al recinto
    mostrarMascara(_recintoFeature);
    restrictMapToRecinto();
    activarCapaCapturaEdicion();

    // Cerrar cualquier popup abierto
    map.closePopup();

    ensureSubparcelasDraftPane();
    repintarBorradoresEnMapa();

    // Mostrar overlay en el panel (patrón igual que cultivos/operaciones)
    openOverlay();

    // En móvil el mapa debe quedar visible: panel oculto hasta que el usuario lo pida
    if (_isTouchUi) {
      document.body.classList.remove('subparcelas-panel-visible');
    }

    // Forzar invalidateSize síncrono: el CSS (bottom:72px) ya se aplicó con openOverlay
    try { map.invalidateSize({ animate: false }); } catch (_) {}

    // Ajustar mapa al recinto o a los borradores ya existentes
    vistaPreviewMapa({ silent: true, fallbackRecinto: true });

    actualizarBorradores();
    actualizarBtnGuardar();

    if (_isTouchUi) {
      if (_borradores.length >= 2) {
        // Ya hay cortes: mostrar y dejar que el usuario decida si añade más
        setHintDibujo('Revisa el mapa. Pulsa «Trazar» para más cortes o «Guardar».');
      } else {
        // Primera vez: activar dibujo automáticamente
        setHintDibujo('Toca el mapa en dos puntos para trazar la línea de corte.');
        activarDraw();
      }
    } else if (!_borradores.length) {
      activarDraw();
    }
  }

  /* ─────────────────────────────────────────────
     MODO EDICIÓN — cerrar
  ───────────────────────────────────────────── */
  function cerrarEdicion() {
    _enModoEdicion = false;
    pararDraw();
    quitarCapaCapturaEdicion();
    toggleInteraccionRecintos(true);
    quitarMascara();
    restoreMapBounds();
    _borradorFusionSel.clear();

    if (_drawnLayer) {
      _drawnLayer.clearLayers();
      map.removeLayer(_drawnLayer);
      _drawnLayer = null;
    }
    if (_linesLayer) {
      _linesLayer.clearLayers();
      map.removeLayer(_linesLayer);
      _linesLayer = null;
    }
    _borradores = [];

    closeOverlay();

    setTimeout(() => { try { map.invalidateSize(); } catch (_) {} }, 280);
    const borradoresEl = $('subparcelas-borradores');
    if (borradoresEl) borradoresEl.innerHTML = '';
  }

  function closeSubparcelasEdicion() {
    if (!_enModoEdicion) return;
    cerrarEdicion();
    if (_recintoId) {
      apiGet(_recintoId).then(subs => {
        renderPanel(subs);
        pintarEnMapa(subs);
      }).catch(() => {});
    }
  }
  window.closeSubparcelasEdicion = closeSubparcelasEdicion;

  /* ─────────────────────────────────────────────
     Dibujo de línea por 2 clics (sin doble clic)
     1er clic = inicio · mover ratón = previsualiza · 2º clic = fin
     Esc o botón derecho = cancelar la línea en curso
  ───────────────────────────────────────────── */
  function setEstadoBotonDibujo(activo) {
    const btn = $('btn-agregar-subparcela');
    if (btn) {
      btn.classList.toggle('active', activo);
      btn.innerHTML = activo
        ? '<i class="fa-solid fa-xmark me-1"></i> Cancelar trazado'
        : '<i class="fa-solid fa-slash me-1"></i> Dibujar línea divisoria';
    }
    // Botón "Trazar" en la barra móvil
    const btnM = $('btn-mobile-dibujar');
    if (btnM) {
      btnM.classList.toggle('btn-danger',  activo);
      btnM.classList.toggle('btn-warning', !activo);
      btnM.innerHTML = activo
        ? '<i class="fa-solid fa-xmark me-1"></i>Cancelar'
        : '<i class="fa-solid fa-slash me-1"></i>Trazar';
    }
  }

  function setHintDibujo(txt) {
    const hint = $('guardar-division-hint');
    if (hint && txt != null) hint.textContent = txt;
    const mobileHint = $('subparcelas-mobile-hint');
    if (mobileHint && txt != null) mobileHint.textContent = txt;
  }

  function activarDraw() {
    if (_dibujando) { pararDraw(); return; }

    _dibujando = true;
    _lineStart = null;
    setEstadoBotonDibujo(true);
    setHintDibujo(_isTouchUi
      ? 'Toca el mapa en dos puntos para trazar la línea divisoria.'
      : 'Haz clic en un punto y luego en otro para trazar la línea.');
    document.body.classList.add('subparcelas-drawing');
    document.body.classList.remove('subparcelas-panel-visible');
    lockMobileDrawScroll(true);

    // Notificar a Leaflet del nuevo tamaño del mapa (el CSS bottom:72px ya se aplicó)
    try { map.invalidateSize({ animate: false }); } catch (_) {}
    try { map.getContainer().style.cursor = 'crosshair'; } catch (_) {}
    try { if (map.doubleClickZoom?.disable) map.doubleClickZoom.disable(); } catch (_) {}

    _drawKeyHandler = (e) => { if (e.key === 'Escape') cancelarLineaEnCurso(); };
    document.addEventListener('keydown', _drawKeyHandler);

    if (_isTouchUi) {
      // Móvil: listener a nivel document (capture) — el más fiable, sin conflictos con Leaflet
      try {
        _savedMapDragging = map.dragging.enabled();
        map.dragging.disable();
      } catch (_) {}
      try {
        if (map.touchZoom?.disable) {
          _savedTouchZoom = map.touchZoom.enabled();
          map.touchZoom.disable();
        }
      } catch (_) {}

      _docTouchEndHandler = _crearDocTouchHandler();
      _drawTouchMoveHandler = _crearDocTouchMoveHandler();
      document.addEventListener('touchend',  _docTouchEndHandler,   { capture: true, passive: false });
      document.addEventListener('touchmove', _drawTouchMoveHandler, { passive: true });
    } else {
      // Desktop: usar map.on('click') estándar de Leaflet
      _drawMoveHandler = (e) => onDrawMove(e);
      map.on('mousemove',  _drawMoveHandler);
      map.on('click',      onDrawClick);
      map.on('contextmenu', cancelarLineaEnCurso);
    }

    setSavedPaneInteractive(false);
    setTimeout(() => { try { map.invalidateSize(); } catch (_) {} }, 200);
  }

  function pararDraw() {
    _dibujando = false;
    document.body.classList.remove('subparcelas-drawing');
    document.body.classList.remove('subparcelas-panel-visible');
    lockMobileDrawScroll(false);
    cancelarLineaEnCurso();

    if (_drawKeyHandler) { document.removeEventListener('keydown', _drawKeyHandler); _drawKeyHandler = null; }

    if (_isTouchUi) {
      if (_docTouchEndHandler)   { document.removeEventListener('touchend',  _docTouchEndHandler,   { capture: true }); _docTouchEndHandler = null; }
      if (_drawTouchMoveHandler) { document.removeEventListener('touchmove', _drawTouchMoveHandler); _drawTouchMoveHandler = null; }
      try { if (_savedMapDragging) map.dragging.enable(); } catch (_) {}
      try { if (_savedTouchZoom && map.touchZoom?.enable) map.touchZoom.enable(); } catch (_) {}
    } else {
      if (_drawMoveHandler) { map.off('mousemove', _drawMoveHandler); _drawMoveHandler = null; }
      map.off('click',      onDrawClick);
      map.off('contextmenu', cancelarLineaEnCurso);
    }

    try { map.getContainer().style.cursor = ''; } catch (_) {}
    try { if (map.doubleClickZoom?.enable) map.doubleClickZoom.enable(); } catch (_) {}
    setEstadoBotonDibujo(false);
    setSavedPaneInteractive(true);
  }

  function cancelarLineaEnCurso() {
    _lineStart = null;
    if (_previewLine)       { map.removeLayer(_previewLine);       _previewLine = null; }
    if (_firstPointMarker)  { map.removeLayer(_firstPointMarker);  _firstPointMarker = null; }
  }

  function onDrawMove(e) {
    if (!_dibujando || !_lineStart) return;
    const latlngs = [_lineStart, e.latlng];
    if (_previewLine) {
      _previewLine.setLatLngs(latlngs);
    } else {
      ensureSubparcelasDraftPane();
      _previewLine = L.polyline(latlngs, {
        color: '#dc3545', weight: 3, dashArray: '8 6', interactive: false,
        pane: 'subparcelasDraftPane',
      }).addTo(map);
    }
  }

  function onDrawClick(e) {
    if (!_dibujando) return;
    const { lat, lng } = e.latlng;

    // Ignorar puntos fuera del recinto
    if (!puntoDentroRecinto(lng, lat)) {
      const now = Date.now();
      if (now - _ultimoAvisoFuera > 1500) {
        _ultimoAvisoFuera = now;
        notifError(_isTouchUi ? 'Toca dentro del recinto.' : 'Haz clic dentro del recinto.');
      }
      return;
    }

    // Primer punto
    if (!_lineStart) {
      _lineStart = e.latlng;
      // En móvil, mostrar un marcador visible en el primer punto (no hay cursor)
      if (_isTouchUi) {
        ensureSubparcelasDraftPane();
        if (_firstPointMarker) { map.removeLayer(_firstPointMarker); }
        _firstPointMarker = L.circleMarker(e.latlng, {
          radius: 9, color: '#fff', weight: 2,
          fillColor: '#dc3545', fillOpacity: 1,
          interactive: false, pane: 'subparcelasDraftPane',
        }).addTo(map);
      }
      setHintDibujo(_isTouchUi
        ? 'Primer punto fijado. Ahora toca el segundo punto para trazar la línea.'
        : 'Ahora haz clic en el segundo punto para cerrar la línea.');
      return;
    }

    // Segundo punto → construir línea y dividir
    const start = _lineStart;
    const end = e.latlng;
    cancelarLineaEnCurso();

    if (start.distanceTo(end) < 0.5) {
      notifError('Los dos puntos están demasiado juntos. Traza una línea más larga.');
      return;
    }

    const lineFeature = turf.lineString([[start.lng, start.lat], [end.lng, end.lat]]);

    const ok = aplicarDivisionPorLinea(lineFeature);
    if (!ok) {
      notifError('La línea no divide el recinto. Traza una línea que cruce la parcela de lado a lado.');
      return;
    }

    pintarLineaDivisoria(lineFeature);
    repintarBorradoresEnMapa();
    actualizarBorradores();
    actualizarBtnGuardar();
    pararDraw();   // se detiene tras trazar; el usuario pulsa "Trazar" de nuevo para otro corte
    try { map.invalidateSize({ animate: false }); } catch (_) {}
    vistaPreviewMapa({ silent: true });
    setHintDibujo(_isTouchUi
      ? `${_borradores.length} zonas creadas. Pulsa «Trazar» para más cortes o «Guardar» para confirmar.`
      : 'Recinto dividido. Pulsa «Dibujar línea divisoria» para más cortes o «Guardar» para confirmar.');
    notifOk('División aplicada en el mapa. Revisa el resultado y pulsa Guardar para confirmar.');
  }

  /* ─────────────────────────────────────────────
     Lista de borradores en el overlay
  ───────────────────────────────────────────── */
  function actualizarBorradores() {
    const c = $('subparcelas-borradores');
    if (!c) return;
    c.innerHTML = '';

    if (!_borradores.length) {
      c.innerHTML = '<p class="text-muted small text-center py-2 mb-0">Dibuja una línea para dividir el recinto.</p>';
      return;
    }

    _borradores.forEach((b, i) => {
      const row = document.createElement('div');
      row.className = 'd-flex align-items-center gap-2 mb-2 p-2 rounded bg-light border';
      if (_borradorFusionSel.has(i)) row.classList.add('border-primary');

      const col = COLS[i % COLS.length];

      const chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.className = 'form-check-input flex-shrink-0 mt-0';
      chk.title = 'Seleccionar para fusionar';
      chk.checked = _borradorFusionSel.has(i);
      chk.addEventListener('change', () => {
        if (chk.checked) _borradorFusionSel.add(i);
        else _borradorFusionSel.delete(i);
        row.classList.toggle('border-primary', chk.checked);
        actualizarBtnFusionarBorradores();
      });

      const dot = document.createElement('span');
      dot.style.cssText = `display:inline-block;width:10px;height:10px;border-radius:50%;background:${col};flex-shrink:0`;

      const inp = document.createElement('input');
      inp.type  = 'text';
      inp.className = 'form-control form-control-sm flex-grow-1';
      inp.value = b.nombre;
      inp.addEventListener('change', () => {
        _borradores[i].nombre = inp.value.trim() || String(i + 1);
      });

      const badge = document.createElement('span');
      badge.className = 'badge bg-success text-nowrap';
      badge.textContent = haStr(b.ha);

      const btnDel = document.createElement('button');
      btnDel.className = 'btn btn-sm btn-outline-danger flex-shrink-0';
      btnDel.title = 'Quitar este corte (se une a la zona vecina)';
      btnDel.innerHTML = '<i class="bi bi-trash"></i>';
      btnDel.addEventListener('click', () => eliminarBorrador(i));

      // Color del polígono en el mapa: actualizar al color de lista
      if (b.mapLayer) {
        b.mapLayer.setStyle({ color: col, fillColor: col });
      }

      row.append(chk, dot, inp, badge, btnDel);
      c.appendChild(row);
    });
    actualizarBtnFusionarBorradores();
  }

  function actualizarBtnGuardar() {
    const btn  = $('btn-guardar-division');
    const btnMobile = $('btn-mobile-guardar-division');
    const hint = $('guardar-division-hint');
    if (!btn) return;

    const tieneDivision = _borradores.length >= 2;
    const puedeGuardar = tieneDivision || _habiaSubparcelas;
    btn.disabled = !puedeGuardar;
    if (btnMobile) btnMobile.disabled = !puedeGuardar;

    if (hint) {
      if (tieneDivision) {
        hint.textContent = '';
      } else if (_habiaSubparcelas) {
        hint.textContent = 'Al guardar, el recinto quedará sin división.';
      } else {
        hint.textContent = `Dibuja líneas para dividir el recinto (tienes ${_borradores.length}).`;
      }
    }
  }

  /* ─────────────────────────────────────────────
     Guardar división
  ───────────────────────────────────────────── */
  async function guardar() {
    if (!_recintoId) return;
    const btn = $('btn-guardar-division');
    if (btn) btn.disabled = true;

    try {
      let res;
      if (_borradores.length >= 2) {
        const features = _borradores.map(b => ({
          type: 'Feature',
          geometry: b.feature.geometry,
          properties: { nombre: b.nombre },
        }));
        res = await apiPost(_recintoId, features);
        if (!res.ok) throw new Error(res.error);
        notifOk('División guardada correctamente');
      } else {
        // 0 o 1 piezas → el recinto queda sin división: borrar todas
        res = await apiDelete(_recintoId);
        if (!res.ok) throw new Error(res.error);
        notifOk('Se ha eliminado la división del recinto');
      }
      cerrarEdicion();
      await renderSubparcelasForRecinto(_recintoId);
      setTimeout(() => vistaPreviewMapa({ silent: true }), 400);
    } catch (e) {
      notifError(e.message || 'No se pudo guardar');
      if (btn) btn.disabled = false;
    }
  }

  /* ─────────────────────────────────────────────
     Fusionar subparcelas guardadas
  ───────────────────────────────────────────── */
  async function fusionarGuardadas() {
    if (!_recintoId || _fusionSel.size < 2) return;

    const ok = await AppConfirm.open({
      title: '¿Fusionar subparcelas?',
      message: 'Las subparcelas seleccionadas se unirán en una sola zona.',
      okText: 'Fusionar',
      cancelText: 'Cancelar',
      okClass: 'btn-primary',
    });
    if (!ok) return;

    const btn = $('btn-fusionar-subparcelas');
    if (btn) btn.disabled = true;

    try {
      const subs = await apiGet(_recintoId);
      const selected = subs.filter(s => _fusionSel.has(s.id_subparcela));
      const rest = subs.filter(s => !_fusionSel.has(s.id_subparcela));

      const feats = selected.map(s => ({ type: 'Feature', geometry: s.geom, properties: {} }));
      const unionFeat = unionPolygonFeatures(feats);
      if (!unionFeat) {
        throw new Error('Solo puedes fusionar subparcelas que estén juntas (que compartan un borde).');
      }

      const nombres = selected.map(s => s.nombre).filter(Boolean);
      const nombreFusion = nombres.length ? nombres.join(' + ') : 'Subparcela fusionada';

      const features = [
        ...rest.map(s => ({
          type: 'Feature',
          geometry: s.geom,
          properties: { nombre: s.nombre },
        })),
        {
          type: 'Feature',
          geometry: unionFeat.geometry,
          properties: { nombre: nombreFusion },
        },
      ];

      const res = await apiPost(_recintoId, features);
      if (!res.ok) throw new Error(res.error);
      notifOk('Subparcelas fusionadas correctamente');
      _fusionSel.clear();
      await renderSubparcelasForRecinto(_recintoId);
    } catch (e) {
      notifError(e.message || 'No se pudo fusionar');
      actualizarBtnFusionar();
    }
  }

  function fusionarBorradoresSeleccionados() {
    if (_borradorFusionSel.size < 2) return;
    const ok = fusionarBorradoresPorIndices([..._borradorFusionSel]);
    if (ok) {
      notifOk('Subparcelas fusionadas');
      actualizarBorradores();
      actualizarBtnGuardar();
      actualizarBtnFusionarBorradores();
    }
  }

  /* ─────────────────────────────────────────────
     Listeners de botones
  ───────────────────────────────────────────── */
  // Iniciar división (desde la sección "Dividir recinto")
  $('btn-iniciar-division')?.addEventListener('click', () => abrirEdicion([]));

  // Modificar división existente
  $('btn-editar-division')?.addEventListener('click', async () => {
    const subs = await apiGet(_recintoId);
    const bors = subs.map((sp, i) => {
      const feat = { type: 'Feature', geometry: sp.geom, properties: {} };
      const ml   = L.geoJSON(feat, {
        pane: 'subparcelasDraftPane',
        style: { color: COLS[i % COLS.length], weight: 2,
                 fillColor: COLS[i % COLS.length], fillOpacity: 0.45 },
      });
      return { nombre: sp.nombre || String(i + 1),
               ha: parseFloat(sp.superficie_ha), feature: feat, mapLayer: ml };
    });
    abrirEdicion(bors);
  });

  // Dibujar nueva subparcela
  $('btn-agregar-subparcela')?.addEventListener('click', () => activarDraw());

  // Cancelar edición
  $('btn-cancelar-division')?.addEventListener('click', async () => {
    cerrarEdicion();
    const subs = await apiGet(_recintoId);
    await renderPanel(subs);
    pintarEnMapa(subs);
  });

  // Guardar división
  $('btn-guardar-division')?.addEventListener('click', () => guardar());
  $('btn-mobile-guardar-division')?.addEventListener('click', () => guardar());

  // Salir del editor completo (botón ✕ de la barra)
  $('btn-mobile-cancelar-trazado')?.addEventListener('click', async () => {
    cerrarEdicion();
    const subs = await apiGet(_recintoId);
    await renderPanel(subs);
    pintarEnMapa(subs);
  });

  // Toggle dibujo desde la barra móvil
  $('btn-mobile-dibujar')?.addEventListener('click', () => activarDraw());

  $('btn-mobile-ver-panel')?.addEventListener('click', () => {
    document.body.classList.toggle('subparcelas-panel-visible');
    setTimeout(() => { try { map.invalidateSize(); } catch (_) {} }, 280);
  });

  function vistaPreviewMapa(opts = {}) {
    const { silent = false, fallbackRecinto = false } = opts;
    try {
      const layers = [];
      if (_enModoEdicion && _drawnLayer) {
        _drawnLayer.eachLayer(l => layers.push(l));
      }
      if (_savedLayer) {
        _savedLayer.eachLayer(l => layers.push(l));
      }

      if (layers.length) {
        const b = L.featureGroup(layers).getBounds();
        if (b?.isValid?.()) {
          map.fitBounds(b.pad(0.08), { padding: [24, 24], maxZoom: 18, animate: true, duration: 0.35 });
          return true;
        }
      }

      if (fallbackRecinto && _recintoFeature) {
        const b = L.geoJSON(_recintoFeature).getBounds();
        if (b?.isValid?.()) {
          map.fitBounds(b.pad(0.06), { padding: [40, 40], maxZoom: 17, animate: true, duration: 0.35 });
          return true;
        }
      }

      if (!silent) notifError('No hay subparcelas visibles en el mapa.');
      return false;
    } catch (_) {
      if (!silent) notifError('No se pudo centrar el mapa en las subparcelas.');
      return false;
    }
  }

  // btn-vista-subparcelas y btn-overlay-vista-mapa eliminados del HTML

  // Fusionar subparcelas guardadas
  $('btn-fusionar-subparcelas')?.addEventListener('click', () => fusionarGuardadas());

  // Fusionar borradores en modo edición
  $('btn-fusionar-borradores')?.addEventListener('click', () => fusionarBorradoresSeleccionados());

}); // fin DOMContentLoaded