import { app, BrowserWindow, shell, session } from "electron";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import { fileURLToPath } from "url";
import http from "http";
import { initUpdater } from "./updater.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isDev = !app.isPackaged;
const API_PORT = 8787;
const API_URL = `http://127.0.0.1:${API_PORT}`;

// LAN WebRTC to Creality printer: avoid mDNS-only candidates on Windows/Electron.
app.commandLine.appendSwitch("disable-features", "WebRtcHideLocalIpsWithMdns");

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

const FREECAD_PYTHON = "C:\\Program Files\\FreeCAD 1.1\\bin\\python.exe";
const BACKEND_DIR = isDev
  ? path.join(__dirname, "..", "..", "freecad-studio", "backend")
  : path.join(process.resourcesPath, "backend");

function waitForServer(timeoutMs = 30000): Promise<void> {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get(`${API_URL}/api/status`, (res) => {
        res.resume();
        if (res.statusCode === 200) resolve();
        else retry();
      });
      req.on("error", retry);
      function retry() {
        if (Date.now() - start > timeoutMs) reject(new Error("Backend timeout"));
        else setTimeout(check, 500);
      }
    };
    check();
  });
}

function startBackend() {
  backendProcess = spawn(FREECAD_PYTHON, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", `--port=${API_PORT}`], {
    cwd: BACKEND_DIR,
    windowsHide: true,
    stdio: "ignore",
  });
  backendProcess.on("error", (err) => console.error("Backend error:", err));
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    title: "CadForge",
    backgroundColor: "#000000",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL("http://127.0.0.1:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

async function ensureFreeCADConnected() {
  let started = false;
  for (let i = 0; i < 30; i++) {
    try {
      const res = await fetch(`${API_URL}/api/status`);
      if (!res.ok) {
        await new Promise((r) => setTimeout(r, 1000));
        continue;
      }
      const status = (await res.json()) as { rpc_connected?: boolean };
      if (status.rpc_connected) return;
      if (!started) {
        started = true;
        await fetch(`${API_URL}/api/start-all`, { method: "POST" });
      }
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
}

app.whenReady().then(async () => {
  initUpdater(() => mainWindow);

  const allowMediaCapture = (permission: string) =>
    permission === "media" || permission === "display-capture";

  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(allowMediaCapture(String(permission)));
  });
  session.defaultSession.setPermissionCheckHandler((_wc, permission) => {
    return allowMediaCapture(String(permission));
  });

  startBackend();
  try {
    await waitForServer();
    await ensureFreeCADConnected();
  } catch {
    console.warn("Backend slow to start — UI will retry");
  }
  createWindow();
});

app.on("window-all-closed", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});