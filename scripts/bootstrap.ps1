[CmdletBinding()]
param(
    [switch]$WithoutOracle
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$localUv = Join-Path $repoRoot ".tools\uv\bin\uv.exe"
if (Test-Path -LiteralPath $localUv -PathType Leaf) {
    $uvCommand = $localUv
} else {
    $uvCommand = (Get-Command uv -ErrorAction Stop).Source
}

$previousPythonInstallDir = $env:UV_PYTHON_INSTALL_DIR
$previousCacheDir = $env:UV_CACHE_DIR
$env:UV_PYTHON_INSTALL_DIR = Join-Path $repoRoot ".python"
$env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache"

Push-Location $repoRoot
try {
    & $uvCommand python install 3.11 --no-bin --no-registry
    if ($LASTEXITCODE -ne 0) {
        throw "uv python install failed with exit code $LASTEXITCODE"
    }

    $syncArguments = @("sync", "--extra", "dev")
    if (-not $WithoutOracle) {
        $syncArguments += @("--extra", "oracle")
    }
    if (Test-Path -LiteralPath (Join-Path $repoRoot "uv.lock")) {
        $syncArguments += "--locked"
    }

    & $uvCommand @syncArguments
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed with exit code $LASTEXITCODE"
    }

    & $uvCommand run attain-sampling doctor
    if ($LASTEXITCODE -ne 0) {
        throw "environment doctor failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
    if ($null -eq $previousPythonInstallDir) {
        Remove-Item Env:UV_PYTHON_INSTALL_DIR -ErrorAction SilentlyContinue
    } else {
        $env:UV_PYTHON_INSTALL_DIR = $previousPythonInstallDir
    }
    if ($null -eq $previousCacheDir) {
        Remove-Item Env:UV_CACHE_DIR -ErrorAction SilentlyContinue
    } else {
        $env:UV_CACHE_DIR = $previousCacheDir
    }
}
