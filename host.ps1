# CryptoTrace Sentinel (SIH26183) — PowerShell Host Launcher
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "      CryptoTrace Sentinel (SIH26183) — Launching System" -ForegroundColor Green
Write-Host "      Real-Time Fraud-Linked Cryptocurrency Exchange Identification" -ForegroundColor Gray
Write-Host "      Ministry of Home Affairs / I4C" -ForegroundColor Gray
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "[1/2] Starting Backend API Server (http://localhost:8000)..." -ForegroundColor Yellow
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-Command", "cd '$rootDir\backend'; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

Start-Sleep -Seconds 2

Write-Host "[2/2] Starting Frontend Web Portal (http://localhost:5173)..." -ForegroundColor Yellow
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-Command", "cd '$rootDir\frontend'; npm run dev -- --host 0.0.0.0 --port 5173"

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host " Services launched successfully!" -ForegroundColor Green
Write-Host " • Frontend UI: http://localhost:5173" -ForegroundColor White
Write-Host " • Backend API: http://localhost:8000" -ForegroundColor White
Write-Host " • Swagger API: http://localhost:8000/docs" -ForegroundColor White
Write-Host "==============================================================================" -ForegroundColor Cyan
