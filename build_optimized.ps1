$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

$env:SILUKMAN_DISABLE_CV2_PREPROCESS = "1"

& $python -m PyInstaller --noconfirm (Join-Path $PSScriptRoot "silukman_file_converter_optimized.spec")

$exe = Join-Path $PSScriptRoot "dist\silukman_file_converter_optimized.exe"
if (-not (Test-Path $exe)) {
  throw "Optimized EXE was not created: $exe"
}

$sizeMb = [Math]::Round((Get-Item $exe).Length / 1MB, 2)
Write-Host "Optimized EXE: $exe"
Write-Host "Size: $sizeMb MiB"
