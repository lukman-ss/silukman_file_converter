$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "build_release_package.ps1") -Channel "internal-beta"
