# ============================
# Configuración NDVI Sentinel-2
# ============================

$env:ROI_PATH = "C:\Users\Usuario\Desktop\Sistema-GIS-main\data\processed\roi.gpkg"

$env:S2_DAYS_BACK = "60"
$env:S2_CLOUD_MAX = "40"
$env:S2_MAX_ITEMS_TOTAL = "20"
$env:S2_MAX_ITEMS_PER_TILE = "5"
$env:S2_FETCH_LIMIT = "200"

$env:NDVI_RES_M = "10"
$env:NDVI_MAX_DIM = "8000"

$env:DEBUG_S2 = "1"
$env:DEBUG_STAC = "0"

# ============================
# Comprobaciones rápidas
# ============================

if (-not (Test-Path $env:ROI_PATH)) {
  Write-Error "ROI_PATH no existe: $env:ROI_PATH"
  exit 1
}

Write-Host "Python:"; python --version
Write-Host "ROI_PATH=$env:ROI_PATH"
Write-Host "DAYS_BACK=$env:S2_DAYS_BACK  CLOUD_MAX=$env:S2_CLOUD_MAX"
Write-Host "RES_M=$env:NDVI_RES_M  MAX_DIM=$env:NDVI_MAX_DIM"

# ============================
# Ejecución
# ============================

Write-Host ("START: " + (Get-Date))
python .\update_ndvi.py
Write-Host ("END: " + (Get-Date))
exit $LASTEXITCODE