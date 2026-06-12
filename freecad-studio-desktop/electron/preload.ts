import { contextBridge, ipcRenderer, type IpcRendererEvent } from "electron";
import type { UpdaterPayload } from "./updater.js";

contextBridge.exposeInMainWorld("electronAPI", {
  updater: {
    check: () => ipcRenderer.invoke("updater:check"),
    install: () => ipcRenderer.invoke("updater:install"),
    onStatus: (callback: (status: UpdaterPayload) => void) => {
      const listener = (_event: IpcRendererEvent, status: UpdaterPayload) => {
        callback(status);
      };
      ipcRenderer.on("updater:status", listener);
      return () => ipcRenderer.removeListener("updater:status", listener);
    },
  },
});
