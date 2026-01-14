class GaleriaImagenes {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.imagenes = [];
    this.maxVisibles = 5;
    this.mostrandoTodas = false;
    this.init();
  }

  init() {
    this.cargarImagenes();
    this.initSubida();
  }

  async cargarImagenes() {
    try {
      this.container.innerHTML = '<p>Cargando imágenes...</p>';

      // IMÁGENES DE EJEMPLO
      this.imagenes = [
        { id: 1, thumb: 'https://picsum.photos/400/300?1', titulo: 'Imagen 1', descripcion: 'Descripción 1' },
        { id: 2, thumb: 'https://picsum.photos/400/300?2', titulo: 'Imagen 2', descripcion: 'Descripción 2' },
        { id: 3, thumb: 'https://picsum.photos/400/300?3', titulo: 'Imagen 3', descripcion: 'Descripción 3' },
        { id: 4, thumb: 'https://picsum.photos/400/300?4', titulo: 'Imagen 4', descripcion: 'Descripción 4' },
        { id: 5, thumb: 'https://picsum.photos/400/300?5', titulo: 'Imagen 5', descripcion: 'Descripción 5' },
        { id: 6, thumb: 'https://picsum.photos/400/300?6', titulo: 'Imagen 6', descripcion: 'Descripción 6' },
      ];

      this.renderizarGaleria();
    } catch (error) {
      console.error(error);
      this.container.innerHTML = '<p>Error cargando imágenes</p>';
    }
  }

  renderizarGaleria() {
    this.container.innerHTML = '';
    const imagenesAMostrar = this.mostrandoTodas ? this.imagenes : this.imagenes.slice(0, this.maxVisibles);

    imagenesAMostrar.forEach(imagen => {
      const item = document.createElement('div');
      item.className = 'galeria-item';
      item.style.cursor = 'default';

      item.innerHTML = `
        <img src="${imagen.thumb}" alt="${imagen.titulo}" loading="lazy">
        <div class="galeria-overlay">
          <h4>${imagen.titulo}</h4>
          <p>${imagen.descripcion}</p>
        </div>
      `;

      this.container.appendChild(item);
    });

    // Tarjeta "Ver Todas"
    if (!this.mostrandoTodas && this.imagenes.length > this.maxVisibles) {
      const verMas = document.createElement('div');
      verMas.className = 'galeria-item galeria-ver-mas';
      verMas.innerHTML = `
        <div class="ver-mas">
          <span>+${this.imagenes.length - this.maxVisibles}</span>
          <p>Ver todas</p>
        </div>
      `;
      verMas.onclick = () => {
        this.mostrandoTodas = true;
        this.renderizarGaleria();
      };
      this.container.appendChild(verMas);
    }
  }

  initSubida() {
    const form = document.getElementById('form-subida');
    form.onsubmit = async (e) => {
      e.preventDefault();

      const fileInput = document.getElementById('imagen-file');
      const titulo = document.getElementById('imagen-titulo').value;
      const descripcion = document.getElementById('imagen-descripcion').value;

      if (!fileInput.files.length) return alert("Selecciona una imagen");

      const formData = new FormData();
      formData.append('imagen', fileInput.files[0]);
      formData.append('titulo', titulo);
      formData.append('descripcion', descripcion);

      try {
        const res = await fetch('/api/galeria/subir', {
          method: 'POST',
          body: formData
        });

        if (!res.ok) throw new Error("Error al subir la imagen");

        const nuevaImagen = await res.json();
        this.imagenes.push(nuevaImagen);
        this.renderizarGaleria();

        // Cerrar modal Bootstrap
        const modalEl = document.getElementById('modalSubida');
        const modal = bootstrap.Modal.getInstance(modalEl);
        modal.hide();

        form.reset();
      } catch (error) {
        console.error(error);
        alert("Error subiendo la imagen");
      }
    };
  }
}

// Inicializar galería
let galeria;
document.addEventListener('DOMContentLoaded', () => {
  galeria = new GaleriaImagenes('galeria-grid');
});
