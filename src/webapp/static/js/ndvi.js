class NDVI {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.recintoId = null;
    this.init();
  }

  init() {
    this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver NDVI</p>';
  }

  async setRecintoId(recintoId) {
    this.recintoId = recintoId;
    await this.cargarYMostrar();
  }

  async cargarYMostrar() {
    if (!this.recintoId) {
      this.container.innerHTML = '<p class="text-muted">Selecciona un recinto para ver NDVI</p>';
      return;
    }

    try {
      // Cargar datos del NDVI
      const response = await fetch(`/api/indices-raster?id_recinto=${this.recintoId}&tipo_indice=NDVI`);
      
      if (!response.ok) {
        throw new Error('Error al cargar NDVI');
      }

      const indices = await response.json();
      
      if (!indices || indices.length === 0) {
        this.container.innerHTML = `
          <div class="text-muted text-center py-3">
            <i class="fa-solid fa-leaf mb-2" style="font-size: 2rem; opacity: 0.3;"></i>
            <p class="mb-0">No hay datos NDVI disponibles</p>
          </div>
        `;
        return;
      }

      // Tomar el índice más reciente
      const ultimoIndice = indices[0];
      
      // Obtener ruta de la imagen desde la BD
      let rutaImagen = ultimoIndice.ruta_ndvi;
      
      // Limpiar la ruta: quitar prefijo 'webapp/' si existe
      if (rutaImagen) {
        rutaImagen = rutaImagen.replace(/^webapp\//, '');
        
        // Asegurar que la ruta empiece con /
        if (!rutaImagen.startsWith('/')) {
          rutaImagen = '/' + rutaImagen;
        }
      }
      
      // Si no hay ruta, usar fallback
      if (!rutaImagen) {
        rutaImagen = `/static/thumbnails/${ultimoIndice.fecha_ndvi ? ultimoIndice.fecha_ndvi.replace(/-/g, '').substring(0, 8) : 'unknown'}_${this.recintoId}.png`;
      }
      
      this.container.innerHTML = `
        <div class="ndvi-card">
          <img src="${rutaImagen}" 
               alt="NDVI Recinto ${this.recintoId}" 
               class="ndvi-imagen"
               onerror="this.parentElement.innerHTML='<p class=text-muted>No hay imagen NDVI disponible</p>'">
          
          <div class="ndvi-stats">
            <div class="stat-item">
              <span class="stat-label">Media</span>
              <span class="stat-value">${ultimoIndice.valor_medio.toFixed(4)}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Mín</span>
              <span class="stat-value">${ultimoIndice.valor_min.toFixed(4)}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Máx</span>
              <span class="stat-value">${ultimoIndice.valor_max.toFixed(4)}</span>
            </div>
            
          </div>
        </div>
      `;
      
    } catch (error) {
      console.error('Error:', error);
      this.container.innerHTML = '<p class="text-danger">Error cargando NDVI</p>';
    }
  }
}

// Inicializar
window.ndviManager = null;
document.addEventListener('DOMContentLoaded', () => {
  window.ndviManager = new NDVI('ndvi-container');
});