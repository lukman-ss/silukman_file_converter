param(
    [string]$ProjectRoot = "",
    [string]$SharedRoot = "",
    [switch]$ImportAfterRun,
    [int]$ShutdownDelaySeconds = 5,
    [int]$EvidenceTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if (-not $SharedRoot) {
    $SharedRoot = Join-Path $ProjectRoot "sandbox_clean_windows"
}
$SharedRoot = [System.IO.Path]::GetFullPath($SharedRoot)

function Find-WindowsSandbox {
    $cmd = Get-Command "WindowsSandbox.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidate = Join-Path $env:WINDIR "System32\WindowsSandbox.exe"
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    return ""
}

$sandboxExe = Find-WindowsSandbox
if (-not $sandboxExe) {
    $result = [ordered]@{
        decision = "BLOCKED"
        reason = "WindowsSandbox.exe not found. Windows Sandbox is not enabled or not available on this Windows edition."
        enable_command = "Start PowerShell as Administrator, then run: Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All -NoRestart; Restart-Computer"
        fallback = "Use a real clean Windows VM and run qa\clean_windows_runner.ps1 from the clean package."
    }
    $outDir = Join-Path $ProjectRoot "output\production_qa"
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $outDir "sandbox_clean_windows_result.json") -Encoding UTF8
    Write-Host "BLOCKED: WindowsSandbox.exe not found."
    Write-Host $result.enable_command
    exit 2
}

Push-Location $ProjectRoot
try {
    python tools\build_clean_windows_package.py
} finally {
    Pop-Location
}

Remove-Item -LiteralPath $SharedRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $SharedRoot -Force | Out-Null
$packageRoot = Join-Path $ProjectRoot "clean_windows_validation_package"
Get-ChildItem -LiteralPath $packageRoot -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $SharedRoot -Recurse -Force
}

$startup = Join-Path $SharedRoot "run_clean_windows_qa.ps1"
@"
`$ErrorActionPreference = "Stop"
Set-Location C:\QA
`$logRoot = "C:\QA\output\production_qa"
New-Item -ItemType Directory -Path `$logRoot -Force | Out-Null
`$log = Join-Path `$logRoot "sandbox_bootstrap.log"
"started=`$(Get-Date -Format s)" | Set-Content -LiteralPath `$log -Encoding UTF8
"pwd=`$(Get-Location)" | Add-Content -LiteralPath `$log -Encoding UTF8
"has_runner=`$(Test-Path .\qa\clean_windows_runner.ps1)" | Add-Content -LiteralPath `$log -Encoding UTF8
"has_exe=`$(Test-Path .\dist\silukman_file_converter.exe)" | Add-Content -LiteralPath `$log -Encoding UTF8
"root_items=`$((Get-ChildItem C:\QA -Force | Select-Object -ExpandProperty Name) -join ', ')" | Add-Content -LiteralPath `$log -Encoding UTF8
"dist_items=`$((Get-ChildItem C:\QA\dist -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ', ')" | Add-Content -LiteralPath `$log -Encoding UTF8
try {
    `$stdout = Join-Path `$logRoot "clean_windows_runner.stdout.log"
    `$stderr = Join-Path `$logRoot "clean_windows_runner.stderr.log"
    `$process = Start-Process -FilePath "powershell" -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", "C:\QA\qa\clean_windows_runner.ps1") -WorkingDirectory "C:\QA" -Wait -PassThru -RedirectStandardOutput `$stdout -RedirectStandardError `$stderr
    `$exitCode = `$process.ExitCode
    "runner_exit_code=`$exitCode" | Add-Content -LiteralPath `$log -Encoding UTF8
} catch {
    "runner_exception=`$(`$_.Exception.Message)" | Add-Content -LiteralPath `$log -Encoding UTF8
    `$exitCode = 1
}
"validation_exists=`$(Test-Path C:\QA\output\production_qa\clean_windows_validation.json)" | Add-Content -LiteralPath `$log -Encoding UTF8
"finished=`$(Get-Date -Format s)" | Add-Content -LiteralPath `$log -Encoding UTF8
Start-Sleep -Seconds $ShutdownDelaySeconds
shutdown /s /t 0
"@ | Set-Content -LiteralPath $startup -Encoding UTF8

$wsb = Join-Path $ProjectRoot "clean_windows_qa.wsb"
@"
<Configuration>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$SharedRoot</HostFolder>
      <SandboxFolder>C:\QA</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell -ExecutionPolicy Bypass -File C:\QA\run_clean_windows_qa.ps1</Command>
  </LogonCommand>
</Configuration>
"@ | Set-Content -LiteralPath $wsb -Encoding UTF8

Write-Host "Windows Sandbox executable: $sandboxExe"
Write-Host "Shared package folder: $SharedRoot"
Write-Host "Sandbox config: $wsb"
Write-Host "Starting Windows Sandbox. It will shut down automatically after QA."

$validation = Join-Path $SharedRoot "output\production_qa\clean_windows_validation.json"
$bootstrapLog = Join-Path $SharedRoot "output\production_qa\sandbox_bootstrap.log"

Start-Process -FilePath $sandboxExe -ArgumentList "`"$wsb`""

$started = Get-Date
while (((Get-Date) - $started).TotalSeconds -lt $EvidenceTimeoutSeconds) {
    if (Test-Path -LiteralPath $validation) {
        break
    }
    Start-Sleep -Seconds 2
}

if (-not (Test-Path -LiteralPath $validation)) {
    Write-Host "BLOCKED: Sandbox finished but validation JSON was not produced: $validation"
    if (Test-Path -LiteralPath $bootstrapLog) {
        Write-Host "Bootstrap log:"
        Get-Content -LiteralPath $bootstrapLog
    }
    exit 2
}

Write-Host "Clean Windows validation evidence:"
Write-Host "  $validation"

if ($ImportAfterRun) {
    Push-Location $ProjectRoot
    try {
        python tools\import_clean_windows_validation.py $validation
    } finally {
        Pop-Location
    }
}
