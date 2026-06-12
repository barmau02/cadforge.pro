import { Services, Status } from "../api";
import { UpdaterStatus } from "../hooks/useUpdater";
import { IconPower, IconRefresh } from "./icons";

export function TopBar({
  status,
  services,
  busy,
  buildPhase,
  buildProgress,
  onStartAll,
  updaterSupported,
  updaterStatus,
  updaterChecking,
  updaterReady,
  onCheckUpdates,
  onInstallUpdate,
}: {
  status: Status | null;
  services: Services | null;
  busy: boolean;
  buildPhase: string | null;
  buildProgress: number;
  onStartAll: () => void;
  updaterSupported: boolean;
  updaterStatus: UpdaterStatus;
  updaterChecking: boolean;
  updaterReady: boolean;
  onCheckUpdates: () => void;
  onInstallUpdate: () => void;
}) {
  const items = services?.items ?? [];
  const cadLive = status?.cad_ready ?? status?.rpc_connected === true;
  const headless = status?.freecad_mode === "headless";

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-services">
          {items.map((item) => (
            <div
              key={item.id}
              className={`service-badge ${item.ok ? "online" : "offline"}`}
              title={item.detail}
            >
              <span className="service-led" />
              <span className="service-label">{item.name}</span>
            </div>
          ))}
        </div>
        {busy && buildPhase && (
          <div className="topbar-activity" role="status" aria-live="polite">
            <span className="topbar-activity-dot" />
            <span className="topbar-activity-text">{buildPhase}</span>
            {buildProgress > 0 && (
              <span className="topbar-activity-pct">{buildProgress}%</span>
            )}
          </div>
        )}
      </div>

      <div className="topbar-actions">
        {updaterSupported && (
          <div className="update-controls">
            {updaterStatus.message && (
              <div
                className={`update-status update-status--${updaterStatus.state}`}
                role="status"
                aria-live="polite"
                title={updaterStatus.message}
              >
                {updaterStatus.message}
              </div>
            )}
            {updaterReady ? (
              <button
                type="button"
                className="btn btn-compact btn-primary"
                onClick={onInstallUpdate}
              >
                Restart to update
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-compact btn-ghost"
                disabled={updaterChecking}
                onClick={onCheckUpdates}
                title="Check for PromptForge updates"
              >
                <IconRefresh size={15} />
                {updaterChecking ? "Checking…" : "Check for updates"}
              </button>
            )}
          </div>
        )}
        <button
          type="button"
          className={`btn btn-compact ${cadLive ? "btn-primary" : "btn-ghost"}`}
          disabled={busy || services?.all_ready}
          onClick={onStartAll}
        >
          <IconPower size={15} />
          {services?.all_ready ? "Running" : "Start All"}
        </button>
        {status?.active_job_title && (
          <div className="job-badge" title={status.active_job_doc ?? undefined}>
            {status.active_job_title}
          </div>
        )}
        <div className={`conn-badge ${cadLive ? "online" : "offline"}`}>
          <span className="conn-led" />
          {status === null
            ? "Connecting…"
            : cadLive
              ? headless
                ? "CAD ready"
                : "FreeCAD live"
              : headless
                ? "CAD offline"
                : "FreeCAD offline"}
        </div>
      </div>
    </header>
  );
}
