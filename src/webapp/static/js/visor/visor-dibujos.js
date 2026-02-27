document.addEventListener('DOMContentLoaded', function () {

  const editarBtn = document.getElementById('editar-btn');
  const dibujarBtn = document.getElementById('dibujar-btn');
  const poligonoBtn = document.getElementById('poligono-btn');
  const aceptarBtn = document.getElementById('aceptar-btn');
  const cancelarBtn = document.getElementById('cancelar-btn');
  const limpiarBtn = document.getElementById('limpiar-btn');

  // FeatureGroup para guardar los elementos dibujados
  const drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);

 let rectangleDrawer = null;
  let polygonDrawer = null;
  let dibujosTemporales = [];

  // Función para deshabilitar/habilitar interacción con recintos durante el dibujo.
  // Usar pointer-events: none en los panes garantiza que Leaflet.Draw recibe
  // todos los clicks del mapa sin que los polígonos de recintos los intercepten.
  function toggleInteraccionRecintos(enabled) {
    const sigpacP = map.getPane('sigpacPane');
    const misP    = map.getPane('misPane');

    if (enabled) {
      // Restaurar z-index originales
      if (sigpacP) sigpacP.style.zIndex = '700';
      if (misP)    misP.style.zIndex    = '800';
      // Restaurar popups de recintos SIGPAC
      recintosLayer.eachLayer(layer => {
        if (layer._popup) layer.bindPopup(layer._popup);
      });
    } else {
      // Bajar z-index por debajo del overlayPane de Leaflet.Draw (400)
      // para que los paths SVG no intercepten los clicks del dibujador
      if (sigpacP) sigpacP.style.zIndex = '200';
      if (misP)    misP.style.zIndex    = '200';
      // Desactivar popups de recintos SIGPAC
      recintosLayer.eachLayer(layer => layer.unbindPopup());
    }
  }

  // Al hacer clic en editar
  editarBtn.addEventListener('click', () => {
    editarBtn.classList.add('hidden');
    dibujarBtn.classList.remove('hidden');
    poligonoBtn.classList.remove('hidden');
    aceptarBtn.classList.remove('hidden');
    cancelarBtn.classList.remove('hidden');
    limpiarBtn.classList.remove('hidden');

    // Activar modo edición y deshabilitar interacción con recintos
    modoEdicion = true;
    toggleInteraccionRecintos(false);

    // Guardar estado actual
    dibujosTemporales = [];
    drawnItems.eachLayer(layer => {
      dibujosTemporales.push(layer);
    });

    console.log('Modo edición activado');
  });

  // Al hacer clic en dibujar rectángulo
  dibujarBtn.addEventListener('click', () => {
    // Desactivar polígono si está activo
    if (polygonDrawer) {
      polygonDrawer.disable();
      polygonDrawer = null;
    }

    // Crear y activar el dibujador de rectángulos
    L.drawLocal = L.drawLocal || {};
    L.drawLocal.draw = L.drawLocal.draw || {};
    L.drawLocal.draw.handlers = L.drawLocal.draw.handlers || {};

    L.drawLocal.draw.handlers.rectangle = {
      tooltip: {
        start: 'Haz clic y arrastra para dibujar un rectángulo'
      },
      shapeOptions: {
        color: '#3388ff'  // opcional, el color del rectángulo
      }
    };

    // Ahora sí inicializamos el drawer
    rectangleDrawer = new L.Draw.Rectangle(map);
    rectangleDrawer.enable();

    console.log('Modo dibujo de rectángulo activado');
  });

  // Al hacer clic en dibujar polígono
  poligonoBtn.addEventListener('click', () => {
    // Desactivar rectángulo si está activo
    if (rectangleDrawer) {
      rectangleDrawer.disable();
      rectangleDrawer = null;
    }

    // Crear y activar el dibujador de polígonos
    // Configurar mensajes en español para polígonos
    L.drawLocal = L.drawLocal || {};
    L.drawLocal.draw = L.drawLocal.draw || {};
    L.drawLocal.draw.handlers = L.drawLocal.draw.handlers || {};

    L.drawLocal.draw.handlers.polygon = {
      tooltip: {
        start: 'Haz clic para empezar a dibujar el polígono',   
        cont: 'Haz clic para continuar el polígono',          
        end: 'Haz clic en el primer punto para cerrar el polígono' 
      },
      shapeOptions: {
        color: '#3388ff' // opcional: color del polígono
      }
    };

    // Ahora inicializamos el drawer del polígono
    polygonDrawer = new L.Draw.Polygon(map);
    polygonDrawer.enable();


    console.log('Modo dibujo de polígono activado - Haz clic para añadir puntos, doble clic para terminar');
  });

  // Evento cuando se completa el dibujo
  map.on(L.Draw.Event.CREATED, (e) => {
    const layer = e.layer;
    drawnItems.addLayer(layer);
    console.log('Forma dibujada:', layer);
  });

  // Al hacer clic en aceptar
 // Al hacer clic en aceptar
  aceptarBtn.addEventListener('click', async () => {
    // Obtener todos los dibujos actuales
    const dibujos = [];
    
    drawnItems.eachLayer((layer) => {
      const geoJSON = layer.toGeoJSON();
      const tipo = layer instanceof L.Rectangle ? 'rectangulo' : 'poligono';
      
      dibujos.push({
        geojson: geoJSON,
        tipo: tipo
      });
    });

    // Si hay dibujos, enviarlos al backend
    if (dibujos.length > 0) {
  try {
    const response = await fetch('/api/guardar-dibujos', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ dibujos: dibujos })
    });

    const data = await response.json();

    if (!response.ok) {
      NotificationSystem.show({
        type: "error",
        title: "No se pudo guardar",
        message: data.error || "Ocurrió un error al guardar los dibujos"
      });
      return;
    }

    // ✅ Mostrar éxito
    NotificationSystem.show({
      type: "success",
      title: "Dibujo guardado",
      message: data.message || "Dibujo/s creado/s correctamente"
    });

  } catch (error) {
    console.error('Error en la petición:', error);
    NotificationSystem.show({
      type: "error",
      title: "Error de conexión",
      message: "No se pudo conectar con el servidor"
    });
  }
}




    // Continúa con el código original
    dibujarBtn.classList.add('hidden');
    poligonoBtn.classList.add('hidden');
    aceptarBtn.classList.add('hidden');
    cancelarBtn.classList.add('hidden');
    limpiarBtn.classList.add('hidden');
    editarBtn.classList.remove('hidden');

    modoEdicion = false;
    toggleInteraccionRecintos(true);

    if (rectangleDrawer) {
      rectangleDrawer.disable();
      rectangleDrawer = null;
    }
    if (polygonDrawer) {
      polygonDrawer.disable();
      polygonDrawer = null;
    }

    console.log('Cambios guardados');
  });


  // Al hacer clic en cancelar
  cancelarBtn.addEventListener('click', () => {
    dibujarBtn.classList.add('hidden');
    poligonoBtn.classList.add('hidden');
    aceptarBtn.classList.add('hidden');
    cancelarBtn.classList.add('hidden');
    limpiarBtn.classList.add('hidden');
    editarBtn.classList.remove('hidden');

    // Desactivar modo edición y reactivar interacción
    modoEdicion = false;
    toggleInteraccionRecintos(true);

    // Desactiva ambos modos de dibujo
    if (rectangleDrawer) {
      rectangleDrawer.disable();
      rectangleDrawer = null;
    }
    if (polygonDrawer) {
      polygonDrawer.disable();
      polygonDrawer = null;
    }

    // Restaurar estado anterior (eliminar dibujos nuevos)
    drawnItems.clearLayers();
    dibujosTemporales.forEach(layer => {
      drawnItems.addLayer(layer);
    });

    console.log('Edición cancelada');
  });

  // Al hacer clic en limpiar
  limpiarBtn.addEventListener('click', () => {
    // Eliminar todos los dibujos
    drawnItems.clearLayers();
  });
 

const dibujosToggle = document.getElementById('dibujos-toggle');
const dibujosPanel = document.getElementById('dibujos-panel');
const dibujosList = document.getElementById('dibujos-list');
const dibujosCount = document.getElementById('dibujos-count');
const refrescarDibujosBtn = document.getElementById('refrescar-dibujos');

// FeatureGroup para los dibujos guardados
const dibujosGuardadosLayer = new L.FeatureGroup();
map.addLayer(dibujosGuardadosLayer);

// Toggle panel
dibujosToggle.addEventListener('click', () => {
  dibujosPanel.classList.toggle('hidden');
});



// Función para formatear fecha
function formatearFechaDibujo(fechaISO) {
  const fecha = new Date(fechaISO);
  const ahora = new Date();
  const diff = ahora - fecha;
  const dias = Math.floor(diff / (1000 * 60 * 60 * 24));
  
  if (dias === 0) return 'Hoy';
  if (dias === 1) return 'Ayer';
  if (dias < 7) return `Hace ${dias} días`;
  
  return fecha.toLocaleDateString('es-ES', { 
    day: '2-digit', 
    month: '2-digit', 
    year: 'numeric' 
  });
}

let dibujoVisibleId = null;

// Función para cargar dibujos guardados
async function cargarDibujosGuardados() {
  try {
    const response = await fetch('/api/obtener-dibujos');
    const data = await response.json();
    
    if (!response.ok) {
      console.error('Error al obtener dibujos:', data.error);
      return;
    }
    
    const dibujos = data.dibujos || [];
    
    // Actualizar contador
    dibujosCount.textContent = dibujos.length;
    dibujosCount.style.display = dibujos.length > 0 ? 'block' : 'none';
    
    // Limpiar lista y capa
    dibujosList.innerHTML = '';
    dibujosGuardadosLayer.clearLayers();
    dibujoVisibleId = null;
    
    if (dibujos.length === 0) {
      dibujosList.innerHTML = `
        <div class="dibujos-empty">
          <i class="bi bi-bookmark" style="font-size:48px;opacity:0.3;"></i>
          <p style="margin:16px 0 0 0;font-size:14px;">No hay dibujos guardados</p>
        </div>
      `;
      return;
    }
    
    // Header con botón mostrar/ocultar todos
    const headerActions = document.createElement('div');
    headerActions.className = 'dibujos-list-header';
    headerActions.innerHTML = `
      <button class="dibujo-btn-toggle-all" id="toggle-all-dibujos">
        <i class="bi bi-eye-fill"></i> Mostrar todos
      </button>
    `;
    dibujosList.appendChild(headerActions);
    
    let todosVisibles = false;
    
    // Renderizar cada dibujo
    dibujos.forEach((dibujo, index) => {
      const geojson = typeof dibujo.geojson === 'string' 
        ? JSON.parse(dibujo.geojson) 
        : dibujo.geojson;
      
      const item = document.createElement('div');
      item.className = 'dibujo-item';
      item.dataset.dibujoId = dibujo.id;
      
      const colors = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A',
        '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2',
        '#F8B739', '#52B788', '#EF476F', '#06D6A0', 
        '#118AB2', '#FFD166', '#8338EC', '#3A86FF', 
        '#FFBE0B', '#FB5607', '#2EC4B6', '#90DBF4'
      ];

      const color = colors[index % colors.length];
      
      item.innerHTML = `
        <div class="dibujo-content">
          <div class="dibujo-color" style="background-color: ${color};"></div>
          
          <div class="dibujo-info">
            <div class="dibujo-ndvi-compact">
              <div class="ndvi-compact-item">
                <span class="ndvi-label">Máx</span>
                <span class="ndvi-value">${dibujo.ndvi_max?.toFixed(2) || '-'}</span>
              </div>
              <div class="ndvi-compact-item">
                <span class="ndvi-label">Min</span>
                <span class="ndvi-value">${dibujo.ndvi_min?.toFixed(2) || '-'}</span>
              </div>
              <div class="ndvi-compact-item">
                <span class="ndvi-label">Med</span>
                <span class="ndvi-value">${dibujo.ndvi_medio?.toFixed(2) || '-'}</span>
              </div>
            </div>
            
            ${dibujo.area_m2 ? `
              <div class="dibujo-area">
                ${(dibujo.area_m2 / 10000).toFixed(2)} ha
              </div>
            ` : ''}
          </div>
          
          <div class="dibujo-actions-compact">
            <button class="dibujo-btn-icon delete-btn" data-id="${dibujo.id}" title="Eliminar">
              <i class="bi bi-trash-fill"></i>
            </button>
          </div>
        </div>
      `;
      
      dibujosList.appendChild(item);
      
      // Añadir geometría al mapa con el color correspondiente
      const layer = L.geoJSON(geojson, {
        style: {
          color: color,
          weight: 5,
          opacity: 0,
          fillColor: color,
          fillOpacity: 0
        },
        // CRÍTICO: Evitar que los eventos se propaguen a capas inferiores
        bubblingMouseEvents: false,
        pane: 'highlightPane', // Usar el pane de mayor z-index
        interactive: false // Inicialmente no interactivo porque está oculto
      });
      
      layer.dibujoId = dibujo.id;
      layer.dibujoColor = color;
      layer.colorOriginal = color;
      
      // Crear contenido del popup COMPACTO
      const popupContent = `
        <div style="font-family: inherit; min-width: 180px;">
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 2px solid ${color};">
            <div style="width: 4px; height: 20px; background: ${color}; border-radius: 2px;"></div>
            <h6 style="margin: 0; font-size: 13px; font-weight: 700; color: #333;">Consulta</h6>
          </div>
          
          <div style="display: flex; gap: 8px; margin-bottom: 6px;">
            <div style="flex: 1; background: #f8f9fa; padding: 6px; border-radius: 6px; text-align: center;">
              <div style="font-size: 9px; color: #666; font-weight: 600;">MAX</div>
              <div style="font-size: 14px; font-weight: 700; color: #198754;">${dibujo.ndvi_max?.toFixed(2) || '-'}</div>
            </div>
            <div style="flex: 1; background: #f8f9fa; padding: 6px; border-radius: 6px; text-align: center;">
              <div style="font-size: 9px; color: #666; font-weight: 600;">MIN</div>
              <div style="font-size: 14px; font-weight: 700; color: #198754;">${dibujo.ndvi_min?.toFixed(2) || '-'}</div>
            </div>
            <div style="flex: 1; background: #f8f9fa; padding: 6px; border-radius: 6px; text-align: center;">
              <div style="font-size: 9px; color: #666; font-weight: 600;">MED</div>
              <div style="font-size: 14px; font-weight: 700; color: #198754;">${dibujo.ndvi_medio?.toFixed(2) || '-'}</div>
            </div>
          </div>
          
          ${dibujo.area_m2 ? `
            <div style="background: #e7f5ff; padding: 6px; border-radius: 6px; text-align: center;">
              <span style="font-size: 14px; font-weight: 700; color: #1976d2;">${(dibujo.area_m2 / 10000).toFixed(2)} ha</span>
              <span style="font-size: 10px; color: #666; margin-left: 4px;">(${dibujo.area_m2.toFixed(0)} m²)</span>
            </div>
          ` : ''}
        </div>
      `;
      
      // Hacer la capa interactiva con popup
      layer.eachLayer(function(l) {
        l.dibujoId = dibujo.id;
        l.isDibujoGuardado = true;
        
        // NUEVO: Configurar para que no burbujeen los eventos
        l.options.bubblingMouseEvents = false;
        l.options.interactive = false; // Inicialmente no interactivo
        
        if (l.setStyle) {
          l.setStyle({ className: 'dibujo-clickeable'});
        }
        
        // Añadir popup
        l.bindPopup(popupContent, {
          maxWidth: 250,
          className: 'dibujo-popup',
          autoPan: true
        });
        
        // Click handler - solo abrir popup, sin cambiar visibilidad
        l.on('click', function(e) {
          // Prevenir propagación
          if (e && e.originalEvent) {
            e.originalEvent._stopped = true;
          }
          
          // Solo abrir popup si el dibujo está visible
          const currentStyle = this.options;
          if (currentStyle.opacity > 0 && currentStyle.interactive) {
            this.openPopup();
          }
          
          return false;
        }, null, true);
        
        // Efectos hover - SOLO si el dibujo está visible
        l.on('mouseover', function(e) {
          const currentOpacity = this.options.opacity || 0;
          
          // Solo aplicar hover si está visible E interactivo
          if (currentOpacity > 0 && this.options.interactive && this.setStyle) {
            const currentWeight = this.options.weight || 3;
            const currentFill = this.options.fillOpacity || 0.3;
            
            this.setStyle({ 
              weight: currentWeight + 2, 
              fillOpacity: Math.min(currentFill + 0.1, 0.5)
            });
          }
          return false;
        });
        
        l.on('mouseout', function(e) {
          const currentOpacity = this.options.opacity || 0;
          
          // Solo resetear hover si está visible E interactivo
          if (currentOpacity > 0 && this.options.interactive && this.setStyle) {
            const isActive = dibujoVisibleId === dibujo.id;
            this.setStyle({ 
              weight: isActive ? 4 : 3,
              fillOpacity: isActive ? 0.35 : 0.3
            });
          }
          return false;
        });
      });
      
      dibujosGuardadosLayer.addLayer(layer);
      
      // Evento eliminar
      item.querySelector('.delete-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        eliminarDibujo(dibujo.id);
      });
      
      // Click en el item para toggle visibilidad (solo uno a la vez)
      item.addEventListener('click', () => {
  // Verificar si "mostrar todos" está activo
  const btnToggleAll = document.getElementById('toggle-all-dibujos');
  const mostrandoTodos = btnToggleAll && btnToggleAll.textContent.includes('Ocultar todos');
  
  if (mostrandoTodos) {
    // Si están todos visibles, solo resaltar sin ocultar los demás
    resaltarDibujoSinOcultar(dibujo.id, item);
  } else {
    // Si no están todos visibles, comportamiento normal (mostrar solo uno)
    resaltarDibujo(dibujo.id, item);
  }
});
    });
    

    // Añade esta función ANTES de la función "resaltarDibujo":
// Busca la función resaltarDibujoSinOcultar y reemplázala completamente por esta:
function resaltarDibujoSinOcultar(id, itemElement) {
  // Quitar clase active de todos los items
  document.querySelectorAll('.dibujo-item').forEach(item => {
    item.classList.remove('active');
  });
  
  // Añadir clase active al item seleccionado
  itemElement.classList.add('active');
  dibujoVisibleId = id;
  
  // Mantener todos visibles pero resaltar el seleccionado
  dibujosGuardadosLayer.eachLayer(layer => {
    if (layer.dibujoId === id) {
      // Resaltar este con máxima visibilidad
      layer.setStyle({ 
        opacity: 1,
        fillOpacity: 0.45,
        weight: 5
      });
      
      // Activar interactividad
      layer.eachLayer(l => {
        l.options.interactive = true;
        if (l._path) {
          l._path.style.pointerEvents = 'auto';
        }
      });
      
      // Hacer zoom
      map.fitBounds(layer.getBounds(), {
        padding: [50, 50],
        maxZoom: 16
      });
      
      // Abrir popup automáticamente
      setTimeout(() => {
        layer.eachLayer(l => {
          if (l.getPopup) {
            l.openPopup();
          }
        });
      }, 300);
      
    } else {
      // Mantener visibles los demás pero con opacidad original (0.9)
      layer.setStyle({ 
        opacity: 0.9,
        fillOpacity: 0.3,
        weight: 3
      });
      
      // Mantener interactividad de todos
      layer.eachLayer(l => {
        l.options.interactive = true;
        if (l._path) {
          l._path.style.pointerEvents = 'auto';
        }
      });
    }
  });
}
    // Toggle todos
    const toggleAllBtn = document.getElementById('toggle-all-dibujos');
    if (toggleAllBtn) {
      toggleAllBtn.addEventListener('click', function() {
        todosVisibles = !todosVisibles;
        
        // Quitar el activo individual
        dibujoVisibleId = null;
        document.querySelectorAll('.dibujo-item').forEach(item => {
          item.classList.remove('active');
        });
        
        dibujosGuardadosLayer.eachLayer(layer => {
          if (todosVisibles) {
            // Mostrar todos
            layer.setStyle({ 
              opacity: 0.9,
              fillOpacity: 0.3
            });
            
            // CRÍTICO: Activar interactividad para todos
            layer.eachLayer(l => {
              l.options.interactive = true;
              if (l._path) {
                l._path.style.pointerEvents = 'auto';
              }
            });
          } else {

  map.closePopup();

  // Ocultar todos
  layer.setStyle({ 
    opacity: 0, 
    fillOpacity: 0 
  });

  // Desactivar interactividad
  layer.eachLayer(l => {
    l.options.interactive = false;
    if (l._path) {
      l._path.style.pointerEvents = 'none';
    }
  });
}
        });
        
        this.innerHTML = todosVisibles 
          ? '<i class="bi bi-eye-slash-fill"></i> Ocultar todos'
          : '<i class="bi bi-eye-fill"></i> Mostrar todos';
      });
    }
    
  } catch (error) {
    console.error('Error al cargar dibujos:', error);
  }
}

// Resaltar dibujo al hacer click en la lista (sin ocultarlo)
function resaltarDibujo(id, itemElement) {
  // Quitar clase active de todos los items
  document.querySelectorAll('.dibujo-item').forEach(item => {
    item.classList.remove('active');
  });
  
  // Añadir clase active al item seleccionado
  itemElement.classList.add('active');
  dibujoVisibleId = id;
  
  // OCULTAR TODOS primero, luego mostrar solo el seleccionado
  dibujosGuardadosLayer.eachLayer(layer => {
    if (layer.dibujoId === id) {
      // Mostrar solo este con máxima visibilidad Y hacerlo interactivo
      layer.setStyle({ 
        opacity: 1,
        fillOpacity: 0.45,
        weight: 5
      });
      
      // CRÍTICO: Activar interactividad
      layer.eachLayer(l => {
        l.options.interactive = true;
        if (l._path) {
          l._path.style.pointerEvents = 'auto';
        }
      });
      
      // Hacer zoom
      map.fitBounds(layer.getBounds(), {
        padding: [50, 50],
        maxZoom: 16
      });
      
      // Abrir popup automáticamente
      setTimeout(() => {
        layer.eachLayer(l => {
          if (l.getPopup) {
            l.openPopup();
          }
        });
      }, 300);
      
    } else {
  // Mantener visibles los demás, pero atenuados
  layer.setStyle({ 
    opacity: 0.4,
    fillOpacity: 0.15,
    weight: 3
  });

  // Siguen siendo interactivos si quieres
  layer.eachLayer(l => {
    l.options.interactive = true;
    if (l._path) {
      l._path.style.pointerEvents = 'auto';
    }
  });
}
  });
}

// Toggle al hacer click (mantener por compatibilidad pero ya no se usa mucho)
function toggleDibujoClick(id, itemElement) {
  const wasVisible = (dibujoVisibleId === id);
  
  // Quitar clase active de todos los items
  document.querySelectorAll('.dibujo-item').forEach(item => {
    item.classList.remove('active');
  });
  
  // Ocultar todos los dibujos
  dibujosGuardadosLayer.eachLayer(layer => {
    layer.setStyle({ opacity: 0, fillOpacity: 0 });
  });
  
  if (wasVisible) {
    // Si ya estaba visible, ocultarlo
    dibujoVisibleId = null;
  } else {
    // Mostrar solo este con mayor visibilidad
    dibujoVisibleId = id;
    itemElement.classList.add('active');
    
    dibujosGuardadosLayer.eachLayer(layer => {
      if (layer.dibujoId === id) {
        layer.setStyle({ 
          opacity: 1,           // Aumentado de 0.8 a 1
          fillOpacity: 0.35,    // Aumentado de 0.25 a 0.35
          weight: 4             // Aumentado de 3 a 4
        });
        
        // Hacer zoom
        map.fitBounds(layer.getBounds(), {
          padding: [50, 50],
          maxZoom: 16
        });
      }
    });
  }
}

// Eliminar dibujo
window.eliminarDibujo = async function(id) {

  const ok = await AppConfirm.open({
    title: "Eliminar dibujo",
    message: "¿Estás seguro de que deseas eliminar este dibujo?",
    okText: "Eliminar",
    cancelText: "Cancelar",
    okClass: "btn-danger"
  });

  if (!ok) return;

  try {
    const response = await fetch(`/api/eliminar-dibujo/${id}`, {
      method: 'DELETE'
    });

    if (response.ok) {

      // Limpiar estado si estaba visible
      if (dibujoVisibleId === id) {
        dibujoVisibleId = null;
        map.closePopup();
      }

      cargarDibujosGuardados();

      // ✅ NOTIFICACIÓN
      NotificationSystem.show({
        type: "success",
        title: "Dibujo eliminado",
        message: "El dibujo se eliminó correctamente"
      });

    } else {
      alert('Error al eliminar');
    }

  } catch (error) {
    console.error('Error:', error);
  }
};

// Cargar al inicio
cargarDibujosGuardados();

// CORRECCIÓN PRINCIPAL: Recargar después de guardar con limpieza de estado
if (typeof aceptarBtn !== 'undefined') {
  const originalClickHandler = aceptarBtn.onclick;
  
  aceptarBtn.addEventListener('click', function(e) {
    // Ejecutar el handler original si existe
    if (originalClickHandler) {
      originalClickHandler.call(this, e);
    }
    
    // Recargar dibujos después de un delay
    setTimeout(() => {
      cargarDibujosGuardados();
      
      // CRÍTICO: Limpiar el estado del modo de dibujo
      if (typeof drawnItems !== 'undefined') {
        drawnItems.clearLayers();
      }
      
      // Resetear variables globales si existen
      if (typeof currentLayer !== 'undefined') {
        currentLayer = null;
      }
      
      // Deshabilitar herramientas de dibujo activas
      if (typeof drawControl !== 'undefined' && map.hasLayer(drawControl)) {
        map.removeControl(drawControl);
        // Volver a añadir el control limpio
        if (typeof L.Control.Draw !== 'undefined') {
          map.addControl(drawControl);
        }
      }
      
      // NUEVO: Activar automáticamente "mostrar todos" después de guardar
      setTimeout(() => {
        const btnToggleAll = document.getElementById('toggle-all-dibujos');
        if (btnToggleAll && btnToggleAll.textContent.includes('Mostrar todos')) {
          btnToggleAll.click();
        }
      }, 100);
    }, 1000);
  });
}

// NUEVO: Hacer los dibujos guardados clickeables en el mapa
// Ahora con prevención de conflictos con recintos
dibujosGuardadosLayer.on('click', function(e) {
  // Solo procesar si realmente se hizo clic en un dibujo guardado
  if (!e.layer || !e.layer.isDibujoGuardado) return;
  
  const clickedLayer = e.layer;
  const dibujoId = clickedLayer.dibujoId;
  
  if (dibujoId) {
    // Encontrar el item correspondiente en la lista
    const item = document.querySelector(`.dibujo-item[data-dibujo-id="${dibujoId}"]`);
    if (item) {
      // Hacer scroll al item en la lista
      item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      
      // Resaltar el dibujo
      resaltarDibujo(dibujoId, item);
    }
  }
});

}); // end DOMContentLoaded - visor-dibujos.js