# Run once if Electron binary fails to download via npm
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dist = Join-Path $Root "node_modules\electron\dist"
$Zip = Join-Path $env:TEMP "electron-v34.zip"
$Url = "https://github.com/electron/electron/releases/download/v34.0.0/electron-v34.0.0-win32-x64.zip"

Write-Host "Downloading Electron..."
Invoke-WebRequest -Uri $Url -OutFile $Zip
Remove-Item -Recurse -Force $Dist -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Dist | Out-Null
Expand-Archive -Path $Zip -DestinationPath $Dist -Force
"v34.0.0" | Set-Content (Join-Path $Dist "version")
"electron.exe" | Set-Content (Join-Path $Root "node_modules\electron\path.txt")
Write-Host "Electron ready."