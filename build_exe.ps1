# Build BookAnalyzer.exe via PyInstaller.
# Run from project root:  powershell -ExecutionPolicy Bypass -File build_exe.ps1

Write-Host "Syncing build deps..." -ForegroundColor Cyan
uv sync --extra build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Cleaning previous build..." -ForegroundColor Cyan
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }

Write-Host "Building exe..." -ForegroundColor Cyan
uv run pyinstaller BookAnalyzer.spec --noconfirm
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Exe at: dist\BookAnalyzer.exe" -ForegroundColor Green
