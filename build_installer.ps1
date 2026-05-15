$ErrorActionPreference = "Stop"

$searchedPaths = New-Object System.Collections.Generic.List[string]
$iscc = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
$isccPath = if ($iscc) {
  $searchedPaths.Add($iscc.Source)
  $iscc.Source
} else {
  $null
}

$commonPaths = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
  "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
)

foreach ($candidate in $commonPaths) {
  if (-not [string]::IsNullOrWhiteSpace($candidate)) {
    $searchedPaths.Add($candidate)
  }
  if (-not $isccPath -and (Test-Path $candidate)) {
    $isccPath = $candidate
  }
}

if (-not $isccPath) {
  $searched = ($searchedPaths | Select-Object -Unique) -join "; "
  throw "Inno Setup compiler (ISCC.exe) tidak ditemukan. Install Inno Setup 6 dari https://jrsoftware.org/isdl.php atau jalankan: winget install --id JRSoftware.InnoSetup -e. Searched: $searched"
}

$distDir = Join-Path $PSScriptRoot "dist"
$exeDist = Join-Path $distDir "silukman_file_converter.exe"
$exeOptimized = Join-Path $distDir "silukman_file_converter_optimized.exe"
$exeRoot = Join-Path $PSScriptRoot "silukman_file_converter.exe"

if (-not (Test-Path $distDir)) {
  New-Item -ItemType Directory -Path $distDir | Out-Null
}

if (Test-Path $exeOptimized) {
  Copy-Item $exeOptimized $exeDist -Force
} elseif (-not (Test-Path $exeDist)) {
  if (Test-Path $exeRoot) {
    Copy-Item $exeRoot $exeDist -Force
  } else {
    throw "EXE tidak ditemukan. Expected: $exeOptimized, $exeDist atau $exeRoot"
  }
}

$summaryDir = Join-Path $PSScriptRoot "summary"
if (-not (Test-Path $summaryDir)) {
  New-Item -ItemType Directory -Path $summaryDir | Out-Null
  $latestSummary = Get-ChildItem -Path (Join-Path $PSScriptRoot "output\sample_file_matrix") -Recurse -Filter "summary_exe.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($latestSummary) {
    Copy-Item $latestSummary.FullName (Join-Path $summaryDir "summary_exe.json") -Force
    $summaryMd = Join-Path $latestSummary.DirectoryName "summary.md"
    if (Test-Path $summaryMd) {
      Copy-Item $summaryMd (Join-Path $summaryDir "summary.md") -Force
    }
  }
}

& $isccPath (Join-Path $PSScriptRoot "installer\silukman_file_converter.iss")
