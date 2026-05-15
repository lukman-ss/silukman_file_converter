param(
  [ValidateSet("internal-beta", "production")]
  [string]$Channel = "production",

  [string]$Version = ""
)

$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

$argsList = @("scripts\build_release_package.py", "--channel", $Channel, "--validate-only")
if ($Version) {
  $argsList += "--version"
  $argsList += $Version
}

& $python @argsList
