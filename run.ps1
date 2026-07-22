# Move to this script's own folder, then run the fetcher.
Set-Location -Path $PSScriptRoot

try {
    python pull_whop.py
} catch {
    Write-Host "[!] python not found, trying py launcher..."
    py pull_whop.py
}

Write-Host ""
Read-Host "Done. Press Enter to close"
