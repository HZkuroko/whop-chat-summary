$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$exe = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>$null
    if ($LASTEXITCODE -eq 0) { $exe = "python"; $prefix = @() }
}
if (-not $exe -and (Get-Command py -ErrorAction SilentlyContinue)) {
    & py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>$null
    if ($LASTEXITCODE -eq 0) { $exe = "py"; $prefix = @("-3") }
}
if (-not $exe) { Write-Error "Python 3.9+ not found."; exit 1 }
& $exe @prefix -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path "config.txt")) {
    Copy-Item "config.example.txt" "config.txt"
    Write-Host "Created config.txt. Fill in your own Cookie and channels."
} else {
    Write-Host "Kept existing config.txt unchanged."
}
Write-Host "Setup complete. Run run.bat or python pull_whop.py --interactive."
