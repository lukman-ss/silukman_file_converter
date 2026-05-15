param(
  [string]$Exe = "",

  [switch]$RunExeMatrix,

  [switch]$SkipTests,

  [string]$ManualReport = "",

  [ValidateSet("internal-beta", "production")]
  [string]$Channel = "production"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

if (-not $Exe) {
  $optimized = Join-Path $PSScriptRoot "dist\silukman_file_converter_optimized.exe"
  $default = Join-Path $PSScriptRoot "dist\silukman_file_converter.exe"
  $Exe = if (Test-Path $optimized) { $optimized } else { $default }
}

$argsList = @(
  "tools\production_qa.py",
  "--exe",
  $Exe,
  "--channel",
  $Channel
)

if ($RunExeMatrix) {
  $argsList += "--run-exe-matrix"
}

if ($SkipTests) {
  $argsList += "--skip-tests"
}

if ($ManualReport) {
  $argsList += "--manual-report"
  $argsList += $ManualReport
}

& $python @argsList
