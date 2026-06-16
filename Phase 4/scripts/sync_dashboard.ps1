# Copy the JSON results the dashboard consumes into dashboard/public/data/.
$root = Split-Path -Parent $PSScriptRoot
$dst = Join-Path $root "dashboard\public\data"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
foreach ($f in @("metrics.json", "selection.json")) {
    $src = Join-Path $root "results\$f"
    if (Test-Path $src) { Copy-Item $src (Join-Path $dst $f) -Force; Write-Host "copied $f" }
    else { Write-Host "missing results\$f (run the sweep + selection first)" -ForegroundColor Yellow }
}
