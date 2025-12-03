import numpy as np
from PIL import Image
import matplotlib.pyplot as plt


def compute_exg(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """
    Calcula ExG (Excess Green) - índice de vegetación para imágenes RGB.
    ExG = 2*G - R - B
    """
    red = red.astype(np.float32)
    green = green.astype(np.float32)
    blue = blue.astype(np.float32)
    
    # Normalizar a [0, 1]
    red /= 255.0
    green /= 255.0
    blue /= 255.0
    
    exg = 2 * green - red - blue
    return exg


def vegetation_from_rgb(input_path: str,
                       output_gray_path: str,
                       output_color_path: str):
    """
    Genera un mapa de vegetación a partir de una imagen RGB normal.
    """
    # 1. Leer imagen
    rgb_img = Image.open(input_path).convert("RGB")
    rgb = np.array(rgb_img).astype(np.float32)
    
    # Separar canales
    r = rgb[:, :, 0]
    g = rgb[:, :, 1]
    b = rgb[:, :, 2]
    
    # 2. Calcular índice de vegetación
    veg_index = compute_exg(r, g, b)
    
    # 3. Normalizar a [0, 255] para escala de grises
    veg_min = veg_index.min()
    veg_max = veg_index.max()
    veg_norm = (veg_index - veg_min) / (veg_max - veg_min)
    veg_8bit = (veg_norm * 255).astype(np.uint8)
    
    # Guardar en escala de grises
    gray_img = Image.fromarray(veg_8bit)
    gray_img.save(output_gray_path)
    
    # 4. Crear mapa de calor
    plt.figure(figsize=(6, 6))
    plt.imshow(veg_index, cmap="RdYlGn")
    plt.axis("off")
    cbar = plt.colorbar(fraction=0.046, pad=0.04)
    cbar.set_label("Índice de Vegetación (ExG)", rotation=270, labelpad=15)
    
    plt.tight_layout(pad=0)
    plt.savefig(output_color_path, dpi=300, bbox_inches="tight", pad_inches=0)
    plt.close()
    
    print(f"✅ Imágenes generadas:")
    print(f"   - Escala de grises: {output_gray_path}")
    print(f"   - Mapa de calor: {output_color_path}")


if __name__ == "__main__":
    input_image = "./campo_rgb.png"
    output_gray = "./campo_vegetacion_gris.png"
    output_color = "./campo_vegetacion_color.png"
    
    vegetation_from_rgb(input_image, output_gray, output_color)