import type { UpdaterStatus } from "./hooks/useUpdater";

declare global {
  interface Window {
    electronAPI?: {
      updater: {
        check: () => Promise<void>;
        install: () => Promise<void>;
        onStatus: (callback: (status: UpdaterStatus) => void) => () => void;
      };
    };
  }
}

export {};
