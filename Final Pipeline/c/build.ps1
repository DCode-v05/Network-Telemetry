# build.ps1 -- compile and verify the unified detector C twin (MinGW-w64 gcc).
#
# Steps:
#   1. pin the MinGW gcc bin on PATH
#   2. compile  parity_check.exe  and  bench.exe  (gcc -O2 -std=c99 -Wall)
#   3. generate the parity fixture from the Python reference (parity_gen.py)
#   4. run the parity check (PASS/FAIL, max |C - Python|)
#   5. run the bench (measured ns/sample + budget gate)
#
# Run from anywhere:  powershell -NoProfile -File build.ps1

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$build = Join-Path $here 'build'

# 1. MinGW gcc on PATH (WinLibs UCRT build, same as the Phase 4 twin)
$mingw = 'C:\Users\denis\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin'
$env:Path = $mingw + ';' + $env:Path
if (-not (Get-Command gcc -ErrorAction SilentlyContinue)) {
    Write-Error "gcc not found. Edit `$mingw in build.ps1 to point at your MinGW-w64 bin."
}

New-Item -ItemType Directory -Force -Path $build | Out-Null

# 2. compile
Write-Host "[1/4] compiling ..." -ForegroundColor Cyan
gcc -O2 -std=c99 -Wall (Join-Path $here 'unified.c') (Join-Path $here 'parity_check.c') -o (Join-Path $build 'parity_check.exe')
gcc -O2 -std=c99 -Wall (Join-Path $here 'unified.c') (Join-Path $here 'bench.c')         -o (Join-Path $build 'bench.exe')
Write-Host "      built parity_check.exe, bench.exe"

# 3. parity fixture from the Python reference
Write-Host "[2/4] generating parity fixture (python parity_gen.py) ..." -ForegroundColor Cyan
python (Join-Path $here 'parity_gen.py')

# 4. parity check
Write-Host "[3/4] parity check ..." -ForegroundColor Cyan
& (Join-Path $build 'parity_check.exe') (Join-Path $build 'parity_data.txt') 24
$parity = $LASTEXITCODE

# 5. bench
Write-Host "[4/4] bench ..." -ForegroundColor Cyan
& (Join-Path $build 'bench.exe')
$bench = $LASTEXITCODE

Write-Host ""
if ($parity -eq 0 -and $bench -eq 0) {
    Write-Host "ALL C CHECKS PASSED (parity + budget)." -ForegroundColor Green
    exit 0
} else {
    Write-Host "C CHECKS FAILED (parity=$parity bench=$bench)." -ForegroundColor Red
    exit 1
}
