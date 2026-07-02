# sync_data.ps1 -- copy the pipeline result JSONs into the dashboard's public/data.
# The React app fetches these at runtime. Run after run_demo.py --all and collect_c_results.py.

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$results = Join-Path $here '..\results'
$dest = Join-Path $here 'public\data'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$files = 'synthetic_results.json', 'nab_results.json', 'c_results.json'
foreach ($f in $files) {
    $src = Join-Path $results $f
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $dest $f) -Force
        Write-Host "  synced $f"
    } else {
        Write-Host "  MISSING $f (run the pipeline first)" -ForegroundColor Yellow
    }
}
Write-Host "dashboard data ready in public\data" -ForegroundColor Green
