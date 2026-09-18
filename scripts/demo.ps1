[CmdletBinding()]
param([int]$Port = 8765)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$taskPython = Join-Path $taskRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $taskPython)) {
    & (Join-Path $PSScriptRoot "bootstrap.ps1")
}
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
Push-Location $taskRoot
try {
    & $taskPython -m attain_sampling demo --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Demo exited with code $LASTEXITCODE" }
} finally { Pop-Location }
