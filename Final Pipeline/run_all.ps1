# run_all.ps1 -- one-shot end-to-end pipeline for the standalone unified detector.
#
#   1. generate demo data (synthetic all-4-types + stage 3 NAB streams)
#   2. Python streaming demo -> results/synthetic_results.json + nab_results.json
#   3. build + verify the C twin (parity PASS, bench ns/sample, budget gate)
#   4. collect C evidence -> results/c_results.json
#   5. export dashboard data: streams.json (live) + evaluation.json (40 detectors)
#   6. sync C evidence into the dashboard
#
# Then launch the dashboard:  cd dashboard ; npm install ; npm run dev
#
# Run:  powershell -NoProfile -File run_all.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "==> [1/6] demo data" -ForegroundColor Cyan
python (Join-Path $root 'python\make_demo_data.py')

Write-Host "`n==> [2/6] Python streaming demo (synthetic + NAB)" -ForegroundColor Cyan
python (Join-Path $root 'python\run_demo.py') --all --max-print 6

Write-Host "`n==> [3/6] build + verify C twin" -ForegroundColor Cyan
powershell -NoProfile -File (Join-Path $root 'c\build.ps1')

Write-Host "`n==> [4/6] collect C results" -ForegroundColor Cyan
python (Join-Path $root 'c\collect_c_results.py')

Write-Host "`n==> [5/6] export dashboard data (live streams + evaluation)" -ForegroundColor Cyan
python (Join-Path $root 'python\export_streams.py')
python (Join-Path $root 'python\export_eval.py')

Write-Host "`n==> [6/6] sync C evidence into the dashboard" -ForegroundColor Cyan
powershell -NoProfile -File (Join-Path $root 'dashboard\sync_data.ps1')

Write-Host "`nDONE. Launch the dashboard:" -ForegroundColor Green
Write-Host "  cd `"$root\dashboard`"" -ForegroundColor Green
Write-Host "  npm install   # first time only" -ForegroundColor Green
Write-Host "  npm run dev    # then open the printed http://localhost:5173/ URL" -ForegroundColor Green
Write-Host "`nFor the Live Pipeline's Python/C engines, also run (separate terminal):" -ForegroundColor Green
Write-Host "  python `"$root\server.py`"   # engine server on :8008 (JS works without it)" -ForegroundColor Green
