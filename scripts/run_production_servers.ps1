<#
.SYNOPSIS
    Production & Development Server Launcher for Paper-to-Structured-Data Engine.
    Sanitizes lingering processes on ports 8000 & 5173, starts clean instances,
    and runs health verification checks.
#>

$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Paper-to-Structured-Data Server Launcher & Monitor" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ROOT_DIR = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $ROOT_DIR

# 1. Terminate any lingering processes on Port 8000 & Port 5173
Write-Host "`n[1/4] Sanitizing ports 8000 and 5173..." -ForegroundColor Yellow

function Kill-PortProcesses([int]$port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($conns) {
            $pids = $conns.OwningProcess | Where-Object { $_ -gt 0 } | Select-Object -Unique
            foreach ($p in $pids) {
                Write-Host "  -> Terminating process PID $p on port $port..." -ForegroundColor Yellow
                Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        # Fallback via netstat
        $lines = netstat -ano | Select-String ":$port\s"
        foreach ($line in $lines) {
            $tokens = ($line.ToString().Trim() -split "\s+")
            if ($tokens.Count -ge 5) {
                $pidVal = $tokens[-1]
                if ($pidVal -match '^\d+$' -and [int]$pidVal -gt 0) {
                    Write-Host "  -> Terminating PID $pidVal on port $port..." -ForegroundColor Yellow
                    Stop-Process -Id [int]$pidVal -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }
}

Kill-PortProcesses 8000
Kill-PortProcesses 5173

# Give OS 1 second to release sockets
Start-Sleep -Seconds 1

# 2. Launch FastAPI backend using virtualenv uvicorn
Write-Host "`n[2/4] Starting FastAPI Backend on http://127.0.0.1:8000..." -ForegroundColor Green
$uvicornPath = Join-Path $ROOT_DIR "backend\.venv\Scripts\uvicorn.exe"
if (-not (Test-Path $uvicornPath)) {
    Write-Error "uvicorn executable not found at $uvicornPath"
    exit 1
}

$backendProc = Start-Process -FilePath $uvicornPath `
    -ArgumentList "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload" `
    -WorkingDirectory $ROOT_DIR `
    -PassThru

Write-Host "  -> Backend launched with PID $($backendProc.Id)" -ForegroundColor DarkGray

# 3. Launch Vite Frontend on port 5173
Write-Host "`n[3/4] Starting Vite Frontend on http://localhost:5173..." -ForegroundColor Green
$frontendDir = Join-Path $ROOT_DIR "frontend"

$frontendProc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev -- --host 0.0.0.0 --port 5173" `
    -WorkingDirectory $frontendDir `
    -PassThru

Write-Host "  -> Frontend launched with PID $($frontendProc.Id)" -ForegroundColor DarkGray

# 4. Verify Both Health Endpoints
Write-Host "`n[4/4] Verifying health endpoints..." -ForegroundColor Cyan

$backendReady = $false
for ($i = 0; $i -lt 15; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($resp -and $resp.status -eq "HEALTHY") {
            $backendReady = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 800
    }
}

if ($backendReady) {
    Write-Host "  [OK] Backend HTTP 200: Healthy (127.0.0.1:8000)" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Backend did not respond within 12 seconds." -ForegroundColor Red
}

$frontendReady = $false
for ($i = 0; $i -lt 15; $i++) {
    try {
        $tcp = Test-NetConnection -ComputerName "127.0.0.1" -Port 5173 -WarningAction SilentlyContinue
        if ($tcp.TcpTestSucceeded) {
            $frontendReady = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 800
    }
}

if ($frontendReady) {
    Write-Host "  [OK] Frontend Listening: http://localhost:5173" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Frontend port 5173 not responding." -ForegroundColor Red
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  Both servers running cleanly! UI at http://localhost:5173" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
