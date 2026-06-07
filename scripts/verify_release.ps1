param(
    [string]$DistDir = "dist\tbh_stats"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$resolvedDist = Join-Path $RepoRoot $DistDir
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$internalDir = Join-Path $resolvedDist "_internal"
$warnFile = Join-Path $RepoRoot "build\tbh_stats\warn-tbh_stats.txt"

function Require-Path {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path $Path)) {
        $errors.Add("Missing: $Label -> $Path")
    }
}

function Get-RelevantBuildWarnings {
    param([string]$WarnFilePath)

    if (-not (Test-Path $WarnFilePath)) {
        return @()
    }

    $ignorePatterns = @(
        "*missing module named pwd*",
        "*missing module named grp*",
        "*missing module named _posix*",
        "*missing module named fcntl*",
        "*missing module named termios*",
        "*missing module named posix*",
        "*missing module named resource*",
        "*missing module named _scproxy*",
        "*missing module named pyimod02_importers*",
        "*missing module named readline*",
        "*missing module named olefile*",
        "*missing module named pandas - imported by pytesseract*",
        "*excluded module named pandas*",
        "*missing module named psutil - imported by numpy.testing*",
        "*missing module named multiprocessing.*",
        "*missing module named numpy._core*",
        "*missing module named numpy_distutils*",
        "*missing module named 'numpy_distutils.*",
        "*missing module named numpy.random*",
        "*missing module named typing_extensions*",
        "*missing module named charset_normalizer*",
        "*missing module named yaml*",
        "*missing module named _typeshed*",
        "*missing module named _dummy_thread*",
        "*missing module named threadpoolctl*",
        "*missing module named win32pdh*",
        "*missing module named vms_lib*",
        "*missing module named 'java.lang'*",
        "*missing module named java - imported by platform*",
        "*missing module named _winreg*",
        "*missing module named asyncio.DefaultEventLoopPolicy*",
        "*missing module named defusedxml*",
        "*excluded module named _frozen_importlib*",
        "*missing module named _frozen_importlib_external*",
        "*missing module named numpy._distributor_init_local*"
    )

    $rawLines = Get-Content -Encoding UTF8 $WarnFilePath
    $result = @()
    foreach ($line in $rawLines) {
        if ($line -notmatch "^(missing|excluded|runtime) module named") {
            continue
        }
        $ignored = $false
        foreach ($pattern in $ignorePatterns) {
            if ($line -like $pattern) {
                $ignored = $true
                break
            }
        }
        if (-not $ignored) {
            $result += $line
        }
    }
    return $result
}

Require-Path -Path $resolvedDist -Label "release folder"
Require-Path -Path (Join-Path $resolvedDist "tbh_stats.exe") -Label "main exe"
if (Test-Path $internalDir) {
    Require-Path -Path (Join-Path $internalDir "assets") -Label "assets folder"
    Require-Path -Path (Join-Path $internalDir "assets\default_anchor_gold.png") -Label "default anchor asset"
    Require-Path -Path (Join-Path $internalDir "assets\default_boss_icon.png") -Label "default boss asset"
} else {
    Require-Path -Path (Join-Path $resolvedDist "assets") -Label "assets folder"
    Require-Path -Path (Join-Path $resolvedDist "assets\default_anchor_gold.png") -Label "default anchor asset"
    Require-Path -Path (Join-Path $resolvedDist "assets\default_boss_icon.png") -Label "default boss asset"
}

$tesseractCandidates = @(
    (Join-Path $resolvedDist "tesseract.exe"),
    (Join-Path $resolvedDist "tesseract\tesseract.exe"),
    (Join-Path $resolvedDist "Tesseract-OCR\tesseract.exe"),
    (Join-Path $internalDir "tesseract.exe"),
    (Join-Path $internalDir "tesseract\tesseract.exe"),
    (Join-Path $internalDir "Tesseract-OCR\tesseract.exe")
)
if (-not ($tesseractCandidates | Where-Object { Test-Path $_ })) {
    $warnings.Add("Bundled Tesseract was not found in the release folder.")
}

$relevantBuildWarnings = @(Get-RelevantBuildWarnings -WarnFilePath $warnFile)

if ($errors.Count -gt 0) {
    foreach ($line in $errors) {
        Write-Error $line
    }
    exit 1
}

Write-Host "Release layout looks valid: $resolvedDist"
foreach ($line in $warnings) {
    Write-Warning $line
}

if ($relevantBuildWarnings.Count -gt 0) {
    Write-Warning "Build warnings that still deserve review:"
    foreach ($line in $relevantBuildWarnings) {
        Write-Warning ("  " + $line)
    }
} else {
    Write-Host "No app-specific build warnings remain after filtering known optional noise."
}

Write-Host ""
Write-Host "Manual smoke checklist:"
Write-Host "1. Launch tbh_stats.exe on a clean Windows machine."
Write-Host "2. Confirm no console window appears."
Write-Host "3. Open ROI/OCR tab and run OCR test."
Write-Host "4. Confirm config.json and data\\ are created next to the exe after use."
