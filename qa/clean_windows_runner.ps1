param(
    [string]$ExePath = "",
    [string]$SamplesPath = "",
    [string]$OutputRoot = "",
    [int]$LaunchSeconds = 5,
    [int]$OperationTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RootDir "output\production_qa"
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$EvidenceDir = Join-Path $OutputRoot "evidence\clean_windows"
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

function NowIso {
    return (Get-Date).ToString("s")
}

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return "" }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

function Save-Json($Path, $Data) {
    $Data | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function New-Check([string]$Id, [string]$Name, [string]$Status, [string]$Evidence, [string]$Notes, $Details = @{}) {
    return [ordered]@{
        id = $Id
        name = $Name
        status = $Status
        evidence = $Evidence
        timestamp = NowIso
        notes = $Notes
        details = $Details
    }
}

function Resolve-Exe {
    param([string]$Requested)
    $candidates = @()
    if ($Requested) { $candidates += $Requested }
    $candidates += Join-Path $RootDir "dist\silukman_file_converter.exe"
    $candidates += Join-Path $RootDir "dist\silukman_file_converter_optimized.exe"
    $candidates += Join-Path $RootDir "silukman_file_converter.exe"
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }
    return [System.IO.Path]::GetFullPath($candidates[0])
}

function Resolve-Samples {
    param([string]$Requested)
    if ($Requested) { return [System.IO.Path]::GetFullPath($Requested) }
    return [System.IO.Path]::GetFullPath((Join-Path $RootDir "samples"))
}

function Get-CommandSource([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return ""
}

function Capture-Screenshot([string]$Path) {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
        $graphics.Dispose()
        $bitmap.Dispose()
        return [ordered]@{ success = $true; path = $Path; error = "" }
    } catch {
        return [ordered]@{ success = $false; path = $Path; error = $_.Exception.Message }
    }
}

function Find-DependencyError($Text) {
    $patterns = @(
        "missing dll",
        "dll load failed",
        "failed to load",
        "module could not be found",
        "no module named",
        "importerror",
        "modulenotfounderror",
        "vcruntime",
        "msvcp",
        "api-ms-win",
        "traceback"
    )
    $lower = ($Text | Out-String).ToLowerInvariant()
    foreach ($pattern in $patterns) {
        if ($lower.Contains($pattern)) { return $pattern }
    }
    return ""
}

function Stop-ProcessTree([int]$TargetPid) {
    if ($TargetPid -le 0) { return }
    cmd.exe /c "taskkill /PID $TargetPid /T /F >NUL 2>NUL" | Out-Null
}

function Get-ExePids([string]$Exe) {
    $items = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $Exe }
    return @($items | Select-Object -ExpandProperty Id)
}

function Quote-Arg([string]$Value) {
    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

function Invoke-ProcessWithTimeout {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds,
        [string]$StdoutPath,
        [string]$StderrPath
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = (($Arguments | ForEach-Object { Quote-Arg $_ }) -join " ")
    $psi.WorkingDirectory = $RootDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    $started = Get-Date
    [void]$proc.Start()
    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    $finished = $proc.WaitForExit($TimeoutSeconds * 1000)
    $timedOut = -not $finished
    if ($timedOut) {
        Stop-ProcessTree -TargetPid $proc.Id
        try { $proc.WaitForExit(5000) | Out-Null } catch {}
    }
    $elapsed = ((Get-Date) - $started).TotalSeconds
    $stdout = ""
    $stderr = ""
    try { $stdout = $stdoutTask.Result } catch {}
    try { $stderr = $stderrTask.Result } catch {}
    Set-Content -LiteralPath $StdoutPath -Value $stdout -Encoding UTF8
    Set-Content -LiteralPath $StderrPath -Value $stderr -Encoding UTF8
    $exitCode = $null
    if (-not $timedOut) { $exitCode = $proc.ExitCode }
    return [ordered]@{
        command = @($FilePath) + $Arguments
        process_id = $proc.Id
        exit_code = $exitCode
        timed_out = $timedOut
        elapsed_seconds = [Math]::Round($elapsed, 3)
        stdout = $StdoutPath
        stderr = $StderrPath
        dependency_error = Find-DependencyError ($stdout + "`n" + $stderr)
    }
}

function Launch-And-Observe {
    param([string]$Exe, [int]$Seconds)
    $beforePids = @(Get-ExePids -Exe $Exe)
    $started = Get-Date
    $proc = Start-Process -FilePath $Exe -WorkingDirectory $RootDir -PassThru
    Start-Sleep -Seconds $Seconds
    $screenshotPath = Join-Path $EvidenceDir ("screenshot_launch_{0}.png" -f (Get-Date -Format "yyyyMMddHHmmss"))
    $screenshot = Capture-Screenshot -Path $screenshotPath
    $afterPids = @(Get-ExePids -Exe $Exe)
    $newPids = @($afterPids | Where-Object { $beforePids -notcontains $_ })
    $hasExited = $proc.HasExited
    $elapsed = ((Get-Date) - $started).TotalSeconds
    $exitCode = $null
    if ($hasExited) { $exitCode = $proc.ExitCode }
    if (-not $hasExited) {
        Stop-ProcessTree -TargetPid $proc.Id
    }
    foreach ($newPid in $newPids) {
        Stop-ProcessTree -TargetPid $newPid
    }
    return [ordered]@{
        process_id = $proc.Id
        new_process_ids = $newPids
        observed_seconds = $Seconds
        launch_elapsed_seconds = [Math]::Round($elapsed, 3)
        stayed_alive = (-not $hasExited)
        exit_code = $exitCode
        screenshot = $screenshot
    }
}

function Find-SmokeSample([string]$Samples) {
    if (-not (Test-Path -LiteralPath $Samples)) { return $null }
    $preferredNames = @(
        "sample_add_html.html",
        "sample_add_csv.csv",
        "sample_add_png.png",
        "sample_add_pdf.pdf"
    )
    foreach ($name in $preferredNames) {
        $preferred = Join-Path $Samples $name
        if (Test-Path -LiteralPath $preferred) { return (Resolve-Path -LiteralPath $preferred).Path }
    }
    $extensions = @("*.html", "*.htm", "*.csv", "*.png", "*.jpg", "*.jpeg", "*.pdf")
    foreach ($extension in $extensions) {
        $files = Get-ChildItem -LiteralPath $Samples -Recurse -File -Filter $extension |
            Where-Object { $_.FullName -notmatch "\\07_expected_results\\" } |
            Sort-Object FullName
        if ($files.Count -gt 0) { return $files[0].FullName }
    }
    return $null
}

function Get-SmokeOperation([string]$Path) {
    $extension = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    switch ($extension) {
        ".html" { return "html_to_pdf" }
        ".htm" { return "html_to_pdf" }
        ".csv" { return "csv_to_excel" }
        ".png" { return "image_to_pdf" }
        ".jpg" { return "image_to_pdf" }
        ".jpeg" { return "image_to_pdf" }
        ".pdf" { return "pdf_to_png" }
        default { return "" }
    }
}

function Get-RelativePath([string]$Base, [string]$Path) {
    $baseUri = [System.Uri](([System.IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'))
    $pathUri = [System.Uri]([System.IO.Path]::GetFullPath($Path))
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace('/', '\')
}

$Exe = Resolve-Exe -Requested $ExePath
$Samples = Resolve-Samples -Requested $SamplesPath
$Checks = New-Object System.Collections.Generic.List[object]

$machine = [ordered]@{
    computer_name = $env:COMPUTERNAME
    user_name = $env:USERNAME
    os = (Get-CimInstance Win32_OperatingSystem | Select-Object -ExpandProperty Caption)
    os_version = (Get-CimInstance Win32_OperatingSystem | Select-Object -ExpandProperty Version)
    architecture = $env:PROCESSOR_ARCHITECTURE
    powershell_version = $PSVersionTable.PSVersion.ToString()
}

$pythonEvidencePath = Join-Path $EvidenceDir "python_detection.json"
$pythonEvidence = [ordered]@{
    python = Get-CommandSource "python"
    py = Get-CommandSource "py"
    python3 = Get-CommandSource "python3"
    pip = Get-CommandSource "pip"
    pip3 = Get-CommandSource "pip3"
    path = $env:PATH
}
Save-Json $pythonEvidencePath $pythonEvidence
$pythonDetected = [bool]($pythonEvidence.python -or $pythonEvidence.py -or $pythonEvidence.python3 -or $pythonEvidence.pip -or $pythonEvidence.pip3)
$Checks.Add((New-Check "python_path_detection" "Python in PATH detection" ($(if ($pythonDetected) { "blocked" } else { "pass" })) $pythonEvidencePath ($(if ($pythonDetected) { "Python launcher/interpreter detected in PATH." } else { "No Python command detected in PATH." })) $pythonEvidence))

$artifactEvidencePath = Join-Path $EvidenceDir "developer_artifacts.json"
$artifactNames = @("venv", ".venv", ".venv_ocr", "build", ".git", ".pytest_cache", "__pycache__")
$artifacts = @()
foreach ($name in $artifactNames) {
    $path = Join-Path $RootDir $name
    if (Test-Path -LiteralPath $path) { $artifacts += $path }
}
$artifactEvidence = [ordered]@{
    root = $RootDir
    artifacts = $artifacts
}
Save-Json $artifactEvidencePath $artifactEvidence
$Checks.Add((New-Check "developer_artifacts" "Developer artifact detection" ($(if ($artifacts.Count -gt 0) { "blocked" } else { "pass" })) $artifactEvidencePath ($(if ($artifacts.Count -gt 0) { "Virtualenv/build/cache developer artifacts detected near runner." } else { "No virtualenv/build/cache developer artifacts detected near runner." })) $artifactEvidence))

$exeEvidencePath = Join-Path $EvidenceDir "exe_artifact.json"
$exeEvidence = [ordered]@{
    exe = $Exe
    exists = (Test-Path -LiteralPath $Exe)
    size_bytes = $(if (Test-Path -LiteralPath $Exe) { (Get-Item -LiteralPath $Exe).Length } else { 0 })
    sha256 = Get-Sha256 $Exe
}
Save-Json $exeEvidencePath $exeEvidence
$Checks.Add((New-Check "exe_artifact" "EXE artifact exists" ($(if ($exeEvidence.exists) { "pass" } else { "fail" })) $exeEvidencePath ($(if ($exeEvidence.exists) { "EXE artifact found and hashed." } else { "EXE artifact not found." })) $exeEvidence))

$launchEvidencePath = Join-Path $EvidenceDir "exe_launch.json"
if ($exeEvidence.exists) {
    $launchEvidence = Launch-And-Observe -Exe $Exe -Seconds $LaunchSeconds
    Save-Json $launchEvidencePath $launchEvidence
    $Checks.Add((New-Check "exe_launch" "EXE launch" ($(if ($launchEvidence.stayed_alive) { "pass" } else { "fail" })) $launchEvidencePath ($(if ($launchEvidence.stayed_alive) { "EXE launched and stayed alive during observation." } else { "EXE exited during observation." })) $launchEvidence))
} else {
    Save-Json $launchEvidencePath @{ error = "EXE missing" }
    $Checks.Add((New-Check "exe_launch" "EXE launch" "fail" $launchEvidencePath "EXE missing."))
}

$startupEvidencePath = Join-Path $EvidenceDir "startup.json"
if ($exeEvidence.exists) {
    $startup = Launch-And-Observe -Exe $Exe -Seconds 2
    Save-Json $startupEvidencePath $startup
    $Checks.Add((New-Check "startup" "Startup observation" ($(if ($startup.stayed_alive -and $startup.launch_elapsed_seconds -le 10) { "pass" } else { "fail" })) $startupEvidencePath "Startup observed with threshold <= 10 seconds." $startup))
} else {
    Save-Json $startupEvidencePath @{ error = "EXE missing" }
    $Checks.Add((New-Check "startup" "Startup observation" "fail" $startupEvidencePath "EXE missing."))
}

$dllEvidencePath = Join-Path $EvidenceDir "dll_loading.json"
if ($exeEvidence.exists) {
    $dllProbe = Launch-And-Observe -Exe $Exe -Seconds 3
    Save-Json $dllEvidencePath $dllProbe
    $Checks.Add((New-Check "dll_loading" "DLL loading smoke check" ($(if ($dllProbe.stayed_alive) { "pass" } else { "fail" })) $dllEvidencePath ($(if ($dllProbe.stayed_alive) { "No immediate missing-DLL crash observed during launch." } else { "EXE exited immediately; possible missing dependency or startup failure." })) $dllProbe))
} else {
    Save-Json $dllEvidencePath @{ error = "EXE missing" }
    $Checks.Add((New-Check "dll_loading" "DLL loading smoke check" "fail" $dllEvidencePath "EXE missing."))
}

$outputEvidencePath = Join-Path $EvidenceDir "output_creation.json"
$smokeSample = Find-SmokeSample -Samples $Samples
if ($exeEvidence.exists -and $smokeSample) {
    $matrixOut = Join-Path $EvidenceDir ("sample_matrix_output_{0}" -f (Get-Date -Format "yyyyMMddHHmmss"))
    $smokeSamples = Join-Path $EvidenceDir ("smoke_samples_{0}" -f (Get-Date -Format "yyyyMMddHHmmss"))
    if (Test-Path -LiteralPath $matrixOut) { Remove-Item -LiteralPath $matrixOut -Recurse -Force }
    if (Test-Path -LiteralPath $smokeSamples) { Remove-Item -LiteralPath $smokeSamples -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $matrixOut | Out-Null
    New-Item -ItemType Directory -Force -Path $smokeSamples | Out-Null
    $stdoutPath = Join-Path $EvidenceDir "output_creation.stdout.log"
    $stderrPath = Join-Path $EvidenceDir "output_creation.stderr.log"
    $smokeName = Split-Path -Leaf $smokeSample
    $smokeCopy = Join-Path $smokeSamples $smokeName
    Copy-Item -LiteralPath $smokeSample -Destination $smokeCopy -Force
    $smokeOperation = Get-SmokeOperation -Path $smokeCopy
    $run = Invoke-ProcessWithTimeout -FilePath $Exe -Arguments @(
        "--sample-matrix",
        "--samples", $smokeSamples,
        "--output", $matrixOut,
        "--source-label", "clean-windows-vm",
        "--matrix-op", $smokeOperation,
        "--matrix-input", $smokeName
    ) -TimeoutSeconds $OperationTimeoutSeconds -StdoutPath $stdoutPath -StderrPath $stderrPath
    $summaryFiles = Get-ChildItem -LiteralPath $matrixOut -Recurse -File -Filter "summary.json" -ErrorAction SilentlyContinue
    $createdOutputs = Get-ChildItem -LiteralPath $matrixOut -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\output\\" } |
        Select-Object -ExpandProperty FullName
    $outputEvidence = [ordered]@{
        sample = $smokeSample
        smoke_samples = $smokeSamples
        smoke_sample = $smokeCopy
        smoke_operation = $smokeOperation
        matrix_output = $matrixOut
        process = $run
        summary_files = @($summaryFiles | Select-Object -ExpandProperty FullName)
        created_outputs = @($createdOutputs)
        dependency_error = $run.dependency_error
    }
    Save-Json $outputEvidencePath $outputEvidence
    $outputStatus = if (($run.exit_code -eq 0) -and (@($createdOutputs).Count -gt 0) -and (-not $run.dependency_error)) { "pass" } else { "fail" }
    $outputNotes = if ($outputStatus -eq "pass") { "EXE CLI operation created output files and no dependency error was detected." } else { "EXE CLI operation did not create output files or dependency error was detected." }
    $Checks.Add((New-Check "output_creation" "Output creation" $outputStatus $outputEvidencePath $outputNotes $outputEvidence))
} else {
    $reason = if (-not $exeEvidence.exists) { "EXE missing." } else { "No supported smoke sample found." }
    Save-Json $outputEvidencePath @{ reason = $reason; samples = $Samples }
    $Checks.Add((New-Check "output_creation" "Output creation" "blocked" $outputEvidencePath $reason))
}

$cleanEvidencePath = Join-Path $EvidenceDir "clean_windows_decision.json"
$cleanDetails = [ordered]@{
    python_detected = $pythonDetected
    developer_artifacts = $artifacts
    exe_launch_pass = ($Checks | Where-Object { $_.id -eq "exe_launch" } | Select-Object -First 1).status -eq "pass"
    dll_loading_pass = ($Checks | Where-Object { $_.id -eq "dll_loading" } | Select-Object -First 1).status -eq "pass"
    output_creation_pass = ($Checks | Where-Object { $_.id -eq "output_creation" } | Select-Object -First 1).status -eq "pass"
}
$cleanStatus = if ($pythonDetected) {
    "blocked"
} elseif ($artifacts.Count -gt 0) {
    "blocked"
} elseif ($cleanDetails.exe_launch_pass -and $cleanDetails.dll_loading_pass -and $cleanDetails.output_creation_pass) {
    "pass"
} else {
    "fail"
}
$cleanNotes = if ($cleanStatus -eq "blocked") {
    "Python/pip or developer artifacts exist, so this is not proven clean Windows."
} elseif ($cleanStatus -eq "pass") {
    "No Python/pip in PATH, no developer artifacts, EXE launch/DLL/output checks passed."
} else {
    "No Python/pip in PATH, but one or more EXE runtime checks did not pass."
}
Save-Json $cleanEvidencePath $cleanDetails
$Checks.Add((New-Check "clean_windows_no_python" "Clean Windows no-Python decision" $cleanStatus $cleanEvidencePath $cleanNotes $cleanDetails))

$summary = [ordered]@{ pass = 0; fail = 0; blocked = 0 }
foreach ($check in $Checks) {
    $summary[$check.status] = [int]$summary[$check.status] + 1
}
$decision = if ($summary.fail -gt 0) {
    "FAILED"
} elseif ($summary.blocked -gt 0) {
    "BLOCKED"
} else {
    "PASS"
}

$result = [ordered]@{
    schema_version = 1
    app = "silukman_file_converter"
    qa_type = "clean_windows_validation"
    created_at = NowIso
    root = $RootDir
    exe = $Exe
    samples = $Samples
    output_root = $OutputRoot
    evidence_dir = $EvidenceDir
    machine_info = $machine
    summary = $summary
    decision = $decision
    checks = $Checks
    rule = "If Python exists in PATH, clean Windows validation is blocked. If no Python exists and EXE launches, clean Windows launch validation can pass."
}

$resultPath = Join-Path $OutputRoot "clean_windows_validation.json"
Save-Json $resultPath $result

$mdPath = Join-Path $OutputRoot "clean_windows_validation.md"
$lines = @(
    "# Clean Windows Validation",
    "",
    "Decision: ``$decision``",
    "",
    "EXE: ``$Exe``",
    "Evidence: ``$EvidenceDir``",
    "",
    "## Summary",
    "",
    "- pass: $($summary.pass)",
    "- fail: $($summary.fail)",
    "- blocked: $($summary.blocked)",
    "",
    "## Checks",
    "",
    "| check | status | evidence | notes |",
    "| --- | --- | --- | --- |"
)
foreach ($check in $Checks) {
    $lines += "| $($check.name) | $($check.status) | $($check.evidence) | $($check.notes) |"
}
$lines | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Host "Clean Windows validation written:"
Write-Host "  $resultPath"
Write-Host "  $mdPath"
Write-Host "Decision: $decision"

if ($decision -eq "PASS") { exit 0 }
if ($decision -eq "BLOCKED") { exit 2 }
exit 1
