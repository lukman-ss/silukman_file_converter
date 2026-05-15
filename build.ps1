$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

$argsList = @(
  "--noconfirm",
  "--onefile",
  "--windowed",
  "--name",
  "silukman_file_converter"
)

if (Test-Path "assets/icon.ico") {
  $argsList += "--icon=assets/icon.ico"
}

if (Test-Path "app/core/paddle_ocr_worker.py") {
  $argsList += "--add-data"
  $argsList += "app/core/paddle_ocr_worker.py;app/core"
}

$argsList += "app/main.py"

& $python -m PyInstaller @argsList
