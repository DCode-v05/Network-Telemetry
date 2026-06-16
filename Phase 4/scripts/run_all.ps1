# Phase 4 -- end-to-end pipeline: data -> sweep -> C build/bench -> merge -> selection -> figures -> tests
# Usage:  powershell -NoProfile -File scripts\run_all.ps1            (full run)
#         powershell -NoProfile -File scripts\run_all.ps1 -Quick     (smoke run)
param([switch]$Quick, [int]$Seeds = 10)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot          # ...\Phase 4
$py = Join-Path $root "src\python"
$env:PYTHONUNBUFFERED = "1"

Write-Host "== 1/6 ensure real datasets ==" -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $root "data\real\nab\combined_windows.json"))) {
    python (Join-Path $root "scripts\download_data.py")
} else { Write-Host "  real data present" }

Write-Host "== 2/6 evaluation sweep ==" -ForegroundColor Cyan
Push-Location $py
try {
    if ($Quick) { python -m eval.sweep_runner --quick }
    else { python -m eval.sweep_runner --seeds $Seeds }
} finally { Pop-Location }

Write-Host "== 3/6 build + benchmark C twin ==" -ForegroundColor Cyan
$build = Join-Path $root "src\c\build.ps1"
if (Test-Path $build) {
    & $build
    $bench = Join-Path $root "src\c\build\bench.exe"
    if (Test-Path $bench) { & $bench | Out-Null; Write-Host "  c_cost.csv written" }
    else { Write-Host "  bench.exe not found; skipping C cost" -ForegroundColor Yellow }
} else { Write-Host "  src\c\build.ps1 missing; skipping C (Python cost only)" -ForegroundColor Yellow }

Write-Host "== 4/6 merge C cost ==" -ForegroundColor Cyan
python (Join-Path $root "scripts\merge_cost.py")

Write-Host "== 5/6 selection (choose the best) ==" -ForegroundColor Cyan
Push-Location $py; try { python -m selection.select } finally { Pop-Location }

Write-Host "== 6/6 figures + dashboard sync + tests ==" -ForegroundColor Cyan
Push-Location $py; try { python -m eval.figures } finally { Pop-Location }
& (Join-Path $root "scripts\sync_dashboard.ps1")
python -m pytest (Join-Path $root "tests") -q

Write-Host "`nPhase 4 pipeline complete. See results\selection.json and report\." -ForegroundColor Green
