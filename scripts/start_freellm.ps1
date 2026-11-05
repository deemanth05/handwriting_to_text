<#
.SYNOPSIS
    Starts the local FreeLLMAPI router on http://127.0.0.1:3001
#>
$ErrorActionPreference = "Stop"

$freellmPath = "C:\Users\deema\Desktop\projects\Exam_Revision_Planner\.cache\freellmapi"

if (-not (Test-Path $freellmPath)) {
    Write-Error "FreeLLMAPI directory not found at $freellmPath"
    exit 1
}

Push-Location $freellmPath
try {
    Write-Host "[+] Starting FreeLLMAPI router on http://127.0.0.1:3001..." -ForegroundColor Green
    Write-Host "[*] Keep this window open. Press Ctrl+C to terminate." -ForegroundColor Yellow
    node server/dist/index.js
} finally {
    Pop-Location
}
