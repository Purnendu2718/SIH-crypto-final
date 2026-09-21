@echo off
title CryptoTrace Sentinel (SIH26183) — Host Launcher
color 0A

echo ==============================================================================
echo       CryptoTrace Sentinel (SIH26183) — Launching System
echo       Real-Time Fraud-Linked Cryptocurrency Exchange Identification
echo       Ministry of Home Affairs / I4C
echo ==============================================================================
echo.

set ROOT_DIR=%~dp0
cd /d "%ROOT_DIR%"

echo [1/2] Launching Backend API Server on http://localhost:8000 ...
start "CryptoTrace Sentinel - Backend API" cmd /k "cd /d "%ROOT_DIR%backend" && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 /nobreak > nul

echo [2/2] Launching Frontend Web Portal on http://localhost:5173 ...
start "CryptoTrace Sentinel - Frontend Web" cmd /k "cd /d "%ROOT_DIR%frontend" && npm run dev -- --host 0.0.0.0 --port 5173"

echo.
echo ==============================================================================
echo  Services started in separate background consoles!
echo  - Frontend Portal:  http://localhost:5173
echo  - Backend API:      http://localhost:8000
echo  - API Docs:         http://localhost:8000/docs
echo ==============================================================================
echo.
pause
