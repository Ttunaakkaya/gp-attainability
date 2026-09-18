[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$localUv = Join-Path $repoRoot ".tools\uv\bin\uv.exe"
if (Test-Path -LiteralPath $localUv -PathType Leaf) {
    $uvCommand = $localUv
} else {
    $uvCommand = (Get-Command uv -ErrorAction Stop).Source
}

Push-Location $repoRoot
try {
    $commands = @(
        @("ruff", "check", "."),
        @("ruff", "format", "--check", "src", "tests"),
        @("mypy", "src"),
        @("pytest", "-q", "--cov=attain_sampling", "--cov-report=term-missing")
    )
    foreach ($arguments in $commands) {
        & $uvCommand run @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "quality command failed: uv run $($arguments -join ' ')"
        }
    }
} finally {
    Pop-Location
}
