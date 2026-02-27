#!/usr/bin/env python3
"""
Diagnóstico avanzado de cobertura de tiles
"""

import os
from pathlib import Path
from datetime import datetime, timezone
import geopandas as gpd
from shapely.geometry import box, shape
import rasterio
from rasterio.warp import transform_bounds
from pystac_client import Client
import planetary_computer as pc
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Configuración
ROI_PATH = os.getenv(
    "ROI_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "processed" / "roi.gpkg")
)

TARGET_DATE = datetime(2025, 4, 25, tzinfo=timezone.utc)

def get_roi():
    roi = gpd.read_file(ROI_PATH).to_crs(4326)
    return roi

def visualizar_cobertura():
    roi = get_roi()
    bbox = tuple(roi.total_bounds)
    
    print(f"ROI BBox: {bbox}")
    print(f"ROI área: {roi.geometry.iloc[0].area:.6f} grados²")
    
    # Buscar imágenes
    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=pc.sign_inplace
    )
    
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=f"{TARGET_DATE.strftime('%Y-%m-%d')}",
        limit=100
    )
    
    items = list(search.items())
    
    print(f"\nTotal tiles encontrados: {len(items)}\n")
    
    # Crear figura
    fig, ax = plt.subplots(1, 1, figsize=(15, 10))
    
    # Dibujar ROI
    roi.plot(ax=ax, facecolor='yellow', edgecolor='red', alpha=0.3, linewidth=3)
    
    # Colores para tiles
    colors = ['blue', 'green', 'purple', 'orange', 'pink']
    
    for idx, item in enumerate(items):
        # Obtener geometría del tile
        tile_geom = shape(item.geometry)
        
        # Info del tile
        tile_id = item.id
        clouds = item.properties.get('eo:cloud_cover', -1)
        
        print(f"Tile {idx+1}: {tile_id}")
        print(f"  Nubes: {clouds:.1f}%")
        print(f"  Geometría: {tile_geom.bounds}")
        
        # Verificar intersección
        if tile_geom.intersects(roi.geometry.iloc[0]):
            intersection = tile_geom.intersection(roi.geometry.iloc[0])
            coverage_pct = (intersection.area / roi.geometry.iloc[0].area) * 100
            print(f"  ✓ Intersecta con ROI: {coverage_pct:.1f}% del ROI")
            
            # Dibujar tile
            gpd.GeoSeries([tile_geom], crs=4326).plot(
                ax=ax, 
                facecolor=colors[idx % len(colors)], 
                edgecolor='black',
                alpha=0.2,
                linewidth=2,
                label=f"{tile_id[-6:]} ({coverage_pct:.1f}%)"
            )
        else:
            print(f"  ✗ NO intersecta con ROI")
        
        # Verificar cobertura de bandas
        print(f"  Bandas disponibles:")
        for band in ['B04', 'B08', 'SCL']:
            if band in item.assets or band.lower() in item.assets:
                asset_key = band if band in item.assets else band.lower()
                asset = item.assets[asset_key]
                href = asset.href
                
                # Abrir banda y verificar bounds
                try:
                    with rasterio.open(href) as src:
                        # Convertir bounds a EPSG:4326
                        bounds_4326 = transform_bounds(
                            src.crs, "EPSG:4326",
                            *src.bounds
                        )
                        
                        # Verificar si cubre el ROI
                        band_box = box(*bounds_4326)
                        if band_box.intersects(roi.geometry.iloc[0]):
                            coverage = band_box.intersection(roi.geometry.iloc[0]).area / roi.geometry.iloc[0].area * 100
                            print(f"    ✓ {band}: Cubre {coverage:.1f}% del ROI")
                            print(f"      Bounds: {bounds_4326}")
                            print(f"      Shape: {src.shape}, CRS: {src.crs}")
                        else:
                            print(f"    ✗ {band}: NO cubre el ROI")
                            print(f"      Bounds: {bounds_4326}")
                
                except Exception as e:
                    print(f"    ✗ {band}: Error al abrir - {e}")
            else:
                print(f"    ✗ {band}: No disponible")
        
        print()
    
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    ax.set_title(f'Cobertura de Tiles Sentinel-2\n{TARGET_DATE.strftime("%Y-%m-%d")}')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    
    # Guardar figura
    output_path = Path("diagnostico_cobertura.png")
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n✓ Mapa de cobertura guardado: {output_path}")
    
    plt.close()
    
    # Análisis de gaps
    print("\n" + "="*70)
    print("ANÁLISIS DE COBERTURA")
    print("="*70)
    
    roi_geom = roi.geometry.iloc[0]
    total_coverage = roi_geom.bounds  # (minx, miny, maxx, maxy)
    
    # Unión de todos los tiles
    from shapely.ops import unary_union
    tile_geoms = [shape(item.geometry) for item in items]
    union = unary_union(tile_geoms)
    
    # Verificar si cubre completamente el ROI
    if union.contains(roi_geom):
        print("✓ Los tiles cubren COMPLETAMENTE el ROI")
    else:
        print("✗ Los tiles NO cubren completamente el ROI")
        
        # Calcular área sin cobertura
        if union.intersects(roi_geom):
            covered = union.intersection(roi_geom)
            uncovered = roi_geom.difference(covered)
            
            coverage_pct = (covered.area / roi_geom.area) * 100
            print(f"\n  Cobertura: {coverage_pct:.2f}%")
            print(f"  Sin cobertura: {100 - coverage_pct:.2f}%")
            
            if hasattr(uncovered, 'bounds'):
                print(f"  Área sin cobertura (bounds): {uncovered.bounds}")
        else:
            print("  ✗ Los tiles no intersectan el ROI en absoluto")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    try:
        visualizar_cobertura()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()