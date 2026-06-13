# Publish CadForge to GitHub (cadforge.pro)
# Run once after: gh auth login

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Error "Install GitHub CLI: https://cli.github.com/"
}

gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Log in to GitHub first..."
  gh auth login --hostname github.com --git-protocol https --web
}

$repo = "barmau02/cadforge.pro"
$exists = gh repo view $repo 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Creating $repo..."
  gh repo create $repo --public --source=. --remote=origin --description "CadForge — AI concept to printable 3D (cadforge.pro)"
} else {
  git remote remove origin 2>$null
  git remote add origin "https://github.com/$repo.git"
}

Write-Host "Pushing main..."
git push -u origin main

Write-Host ""
Write-Host "Done. Next: Hostinger hPanel -> cadforge.pro -> Git -> connect $repo -> public_html -> Deploy"
