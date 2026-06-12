# PromptForge

AI concept → 3D model → slice → print on Creality K2.

## Structure

| Path | Purpose |
|------|---------|
| `index.html`, `styles.css` | Public landing page (Hostinger Git → `public_html`) |
| `freecad-studio/backend/` | FastAPI API, FreeCAD headless, slicing |
| `freecad-studio-desktop/` | Vite + React + Electron desktop app |
| `cli-anything-freecad/` | Batch FreeCAD CLI sidecar |

## Quick start (local)

```powershell
# Backend
cd freecad-studio\backend
copy ..\config.example.toml ..\config.toml
& "C:\Program Files\FreeCAD 1.1\bin\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8787

# Desktop
cd freecad-studio-desktop
npm install
npm run electron:dev
```

## Deploy website

See [DEPLOY.md](DEPLOY.md) — connect this repo to Hostinger Git with directory `public_html`.

## License

See individual components. API keys belong in `jobs/secrets.db`, never in git.
