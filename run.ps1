$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & python -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>$null
    if ($LASTEXITCODE -eq 0) { $exe = "python"; $prefix = @() }
}
if (-not $exe) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>$null
        if ($LASTEXITCODE -eq 0) { $exe = "py"; $prefix = @("-3") }
    }
}
if (-not $exe) { Write-Error "Python 3.9+ not found."; exit 1 }
$runArgs = if ($args.Count -eq 0) { @("--interactive") } else { $args }
& $exe @prefix "pull_whop.py" @runArgs
exit $LASTEXITCODE
