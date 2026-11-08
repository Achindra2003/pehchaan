@echo off
setlocal enabledelayedexpansion

REM Pehchaan Unified Runner Script for Windows CMD
REM Handles dependencies, environment setup, model downloads, logging, and launching services.

set "ROOT_DIR=%~dp0"
set "LOG_DIR=%ROOT_DIR%logs"
set "API_DIR=%ROOT_DIR%api"
set "WEB_DIR=%ROOT_DIR%web"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "API_LOG=%LOG_DIR%\api.log"
set "WEB_LOG=%LOG_DIR%\web.log"
set "MAIN_LOG=%LOG_DIR%\run.log"

echo ========================================
echo    Pehchaan - Windows Runner Script
echo ========================================
echo Logs directory: %LOG_DIR%
echo [%date% %time%] Starting Pehchaan runner... > "%MAIN_LOG%"

REM 1. Check prerequisites
echo Checking required system tools...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 'uv' is not found. Please install uv: https://astral.sh/uv
    echo [%date% %time%] Error: uv not found >> "%MAIN_LOG%"
    exit /b 1
)

where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 'npm' is not found. Please install Node.js: https://nodejs.org/
    echo [%date% %time%] Error: npm not found >> "%MAIN_LOG%"
    exit /b 1
)
echo [OK] uv and npm found.

REM 2. Environment file check
if not exist "%API_DIR%\.env" (
    if exist "%ROOT_DIR%\.env.example" (
        echo Copying .env.example to api\.env...
        copy "%ROOT_DIR%\.env.example" "%API_DIR%\.env" >nul
        echo [OK] Created api\.env
    )
) else (
    echo [OK] api\.env exists.
)

REM 3. Python backend dependencies
echo Syncing backend Python virtual environment...
cd /d "%API_DIR%"
call uv sync >> "%MAIN_LOG%" 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uv sync failed. Check %MAIN_LOG% for details.
    cd /d "%ROOT_DIR%"
    exit /b 1
)
echo [OK] Backend dependencies synced.

REM 4. Download models
echo Checking ONNX models...
call uv run python scripts\download_models.py >> "%MAIN_LOG%" 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Model download/check failed. Check %MAIN_LOG% for details.
    cd /d "%ROOT_DIR%"
    exit /b 1
)
echo [OK] Models ready.

REM 5. Frontend dependencies
if not exist "%WEB_DIR%\node_modules" (
    echo Installing web dependencies...
    cd /d "%WEB_DIR%"
    call npm install >> "%MAIN_LOG%" 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed. Check %MAIN_LOG% for details.
        cd /d "%ROOT_DIR%"
        exit /b 1
    )
    echo [OK] Web packages installed.
) else (
    echo [OK] web\node_modules exists.
)

REM 6. Start API server in background
echo Starting Backend API (port 8000)...
cd /d "%API_DIR%"
start "Pehchaan API Server" /B cmd /c "uv run uvicorn pehchaan.main:app_factory --factory --reload --port 8000 > ""%API_LOG%"" 2>&1"

REM Wait briefly for backend initialization
timeout /t 3 /nobreak >nul

REM 7. Start Frontend server in background
echo Starting Frontend Web Dev Server (port 5173)...
cd /d "%WEB_DIR%"
start "Pehchaan Web Client" /B cmd /c "npm run dev -- --host 0.0.0.0 > ""%WEB_LOG%"" 2>&1"

cd /d "%ROOT_DIR%"

echo.
echo ======================================================
echo    Pehchaan services started!
echo ======================================================
echo  - Frontend App:       http://localhost:5173
echo  - Backend API:        http://localhost:8000
echo  - API Docs:           http://localhost:8000/docs
echo  - API Logs:           %API_LOG%
echo  - Frontend Logs:      %WEB_LOG%
echo  - Main Setup Log:     %MAIN_LOG%
echo ======================================================
echo.
echo Both servers are running. Close this window or press Ctrl+C to terminate.
pause
