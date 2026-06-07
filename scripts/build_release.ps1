param(
    [switch]$Clean,
    [string]$PythonExe,
    [string]$BuildVenvPath = ".build-venv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Test-PythonRuntimeCommand {
    param(
        [string]$Command,
        [string[]]$PrefixArgs = @()
    )

    try {
        & $Command @($PrefixArgs + @("--version")) *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Get-PythonRuntime {
    param([string]$Requested)

    if ($Requested) {
        if (-not (Test-PythonRuntimeCommand -Command $Requested)) {
            throw "Requested Python runtime could not be started: $Requested"
        }
        return [pscustomobject]@{
            Command = $Requested
            PrefixArgs = @()
        }
    }

    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if ((Test-Path $venvPython) -and (Test-PythonRuntimeCommand -Command $venvPython)) {
        return [pscustomobject]@{
            Command = $venvPython
            PrefixArgs = @()
        }
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd -and (Test-PythonRuntimeCommand -Command $pyCmd.Source -PrefixArgs @("-3"))) {
        return [pscustomobject]@{
            Command = $pyCmd.Source
            PrefixArgs = @("-3")
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and (Test-PythonRuntimeCommand -Command $pythonCmd.Source)) {
        return [pscustomobject]@{
            Command = $pythonCmd.Source
            PrefixArgs = @()
        }
    }

    throw "Python runtime not found. Prepare .venv, py launcher, or pass -PythonExe."
}

function Ensure-BuildVenv {
    param(
        [pscustomobject]$BaseRuntime,
        [string]$VenvPath
    )

    $venvPython = Join-Path $VenvPath "Scripts\python.exe"
    if (Test-Path $venvPython) {
        if (Test-PythonRuntimeCommand -Command $venvPython) {
            return $venvPython
        }
        Remove-Item -Recurse -Force -LiteralPath $VenvPath
    }

    Write-Host ("Creating isolated build venv: {0}" -f $VenvPath)
    Invoke-PythonRuntime -Runtime $BaseRuntime -Arguments @("-m", "venv", $VenvPath)
    if (-not (Test-PythonRuntimeCommand -Command $venvPython)) {
        throw ("Failed to create working build venv: {0}" -f $VenvPath)
    }
    return $venvPython
}

function Invoke-PythonRuntime {
    param(
        [pscustomobject]$Runtime,
        [string[]]$Arguments
    )

    & $Runtime.Command @($Runtime.PrefixArgs + $Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw ("Python command failed with exit code {0}: {1} {2}" -f $LASTEXITCODE, $Runtime.Command, ($Arguments -join " "))
    }
}

function Get-TesseractBundleDir {
    $configPath = Join-Path $RepoRoot "config.json"
    $configuredTesseract = $null
    if (Test-Path $configPath) {
        try {
            $config = Get-Content -Raw -Encoding UTF8 $configPath | ConvertFrom-Json
            $configuredTesseract = $config.tesseract_path
        } catch {
        }
    }

    $candidates = @(
        (Join-Path $RepoRoot "third_party\tesseract"),
        (Join-Path $RepoRoot "vendor\tesseract"),
        (Join-Path $RepoRoot "Tesseract-OCR"),
        "C:\Program Files\Tesseract-OCR",
        "C:\Program Files (x86)\Tesseract-OCR"
    )
    if ($configuredTesseract) {
        $configuredDir = Split-Path -Parent $configuredTesseract
        if ($configuredDir) {
            $candidates = @($configuredDir) + $candidates
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate "tesseract.exe")) {
            return $candidate
        }
    }

    return $null
}

$bootstrapPython = Get-PythonRuntime -Requested $PythonExe
$resolvedBuildVenv = Join-Path $RepoRoot $BuildVenvPath
$buildVenvPython = Ensure-BuildVenv -BaseRuntime $bootstrapPython -VenvPath $resolvedBuildVenv
$python = Get-PythonRuntime -Requested $buildVenvPython
Write-Host ("Using Python: {0} {1}" -f $python.Command, ($python.PrefixArgs -join " "))

Invoke-PythonRuntime -Runtime $python -Arguments @("-m", "pip", "install", "--upgrade", "pip")
Invoke-PythonRuntime -Runtime $python -Arguments @("-m", "pip", "install", "-r", "requirements.txt", "pyinstaller")

if ($Clean) {
    foreach ($path in @("build", "dist")) {
        if (Test-Path $path) {
            Remove-Item -Recurse -Force -LiteralPath $path
        }
    }
}

$pyiArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--noconsole",
    "--name", "tbh_stats",
    "--add-data", "assets;assets",
    "--exclude-module", "pandas",
    "src/tbh_ocr_stats/app.py"
)

$tesseractDir = Get-TesseractBundleDir
if ($tesseractDir) {
    Write-Host ("Bundling Tesseract from: {0}" -f $tesseractDir)
    $pyiArgs += @("--add-data", ("{0};tesseract" -f $tesseractDir))
} else {
    Write-Warning "Bundled Tesseract directory not found. Release will rely on a local Tesseract installation."
}

Invoke-PythonRuntime -Runtime $python -Arguments $pyiArgs

$distDir = Join-Path $RepoRoot "dist\tbh_stats"
$exePath = Join-Path $distDir "tbh_stats.exe"
if (-not (Test-Path $exePath)) {
    throw ("Build finished without expected exe: {0}" -f $exePath)
}
Write-Host ""
Write-Host ("Build complete: {0}" -f $distDir)
Write-Host ("Smoke test target: {0}" -f $exePath)
