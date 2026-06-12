import { useCallback, useEffect, useState } from "react";

export type UpdaterState =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "downloaded"
  | "not-available"
  | "error"
  | "dev-disabled"
  | "unavailable";

export type UpdaterStatus = {
  state: UpdaterState;
  message: string;
  version?: string;
  percent?: number;
};

const IDLE: UpdaterStatus = { state: "idle", message: "" };

export function useUpdater() {
  const [status, setStatus] = useState<UpdaterStatus>({ state: "unavailable", message: "" });
  const supported = typeof window.electronAPI?.updater !== "undefined";

  useEffect(() => {
    const api = window.electronAPI?.updater;
    if (!api) return;

    setStatus(IDLE);
    return api.onStatus(setStatus);
  }, [supported]);

  const check = useCallback(() => {
    void window.electronAPI?.updater?.check();
  }, []);

  const install = useCallback(() => {
    void window.electronAPI?.updater?.install();
  }, []);

  const checking = status.state === "checking" || status.state === "downloading";
  const readyToInstall = status.state === "downloaded";

  return { supported, status, checking, readyToInstall, check, install };
}
