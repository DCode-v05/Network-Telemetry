# build.ps1 -- compile the C twin (parity + bench) with MinGW-w64 gcc.
# Prepends the WinLibs MinGW bin to PATH, then builds both executables into build\.

$env:Path = 'C:\Users\denis\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin;' + $env:Path

New-Item -ItemType Directory -Force -Path 'd:\Deni\Mr.Tech\Experience\Internships\HP CPP\Code\Phase 4\src\c\build' | Out-Null

gcc -O2 -std=c99 -Wall 'd:\Deni\Mr.Tech\Experience\Internships\HP CPP\Code\Phase 4\src\c\tsad.c' 'd:\Deni\Mr.Tech\Experience\Internships\HP CPP\Code\Phase 4\src\c\parity.c' -o 'd:\Deni\Mr.Tech\Experience\Internships\HP CPP\Code\Phase 4\src\c\build\parity.exe'

gcc -O2 -std=c99 -Wall 'd:\Deni\Mr.Tech\Experience\Internships\HP CPP\Code\Phase 4\src\c\tsad.c' 'd:\Deni\Mr.Tech\Experience\Internships\HP CPP\Code\Phase 4\src\c\bench.c'   -o 'd:\Deni\Mr.Tech\Experience\Internships\HP CPP\Code\Phase 4\src\c\build\bench.exe'
