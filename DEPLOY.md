# Deploy PromptForge website via Hostinger Git

Hostinger **Git** clones your GitHub repo into `public_html`. The landing page lives at the **repo root** (`index.html`, `styles.css`) so it becomes your domain homepage.

The desktop app and FreeCAD backend stay on your PC — the website is a download/info page only.

## 1. Push to GitHub

```powershell
cd c:\Users\mauri\forgeprompt
gh auth login
git remote add origin https://github.com/barmau02/promptforge.git
git push -u origin main
```

If the repo does not exist yet:

```powershell
gh repo create barmau02/promptforge --public --source=. --remote=origin --push
```

## 2. Map Git to your webpage (Hostinger hPanel)

1. Open **hPanel** → **Websites** → your domain → **Git** (under Advanced).
2. Click **Create repository** (or **Connect GitHub**).
3. Authorize GitHub and choose **`barmau02/promptforge`**.
4. Set:
   - **Branch:** `main`
   - **Directory / install path:** `public_html` (default — your main website root)
5. Click **Deploy**.
6. Turn on **Auto-deployment** so each `git push` updates the live site.

After deploy, open your domain — you should see the PromptForge landing page.

## 3. How it works

| Repo path | On Hostinger | Served? |
|-----------|--------------|---------|
| `index.html` | `public_html/index.html` | Yes — homepage |
| `styles.css` | `public_html/styles.css` | Yes |
| `.htaccess` | `public_html/.htaccess` | Blocks web access to source folders |
| `freecad-studio/` | `public_html/freecad-studio/` | Blocked by `.htaccess` |
| `freecad-studio-desktop/` | `public_html/freecad-studio-desktop/` | Blocked by `.htaccess` |

## 4. Desktop app releases

Publish the Windows installer to GitHub Releases (not Hostinger):

```powershell
cd freecad-studio-desktop
npm run electron:publish
```

The website links to `https://github.com/barmau02/promptforge/releases/latest`.

## Troubleshooting

- **404 or wrong page:** Confirm Git directory is `public_html`, branch is `main`, and `index.html` is at the repo root.
- **Old content after push:** In hPanel Git, click **Deploy** again or check auto-deploy is enabled.
- **Source folders visible:** Ensure `.htaccess` was deployed; Hostinger Apache must allow `mod_rewrite`.
