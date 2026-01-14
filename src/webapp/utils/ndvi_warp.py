import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.io import MemoryFile
from PIL import Image

def warp_tif_to_3857(src_tif: str, dst_tif: str):
    dst_crs = "EPSG:3857"

    with rasterio.open(src_tif) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )

        kwargs = src.meta.copy()
        kwargs.update({
            "crs": dst_crs,
            "transform": transform,
            "width": width,
            "height": height,
        })

        with rasterio.open(dst_tif, "w", **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear,
                )

def tif_to_png_singleband(src_tif: str, dst_png: str, nodata_to_transparent=True):
    """
    Convierte un GeoTIFF 1 banda (float NDVI) a PNG (RGBA) sin márgenes ni reescalados raros.
    """
    with rasterio.open(src_tif) as src:
        arr = src.read(1).astype("float32")

    vmin, vmax = -1.0, 1.0
    norm = (arr - vmin) / (vmax - vmin)
    norm = np.clip(norm, 0, 1)

    rgb = (norm * 255).astype(np.uint8)

    if nodata_to_transparent:
        alpha = np.where(np.isfinite(arr), 255, 0).astype(np.uint8)
    else:
        alpha = np.full_like(rgb, 255, dtype=np.uint8)

    rgba = np.dstack([rgb, rgb, rgb, alpha])  # colormap
    Image.fromarray(rgba, mode="RGBA").save(dst_png)