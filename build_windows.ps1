param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

# The model weights are intentionally not frozen into the executable by default:
# place approved local weights in .\models\ and choose them in Settings.
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name VehicleAttendance `
    --collect-all ultralytics `
    --collect-all torchvision `
    --collect-all torchreid `
    --add-data "models;models" `
    --add-data "data;data" `
    run.py

Write-Host "Built: dist\VehicleAttendance\VehicleAttendance.exe"
