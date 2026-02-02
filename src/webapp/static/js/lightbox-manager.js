/**
 * LightboxManager - Gestor centralizado del lightbox
 * Maneja correctamente los cambios de recinto y la navegación entre imágenes
 */
class LightboxManager {
  constructor() {
    this.isOpen = false;
    this.currentImageIndex = 0;
    this.images = [];
    this.recintoId = null;
    
    // Elementos DOM
    this.lightbox = null;
    this.lightboxImg = null;
    this.lightboxCaption = null;
    this.closeBtn = null;
    this.prevBtn = null;
    this.nextBtn = null;
    
    this.init();
  }

  init() {
    // Obtener referencias a los elementos del DOM
    this.lightbox = document.getElementById('lightbox');
    this.lightboxImg = document.getElementById('lightbox-img');
    this.lightboxCaption = document.getElementById('lightbox-caption');
    this.closeBtn = document.querySelector('.lightbox-close');
    this.prevBtn = document.getElementById('lightbox-prev');
    this.nextBtn = document.getElementById('lightbox-next');

    // Validar que existen los elementos
    if (!this.lightbox || !this.lightboxImg || !this.lightboxCaption) {
      console.error('LightboxManager: Elementos del lightbox no encontrados');
      return;
    }

    this.setupEventListeners();
  }

  setupEventListeners() {
    // Cerrar con el botón X
    if (this.closeBtn) {
      this.closeBtn.onclick = (e) => {
        e.stopPropagation();
        this.close();
      };
    }

    // Cerrar al hacer clic fuera de la imagen
    this.lightbox.onclick = (e) => {
      if (e.target === this.lightbox) {
        this.close();
      }
    };

    // Navegación con botones
    if (this.prevBtn) {
      this.prevBtn.onclick = (e) => {
        e.stopPropagation();
        this.showPrevious();
      };
    }

    if (this.nextBtn) {
      this.nextBtn.onclick = (e) => {
        e.stopPropagation();
        this.showNext();
      };
    }

    // Cerrar con tecla ESC y navegar con flechas
    document.addEventListener('keydown', (e) => {
      if (!this.isOpen) return;

      switch(e.key) {
        case 'Escape':
          this.close();
          break;
        case 'ArrowLeft':
          this.showPrevious();
          break;
        case 'ArrowRight':
          this.showNext();
          break;
      }
    });
  }

  /**
   * Actualiza el conjunto de imágenes y el ID del recinto
   * Se llama cada vez que cambia de recinto
   */
updateImages(images, recintoId, tipo = 'galeria') {
  if (this.isOpen) this.close();

  this.images = images ? [...images] : [];
  this.recintoId = recintoId;
  this.tipo = tipo; // 👈 NUEVO
  this.currentImageIndex = 0;

  console.log(
    `[Lightbox] imágenes=${this.images.length}, recinto=${recintoId}, tipo=${tipo}`
  );
}
  /**
   * Abre el lightbox mostrando la imagen en el índice especificado
   */
  open(index = 0) {
    console.log(`LightboxManager: open() llamado con índice ${index}`);
    console.log(`LightboxManager: Total de imágenes disponibles: ${this.images.length}`);
    
    if (!this.images || this.images.length === 0) {
      console.warn('LightboxManager: No hay imágenes para mostrar');
      return;
    }

    // Validar índice
    if (index < 0 || index >= this.images.length) {
      console.warn(`LightboxManager: Índice ${index} fuera de rango (0-${this.images.length - 1}), usando 0`);
      index = 0;
    }

    this.currentImageIndex = index;
    this.isOpen = true;
    
    console.log(`LightboxManager: Abriendo con currentImageIndex = ${this.currentImageIndex}`);
    console.log(`LightboxManager: Imagen a mostrar:`, this.images[this.currentImageIndex]);
    
    this.render();
    
    // Mostrar lightbox
    this.lightbox.style.display = 'block';
    document.body.style.overflow = 'hidden';

    console.log(`LightboxManager: Abierto en imagen ${index + 1}/${this.images.length}`);
  }

  /**
   * Cierra el lightbox
   */
  close() {
    this.isOpen = false;
    this.lightbox.style.display = 'none';
    document.body.style.overflow = '';
    
    console.log('LightboxManager: Cerrado');
  }

  /**
   * Muestra la imagen anterior
   */
  showPrevious() {
    if (!this.isOpen || this.images.length === 0) return;
    
    this.currentImageIndex = (this.currentImageIndex - 1 + this.images.length) % this.images.length;
    this.render();
    
    console.log(`LightboxManager: Imagen anterior → ${this.currentImageIndex + 1}/${this.images.length}`);
  }

  /**
   * Muestra la imagen siguiente
   */
  showNext() {
    if (!this.isOpen || this.images.length === 0) return;
    
    this.currentImageIndex = (this.currentImageIndex + 1) % this.images.length;
    this.render();
    
    console.log(`LightboxManager: Imagen siguiente → ${this.currentImageIndex + 1}/${this.images.length}`);
  }

  /**
   * Renderiza la imagen actual en el lightbox
   */
  render() {
    if (!this.images || this.images.length === 0) {
      console.warn('LightboxManager: No hay imágenes para renderizar');
      return;
    }

    const imagen = this.images[this.currentImageIndex];


    if (this.tipo === 'ndvi') {
      this.lightboxImg.src = imagen.url || '';
      this.lightboxImg.style.backgroundColor = '#ffffff';
      this.lightboxImg.style.padding = '10px';
      this.lightboxImg.style.borderRadius = '8px';

      this.lightboxCaption.innerHTML = `
        <strong>${imagen.fecha}</strong><br>
        Media: ${imagen.media}<br>
        Mín: ${imagen.min}<br>
        Máx: ${imagen.max}<br>
        <small>${this.currentImageIndex + 1} de ${this.images.length}</small>
      `;

      this.updateNavigationButtons();
      return; 
    }

    
    if (!imagen) {
      console.error(`LightboxManager: Imagen en índice ${this.currentImageIndex} no encontrada`);
      return;
    }

    // Actualizar imagen
    this.lightboxImg.src = imagen.thumb || imagen.url || '';
    
    // Extraer y formatear coordenadas
    const coords = this.extraerCoordenadas(imagen.geom);
    const coordsHTML = coords 
      ? `<br><small style="color: #17a2b8; font-weight: 500;">📍 ${this.formatearCoordenadas(coords)}</small>` 
      : '';

    // Actualizar caption
    this.lightboxCaption.innerHTML = `
      <strong>${imagen.titulo || 'Sin título'}</strong>
      ${imagen.descripcion ? '<br>' + imagen.descripcion : ''}
      ${coordsHTML}
      <br><small style="opacity: 0.7;">Imagen ${this.currentImageIndex + 1} de ${this.images.length}</small>
    `;

    // Mostrar/ocultar botones de navegación según sea necesario
    this.updateNavigationButtons();
  }

  /**
   * Actualiza la visibilidad de los botones de navegación
   */
  updateNavigationButtons() {
    if (this.images.length <= 1) {
      // Si solo hay una imagen, ocultar botones de navegación
      if (this.prevBtn) this.prevBtn.style.display = 'none';
      if (this.nextBtn) this.nextBtn.style.display = 'none';
    } else {
      // Si hay múltiples imágenes, mostrar botones
      if (this.prevBtn) this.prevBtn.style.display = 'block';
      if (this.nextBtn) this.nextBtn.style.display = 'block';
    }
  }

  /**
   * Extrae coordenadas de geometría WKT (ej: "POINT(lon lat)")
   */
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

  /**
   * Formatea coordenadas para mostrar
   */
  formatearCoordenadas(coords) {
    if (!coords) return '';
    return `Lat: ${coords.lat.toFixed(6)}, Lon: ${coords.lon.toFixed(6)}`;
  }

  /**
   * Verifica si el lightbox está abierto actualmente
   */
  getIsOpen() {
    return this.isOpen;
  }

  /**
   * Obtiene el recinto actual
   */
  getCurrentRecintoId() {
    return this.recintoId;
  }

  /**
   * Obtiene el número total de imágenes
   */
  getImageCount() {
    return this.images.length;
  }
}

// Instancia global del gestor de lightbox
window.lightboxManager = null;

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
  window.lightboxManager = new LightboxManager();
  console.log('LightboxManager: Inicializado correctamente');
});