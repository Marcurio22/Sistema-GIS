import numpy as np
from PIL import Image
import matplotlib.pyplot as plt


def compute_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """
    Calcula NDVI a partir de las bandas RED y NIR.
    red y nir deben ser arrays 2D (mismo tamaño) en float.
    """
    red = red.astype(np.float32)
    nir = nir.astype(np.float32)

    # NDVI = (NIR - RED) / (NIR + RED)
    # Añadimos un epsilon para evitar divisiones por cero
    eps = 1e-6
    ndvi = (nir - red) / (nir + red + eps)

    # Limitamos al rango [-1, 1] por seguridad numérica
    ndvi = np.clip(ndvi, -1.0, 1.0)
    return ndvi


def ndvi_from_rgb_png(input_path: str,
                      ndvi_gray_path: str,
                      ndvi_color_path: str):
    """
    Lee una imagen RGB (como la que has adjuntado) y genera:
      - Un NDVI en escala de grises normalizado
      - Un mapa coloreado (estilo heatmap) con todos los coeficientes NDVI.

    IMPORTANTE: aquí hacemos una APROXIMACIÓN, usando el canal G como NIR.
    Para NDVI real, sustituye 'nir = g' por la banda NIR verdadera.
    """
    # 1. Leer imagen
    rgb_img = Image.open(input_path).convert("RGB")
    rgb = np.array(rgb_img).astype(np.float32)

    # Separar canales (PIL -> RGB)
    r = rgb[:, :, 0]  # Red
    g = rgb[:, :, 1]  # Green
    b = rgb[:, :, 2]  # Blue

    # 2. APROXIMACIÓN: usamos G como pseudo-NIR
    nir = g
    red = r

    # 3. Calcular NDVI
    ndvi = compute_ndvi(red, nir)

    # 4. Guardar NDVI en escala de grises (0–255)
    #    Mapeamos [-1, 1] -> [0, 255]
    ndvi_norm = (ndvi + 1) / 2.0
    ndvi_8bit = (ndvi_norm * 255).astype(np.uint8)
    ndvi_gray_img = Image.fromarray(ndvi_8bit)
    ndvi_gray_img.save(ndvi_gray_path)

    # 5. Crear imagen coloreada tipo la segunda imagen (colormap)
    plt.figure(figsize=(6, 6))
    plt.imshow(ndvi, cmap="RdYlGn")  # rojo = bajo NDVI, verde = alto NDVI
    plt.axis("off")
    cbar = plt.colorbar(fraction=0.046, pad=0.04)
    cbar.set_label("NDVI", rotation=270, labelpad=15)

    plt.tight_layout(pad=0)
    plt.savefig(ndvi_color_path, dpi=300, bbox_inches="tight", pad_inches=0)
    plt.close()


if __name__ == "__main__":
    # Rutas de ejemplo (cámbialas por las tuyas)
    input_image = "./campo_rgb.png"               # la imagen que has adjuntado
    ndvi_gray_out = "campo_ndvi_gris.png"       # NDVI en escala de grises
    ndvi_color_out = "campo_ndvi_color.png"     # NDVI coloreado (tipo heatmap)

    ndvi_from_rgb_png(input_image, ndvi_gray_out, ndvi_color_out)
