# Deploy PromptForge to Hostinger via GitHub

Hostinger shared hosting serves **static websites** (HTML/CSS). The PromptForge **desktop app** and **FreeCAD backend** run on your PC — the website is a landing page with download links.

## 1. Push code to GitHub

```powershell
cd c:\Users\mauri\forgeprompt
gh auth login
git remote add origin https://github.com/barmau02/promptforge.git
git push -u origin main
```

Create the repo on GitHub first if it does not exist (`gh repo create barmau02/promptforge --public --source=. --remote=origin`).

## 2. Option A — Hostinger Git (easiest)

1. Log in to **hPanel** → your domain → **Git**.
2. Connect **GitHub** and select `barmau02/promptforge`, branch `main`.
3. Set **Deploy path** to `website/` (or copy `website/*` into `public_html` after clone).
4. Enable **Auto deployment** on push.

## 3. Option B — GitHub Actions (FTP)

In GitHub → **Settings → Secrets and variables → Actions**, add:

| Secret | Example |
|--------|---------|
| `HOSTINGER_FTP_HOST` | `ftp.yourdomain.com` |
| `HOSTINGER_FTP_USERNAME` | from hPanel → FTP Accounts |
| `HOSTINGER_FTP_PASSWORD` | FTP password |
| `HOSTINGER_FTP_PATH` | `./public_html/` (optional) |

Find FTP details in hPanel → **Files → FTP Accounts**.

Every push to `main` that changes `website/` runs `.github/workflows/deploy-hostinger.yml` and uploads the site.

## 4. Desktop app releases

Build and publish the Windows installer separately:

```powershell
cd freecad-studio-desktop
npm run electron:publish
```

GitHub Releases hosts the `.exe` installer; the website links to `releases/latest`.

## What does not run on Hostinger

- FastAPI backend (needs Python + FreeCAD on a VPS, not basic shared hosting)
- Electron desktop app (download from GitHub Releases)
