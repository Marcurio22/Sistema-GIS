import os
import json
from pathlib import Path
import tempfile
from datetime import datetime, timedelta, timezone

import numpy as np
import geopandas as gpd
from PIL import Image

import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling

from shapely.geometry import box, mapping

from pystac_client import Client

from webapp import create_app, db
from sqlalchemy import text


INVALID_SCL = {1, 3, 7, 8, 9, 10, 11}  # saturado, sombras, nubes, cirros, nieve... : no usar en RGB


def get_roi_bbox_from_gpkg():
    """
    Lee el ROI desde un GeoPackage y devuelve bbox (minx,miny,maxx,maxy) en EPSG:4326.
    Mantiene exactamente el patrón que ya usas en otros scripts.
    """
    # Por defecto: ../data/processed/roi.gpkg
    default_path = Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg"
    roi_path = Path(os.getenv("ROI_PATH", str(default_path)))

    if not roi_path.exists():
        raise FileNotFoundError(f"No existe ROI.gpkg en: {roi_path}")

    roi = gpd.read_file(roi_path).to_crs(4326)  # WGS84
    minx, miny, maxx, maxy = roi.total_bounds
    return float(minx), float(miny), float(maxx), float(maxy)


def open_stac_catalog():
    # earth-search v0 aparece documentado ampliamente; algunos despliegues también tienen v1.
    for url in ("https://earth-search.aws.element84.com/v1", "https://earth-search.aws.element84.com/v0"):
        try:
            return Client.open(url)
        except Exception:
            pass
    raise RuntimeError("No se pudo abrir earth-search (v0/v1).")


def pick_items(catalog, geom_geojson, start_dt, end_dt, max_items=6, cloud_max=60):
    search = catalog.search(
        collections=["sentinel-s2-l2a-cogs"],  # dataset COG abierto :contentReference[oaicite:4]{index=4}
        intersects=geom_geojson,
        datetime=f"{start_dt.isoformat()}/{end_dt.isoformat()}",
    )
    items = list(search.get_items())

    # ordenar: primero baja nubosidad, luego más reciente
    def cloud(item):
        return float(item.properties.get("eo:cloud_cover", 999))

    def dt(item):
        return item.datetime or datetime(1970, 1, 1, tzinfo=timezone.utc)

    items = [it for it in items if cloud(it) <= cloud_max]
    items.sort(key=lambda it: (cloud(it), -dt(it).timestamp()))

    return items[:max_items]


def _href_to_readable(href: str) -> str:
    # earth-search suele dar https; si te da s3://, rasterio lo abre con /vsis3/
    if href.startswith("s3://"):
        return "/vsis3/" + href[len("s3://"):]
    return href


def reproject_asset_to_grid(href, dst_transform, dst_crs, width, height, resampling):
    href = _href_to_readable(href)
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="YES"):
        with rasterio.open(href) as src:
            if src.count == 1:
                dst = np.full((height, width), np.nan, dtype=np.float32)
                reproject(
                    source=rasterio.band(src, 1),
                    destination=dst,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs=dst_crs,
                    resampling=resampling,
                    dst_nodata=np.nan,
                )
                return dst
            else:
                dst = np.full((src.count, height, width), np.nan, dtype=np.float32)
                for b in range(1, src.count + 1):
                    reproject(
                        source=rasterio.band(src, b),
                        destination=dst[b - 1],
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=dst_transform,
                        dst_crs=dst_crs,
                        resampling=resampling,
                        dst_nodata=np.nan,
                    )
                return dst


def compute_output_shape(minx, miny, maxx, maxy, max_dim=4096, min_dim=512):
    lon_span = maxx - minx
    lat_span = maxy - miny
    if lat_span <= 0 or lon_span <= 0:
        return (min_dim, min_dim)

    ratio = lon_span / lat_span
    if ratio >= 1:
        w = max_dim
        h = int(max_dim / ratio)
    else:
        h = max_dim
        w = int(max_dim * ratio)

    w = max(min_dim, min(max_dim, w))
    h = max(min_dim, min(max_dim, h))
    return w, h


def main():
    app = create_app()
    with app.app_context():
        minx, miny, maxx, maxy = get_roi_bbox_from_gpkg()

        # ventana de búsqueda: últimos 14 días
        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(days=14)
        end_dt = now

        geom = mapping(box(minx, miny, maxx, maxy))

        catalog = open_stac_catalog()
        items = pick_items(catalog, geom, start_dt, end_dt, max_items=6, cloud_max=60)

        if not items:
            print("No hay escenas candidatas; no se actualiza.")
            return 0

        width, height = compute_output_shape(minx, miny, maxx, maxy, max_dim=4096)
        dst_crs = "EPSG:4326"
        dst_transform = from_bounds(minx, miny, maxx, maxy, width, height)

        rgb_stack = []

        for it in items:
            assets = it.assets

            # Preferimos un “visual” si existe; si no, usamos B04/B03/B02
            if "visual" in assets:
                rgb_href = assets["visual"].href
                rgb = reproject_asset_to_grid(
                    rgb_href, dst_transform, dst_crs, width, height, Resampling.bilinear
                )  # (3,H,W) float
            else:
                # fallback: construir RGB con B04/B03/B02
                r = reproject_asset_to_grid(assets["B04"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
                g = reproject_asset_to_grid(assets["B03"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
                b = reproject_asset_to_grid(assets["B02"].href, dst_transform, dst_crs, width, height, Resampling.bilinear)
                rgb = np.stack([r, g, b], axis=0)

                # estirado básico a 0-255
                rgb = np.clip(rgb / 3000.0 * 255.0, 0, 255)

            # SCL para máscara de nubes (nearest)
            if "SCL" in assets:
                scl = reproject_asset_to_grid(
                    assets["SCL"].href, dst_transform, dst_crs, width, height, Resampling.nearest
                )
                mask = np.isin(scl.astype(np.int32), list(INVALID_SCL))
                rgb[:, mask] = np.nan

            rgb_stack.append(rgb)

        # Composite: mediana ignorando NaN
        stack = np.stack(rgb_stack, axis=0)  # (T,3,H,W)
        comp = np.nanmedian(stack, axis=0)   # (3,H,W)

        if np.all(np.isnan(comp)):
            print("Composite vacío (todo nubes/NaN); no se actualiza.")
            return 0

        comp = np.nan_to_num(comp, nan=0.0)
        comp = np.clip(comp, 0, 255).astype(np.uint8)
        comp = np.transpose(comp, (1, 2, 0))  # H,W,3

        # Guardado atómico
        static_dir = os.path.join(app.root_path, "static", "sentinel2")
        os.makedirs(static_dir, exist_ok=True)
        out_png = os.path.join(static_dir, "s2_rgb_latest.png")
        out_meta = os.path.join(static_dir, "s2_rgb_latest.json")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png", dir=static_dir) as tmp:
            tmp_png = tmp.name

        Image.fromarray(comp, mode="RGB").save(tmp_png, format="PNG", optimize=True)
        os.replace(tmp_png, out_png)

        meta = {
            "updated_utc": now.isoformat(),
            "items_used": [it.id for it in items],
            "bbox": [minx, miny, maxx, maxy],
        }
        with open(out_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"OK: actualizado {out_png}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())