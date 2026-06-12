$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Url = "http://127.0.0.1:8787"

Set-Location $Backend

$python = "C:\Program Files\FreeCAD 1.1\bin\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python -m pip install -q -r (Join-Path $Root "requirements.txt")
Start-Process $Url
& $python -m uvicorn main:app --host 127.0.0.1 --port 8787 --reload