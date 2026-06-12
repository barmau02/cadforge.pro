# CadForge backend — reliable PowerShell launcher
$ErrorActionPreference = "Stop"
$BackendDir = $PSScriptRoot
$Python = "C:\Program Files\FreeCAD 1.1\bin\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "FreeCAD Python not found: $Python"
    exit 1
}

Set-Location $BackendDir
Write-Host "Starting CadForge API on http://127.0.0.1:8787"
& $Python -m uvicorn main:app --host 127.0.0.1 --port 8787