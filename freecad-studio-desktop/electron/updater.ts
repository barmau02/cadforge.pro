import { app, BrowserWindow, ipcMain } from "electron";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { autoUpdater } = require("electron-updater") as typeof import("electron-updater");

export type UpdaterState =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "downloaded"
  | "not-available"
  | "error"
  | "dev-disabled";

export type UpdaterPayload = {
  state: UpdaterState;
  message: string;
  version?: string;
  percent?: number;
};

type WindowGetter = () => BrowserWindow | null;

function send(getWindow: WindowGetter, payload: UpdaterPayload) {
  getWindow()?.webContents.send("updater:status", payload);
}

export function initUpdater(getWindow: WindowGetter) {
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("checking-for-update", () => {
    send(getWindow, { state: "checking", message: "Checking for updates…" });
  });

  autoUpdater.on("update-available", (info) => {
    send(getWindow, {
      state: "available",
      message: `Update v${info.version} available`,
      version: info.version,
    });
  });

  autoUpdater.on("update-not-available", (info) => {
    send(getWindow, {
      state: "not-available",
      message: `You're on the latest version (v${info.version})`,
      version: info.version,
    });
  });

  autoUpdater.on("download-progress", (progress) => {
    send(getWindow, {
      state: "downloading",
      message: `Downloading update… ${Math.round(progress.percent)}%`,
      percent: progress.percent,
    });
  });

  autoUpdater.on("update-downloaded", (info) => {
    send(getWindow, {
      state: "downloaded",
      message: `Update v${info.version} ready — restart to install`,
      version: info.version,
    });
  });

  autoUpdater.on("error", (err) => {
    send(getWindow, {
      state: "error",
      message: err.message || "Update check failed",
    });
  });

  ipcMain.handle("updater:check", async () => {
    if (!app.isPackaged) {
      send(getWindow, {
        state: "dev-disabled",
        message: "Updates are disabled in development",
      });
      return;
    }
    await autoUpdater.checkForUpdates();
  });

  ipcMain.handle("updater:install", () => {
    if (!app.isPackaged) return;
    autoUpdater.quitAndInstall();
  });

  if (app.isPackaged) {
    setTimeout(() => {
      autoUpdater.checkForUpdates().catch(() => {
        /* silent on startup */
      });
    }, 5000);
  }
}
