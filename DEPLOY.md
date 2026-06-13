# Deploy cadforge.pro with GitHub Pages

**Code** lives on GitHub. **Hosting** is free via GitHub Pages. **Domain** DNS stays at Hostinger.

## 1. GitHub Pages (automatic)

Pushes to `main` that change `index.html` or `styles.css` run `.github/workflows/github-pages.yml`.

Live URLs after DNS is configured:

- https://cadforge.pro
- https://barmau02.github.io/cadforge.pro/

## 2. Point Hostinger DNS to GitHub

hPanel → **Domains** → **cadforge.pro** → **DNS / DNS Zone**

Remove **parking** records. Add:

### A records (apex `@` → GitHub Pages)

| Type | Name | Points to |
|------|------|-----------|
| A | @ | 185.199.108.153 |
| A | @ | 185.199.109.153 |
| A | @ | 185.199.110.153 |
| A | @ | 185.199.111.153 |

### CNAME (optional, for www)

| Type | Name | Points to |
|------|------|-----------|
| CNAME | www | barmau02.github.io |

DNS can take up to 24 hours (often minutes).

In GitHub → repo **Settings → Pages → Custom domain**, enter `cadforge.pro` and enable **Enforce HTTPS** when available.

## 3. Verify

Open https://cadforge.pro — title should be **CadForge — Concept to Print**, not Hostinger parked domain.

## Desktop app

Publish the Windows installer to GitHub Releases (not Pages):

```powershell
cd freecad-studio-desktop
npm run electron:publish
```

## What does not run on GitHub Pages

- FastAPI backend / FreeCAD (local desktop app only)
- Electron app (download from Releases)
