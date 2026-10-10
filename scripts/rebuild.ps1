<#
VisualizeBalance - one-shot rebuild (run on Windows).

ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI unless the file
has a UTF-8 BOM, which garbles non-ASCII text and breaks parsing.

Needs Python 3.8+ (3.11 / 3.12 recommended) because Pillow>=10 and PyInstaller>=6
require it. The script prefers the active interpreter (conda env / venv), then
probes the py launcher, and fails with a readable report if none qualifies.

Usage:
    powershell -ExecutionPolicy Bypass -File scripts\rebuild.ps1
    powershell -ExecutionPolicy Bypass -File scripts\rebuild.ps1 -SkipDeps
    powershell -ExecutionPolicy Bypass -File scripts\rebuild.ps1 -SkipInstaller

Force a specific interpreter:
    $env:VB_PYTHON = "C:\Python312\python.exe"

Outputs:
    dist\VisualizeBalance.exe                     (always)
    scripts\Output\VisualizeBalance-Setup.exe     (needs Inno Setup)
#>
[CmdletBinding()]
param(
    [switch]$SkipDeps,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$MinMajor = 3
$MinMinor = 8

function Step($msg) {
    Write-Host ""
    Write-Host ("==> " + $msg) -ForegroundColor Cyan
}

function Get-PyVersion {
    param([string]$Exe, [string[]]$Pre = @())

    $a = @()
    if ($Pre) { $a += $Pre }
    $a += @("-c", "import sys;print('%d.%d'%sys.version_info[:2])")

    $saved = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = $null
    try { $out = & $Exe @a 2>$null } catch { $out = $null }
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $saved

    if ($rc -eq 0 -and $out) { return ([string]$out).Trim() }
    return $null
}

function Test-VersionOk($ver) {
    if (-not $ver) { return $false }
    $parts = $ver.Split(".")
    $maj = [int]$parts[0]
    $min = [int]$parts[1]
    if ($maj -gt $MinMajor) { return $true }
    if ($maj -eq $MinMajor -and $min -ge $MinMinor) { return $true }
    return $false
}

# ---------------------------------------------------------------- 1. Python
Step ("Locating a suitable Python (>= " + $MinMajor + "." + $MinMinor + ")")

$candidates = @()
if ($env:VB_PYTHON) { $candidates += ,@($env:VB_PYTHON, @()) }
$candidates += ,@("python", @())
foreach ($v in @("3.13", "3.12", "3.11", "3.10", "3.9", "3.8")) {
    $candidates += ,@("py", @("-" + $v))
}

$pythonExe = $null
$pythonArgs = @()
$pythonVer = $null
$report = @()

foreach ($cand in $candidates) {
    $exe = $cand[0]
    $pre = $cand[1]
    $label = ($exe + " " + ($pre -join " ")).Trim()

    $ver = Get-PyVersion -Exe $exe -Pre $pre
    if ($ver) { $report += ("{0}  ->  Python {1}" -f $label, $ver) }

    if ($ver -and (Test-VersionOk $ver)) {
        $pythonExe = $exe
        $pythonArgs = $pre
        $pythonVer = $ver
        break
    }
}

if (-not $pythonExe) {
    Write-Host "Interpreters detected:"
    if ($report.Count -eq 0) { Write-Host "  (none)" } else { $report | ForEach-Object { Write-Host ("  " + $_) } }
    Write-Host ""
    Write-Host "Registered launchers (py -0p):"
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -0p } else { Write-Host "  py launcher not available" }
    Write-Host ""
    throw ("No usable Python >= " + $MinMajor + "." + $MinMinor + " found. Pillow>=10 and PyInstaller>=6 both need it.")
}

$pyPath = (& $pythonExe @pythonArgs -c "import sys;print(sys.executable)")
Write-Host ("Using Python {0}  ({1})" -f $pythonVer, ([string]$pyPath).Trim()) -ForegroundColor Green
if ($report.Count -gt 0) { $report | ForEach-Object { Write-Host ("  " + $_) -ForegroundColor DarkGray } }

# ---------------------------------------------------------------- 2. deps
if ($SkipDeps) {
    Write-Host "Skipping dependency install (-SkipDeps)."
} else {
    Step "Installing dependencies (requirements.txt)"
    & $pythonExe @pythonArgs -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency install failed." }
}

# ---------------------------------------------------------------- 3. exe
Step "Building exe with PyInstaller"
& $pythonExe @pythonArgs (Join-Path $Root "scripts\build.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$exePath = Join-Path $Root "dist\VisualizeBalance.exe"
if (-not (Test-Path $exePath)) { throw ("Build output missing: " + $exePath) }

$exeInfo = Get-Item $exePath
$exeMb = [math]::Round($exeInfo.Length / 1MB, 1)
Write-Host ("exe ready: {0}  ({1} MB, {2})" -f $exePath, $exeMb, $exeInfo.LastWriteTime) -ForegroundColor Green

# ---------------------------------------------------------------- 4. setup
if ($SkipInstaller) {
    Write-Host "Skipping installer build (-SkipInstaller)." -ForegroundColor Yellow
    exit 0
}

Step "Locating Inno Setup (ISCC.exe)"
$iscc = @(
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 5\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Warning "Inno Setup not found; skipping installer. dist\VisualizeBalance.exe is usable as-is."
    exit 0
}

Write-Host ("Using: " + $iscc)
& $iscc (Join-Path $Root "scripts\build.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed." }

$setupPath = Join-Path $Root "scripts\Output\VisualizeBalance-Setup.exe"
if (Test-Path $setupPath) {
    $setupInfo = Get-Item $setupPath
    $setupMb = [math]::Round($setupInfo.Length / 1MB, 1)
    Write-Host ("installer ready: {0}  ({1} MB)" -f $setupPath, $setupMb) -ForegroundColor Green
} else {
    Write-Warning ("Installer output missing: " + $setupPath)
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
