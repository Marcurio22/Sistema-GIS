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

Write-Host "START TEST: " (Get-Date)
python .\update_ndvi_test.py
Write-Host "END TEST: " (Get-Date)