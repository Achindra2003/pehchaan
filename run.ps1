<#
.SYNOPSIS
    Pehchaan Unified Runner Script for Windows PowerShell & Cross-Platform PowerShell.
.DESCRIPTION
    Checks prerequisites, handles environment files, dependencies, ONNX models,
    logs output to logs/, and starts both backend (FastAPI) and frontend (Vite)
    with graceful shutdown on Ctrl+C.
#>

$ErrorActionPreference = "Stop"

$RootDir = $PSScriptRoot
$LogDir = Join-Path $RootDir "logs"
$ApiDir = Join-Path $RootDir "api"
$WebDir = Join-Path $RootDir "web"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$ApiLog = Join-Path $LogDir "api.log"
$WebLog = Join-Path $LogDir "web.log"
$MainLog = Join-Path $LogDir "run.log"

function Log-Message {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $logLine = "[$timestamp] [$Level] $Message"
    Add-Content -Path $MainLog -Value $logLine
    switch ($Level) {
        "SUCCESS" { Write-Host $logLine -ForegroundColor Green }
        "WARN"    { Write-Host $logLine -ForegroundColor Yellow }
        "ERROR"   { Write-Host $logLine -ForegroundColor Red }
        default   { Write-Host $logLine -ForegroundColor Cyan }
    }
}

Write-Host "========================================" -ForegroundColor Magenta
Write-Host "   Pehchaan - PowerShell Runner" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Log-Message "Log directory: $LogDir"

# 1. Check prerequisites
Log-Message "Checking system prerequisites..."
$missing = @()
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    $missing += "uv (Install via: winget install astral-sh.uv OR https://astral.sh/uv)"
}
if (-not (Get-Command "npm" -ErrorAction SilentlyContinue)) {
    $missing += "npm / Node.js (Install via: winget install OpenJS.NodeJS OR https://nodejs.org/)"
}

if ($missing.Count -gt 0) {
    Log-Message "Missing prerequisites:" "ERROR"
    foreach ($item in $missing) {
        Write-Host "  - $item" -ForegroundColor Red
    }
    exit 1
}
Log-Message "Prerequisites check passed (uv and npm found)." "SUCCESS"

# 2. Check .env
Log-Message "Checking environment configuration..."
$apiEnv = Join-Path $ApiDir ".env"
$rootEnvExample = Join-Path $RootDir ".env.example"
$apiEnvExample = Join-Path $ApiDir ".env.example"

if (-not (Test-Path $apiEnv)) {
    if (Test-Path $rootEnvExample) {
        Copy-Item -Path $rootEnvExample -Destination $apiEnv
        Log-Message "Created api/.env from root .env.example" "SUCCESS"
    } elseif (Test-Path $apiEnvExample) {
        Copy-Item -Path $apiEnvExample -Destination $apiEnv
        Log-Message "Created api/.env from api/.env.example" "SUCCESS"
    }
} else {
    Log-Message "api/.env already exists." "SUCCESS"
}

# 3. Python backend dependencies
Log-Message "Syncing backend Python environment (uv sync)..."
try {
    Push-Location $ApiDir
    & uv sync *>> $MainLog
    Pop-Location
    Log-Message "Backend environment synced." "SUCCESS"
} catch {
    Pop-Location
    Log-Message "uv sync failed. Check $MainLog for details." "ERROR"
    exit 1
}

# 4. Download models
Log-Message "Verifying ONNX models..."
try {
    Push-Location $ApiDir
    & uv run python scripts/download_models.py *>> $MainLog
    Pop-Location
    Log-Message "Models verified." "SUCCESS"
} catch {
    Pop-Location
    Log-Message "Model verification failed. Check $MainLog for details." "ERROR"
    exit 1
}

# 5. Frontend dependencies
$webNodeModules = Join-Path $WebDir "node_modules"
if (-not (Test-Path $webNodeModules)) {
    Log-Message "Installing frontend packages (npm install)..."
    try {
        Push-Location $WebDir
        & npm install *>> $MainLog
        Pop-Location
        Log-Message "Frontend packages installed." "SUCCESS"
    } catch {
        Pop-Location
        Log-Message "npm install failed. Check $MainLog for details." "ERROR"
        exit 1
    }
} else {
    Log-Message "web/node_modules found." "SUCCESS"
}

# 6. Start Backend & Frontend Processes
Log-Message "Starting backend API on port 8000..."
$apiProcess = Start-Process -FilePath "uv" `
    -ArgumentList "run uvicorn pehchaan.main:app_factory --factory --reload --port 8000" `
    -WorkingDirectory $ApiDir `
    -RedirectStandardOutput $ApiLog `
    -RedirectStandardError $ApiLog `
    -PassThru

Log-Message "Starting frontend dev server on port 5173..."
$webProcess = Start-Process -FilePath "npm" `
    -ArgumentList "run dev -- --host 0.0.0.0" `
    -WorkingDirectory $WebDir `
    -RedirectStandardOutput $WebLog `
    -RedirectStandardError $WebLog `
    -PassThru

# Register cleanup handler
$cleanup = {
    Log-Message "Stopping running services..." "WARN"
    if ($apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($webProcess -and -not $webProcess.HasExited) {
        Stop-Process -Id $webProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Log-Message "Services stopped." "SUCCESS"
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Green
Write-Host "   Pehchaan services are running successfully!        " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
Write-Host " • Frontend App:       http://localhost:5173"
Write-Host " • Backend API:        http://localhost:8000"
Write-Host " • API Documentation:  http://localhost:8000/docs"
Write-Host " • API Logs:           $ApiLog"
Write-Host " • Frontend Logs:      $WebLog"
Write-Host " • Runner Log:         $MainLog"
Write-Host ""
Write-Host "Press Ctrl+C to stop all services." -ForegroundColor Yellow
Write-Host ""

try {
    while (-not $apiProcess.HasExited -and -not $webProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    & $cleanup
}
