# Deploy CadForge landing page to cadforge.pro (Hostinger API)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Get-EnvValue([string]$Name) {
  if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name))) {
    $envFile = Join-Path (Get-Location) ".env"
    if (Test-Path $envFile) {
      Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*$Name\s*=\s*(.+)\s*$") {
          return $Matches[1].Trim()
        }
      }
    }
  }
  return [Environment]::GetEnvironmentVariable($Name)
}

$token = Get-EnvValue "HOSTINGER_API_TOKEN"
$domain = Get-EnvValue "HOSTINGER_DOMAIN"
if ([string]::IsNullOrWhiteSpace($domain)) { $domain = "cadforge.pro" }
if ([string]::IsNullOrWhiteSpace($token)) {
  Write-Error "Set HOSTINGER_API_TOKEN in .env or environment (see .env.example)."
}

$base = "https://developers.hostinger.com"
$headers = @{
  Authorization = "Bearer $token"
  Accept        = "application/json"
  "Content-Type" = "application/json"
}

Write-Host "Looking up website $domain..."
$sites = Invoke-RestMethod -Uri "$base/api/hosting/v1/websites?domain=$domain" -Headers $headers -Method Get
$site = $sites.data | Where-Object { $_.domain -eq $domain } | Select-Object -First 1
if (-not $site) {
  Write-Error "Website '$domain' not found on this Hostinger account."
}
$username = $site.username
Write-Host "Using hosting account: $username"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$zipName = "cadforge_$stamp.zip"
$zipPath = Join-Path $env:TEMP $zipName
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

$siteFiles = @("index.html", "styles.css", ".htaccess") | Where-Object { Test-Path $_ }
if ($siteFiles.Count -eq 0) {
  Write-Error "No site files found (index.html, styles.css, .htaccess)."
}

Compress-Archive -Path $siteFiles -DestinationPath $zipPath -Force
$archiveB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($zipPath))
Write-Host "Built archive $zipName ($('{0:N0}' -f ((Get-Item $zipPath).Length)) bytes)"

$paths = @(
  "/api/hosting/v1/accounts/$username/websites/$domain/static/builds/from-archive",
  "/api/hosting/v1/accounts/$username/websites/$domain/static-website/builds/from-archive",
  "/api/hosting/v1/accounts/$username/websites/$domain/html/builds/from-archive"
)

$body = @{ archive = $archiveB64; remove_archive = $true } | ConvertTo-Json
$deployed = $false
foreach ($path in $paths) {
  try {
    Write-Host "Trying $path ..."
    $result = Invoke-RestMethod -Uri "$base$path" -Headers $headers -Method Post -Body $body
    Write-Host "Deploy accepted."
    $result | ConvertTo-Json -Depth 6
    $deployed = $true
    break
  } catch {
    $status = $_.Exception.Response.StatusCode.value__
    Write-Host "  -> HTTP $status"
  }
}

Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

if (-not $deployed) {
  Write-Error @"
Hostinger API static deploy endpoint not reached.
Use hPanel Git instead: cadforge.pro -> Git -> barmau02/cadforge.pro -> public_html -> Deploy
"@
}

Write-Host "Done. Open https://$domain in a minute if extraction is still running."
