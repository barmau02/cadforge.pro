import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Status } from "../api";
import { buildPrintPipelineGuide } from "../lib/printPipeline";
import { GcodeViewer } from "./GcodeViewer";
import { ModelViewer } from "./ModelViewer";
import { PrintPipelineGuide } from "./PrintPipelineGuide";
import { PrinterCamera } from "./PrinterCamera";
import { PrinterStatusPanel } from "./PrinterStatusPanel";
import { SliceTopBarControl } from "./SliceTopBarControl";
import { IconPrint3d, IconWifi } from "./icons";
import { gcodePreviewUrl, gcodeThumbnailUrl } from "../api";

type PreviewMode = "solid" | "sliced";

export function PrintPanel({
  status,
  busy,
  stlUrl,
  activeJobId,
  onExport,
  onSlicer,
  onSlice,
  onReslice,
  onSend,
  onDiscover,
  onStartAll,
  onGoDesign,
  onGoSettings,
}: {
  status: Status | null;
  busy: boolean;
  stlUrl: string | null;
  activeJobId: string | null;
  onExport: () => void;
  onSlicer: () => void;
  onSlice: () => void;
  onReslice: () => void;
  onSend: () => void;
  onDiscover: () => void;
  onStartAll: () => void;
  onGoDesign: () => void;
  onGoSettings: () => void;
}) {
  const [previewMode, setPreviewMode] = useState<PreviewMode>("solid");

  const guide = useMemo(() => buildPrintPipelineGuide(status, busy), [status, busy]);

  // Keep solid/isometric STL as default; user switches to sliced toolpaths manually.

  const gcodeUrl = useMemo(() => {
    if (!status?.gcode_ready || status?.gcode_stale || status?.cad_stale) return null;
    return gcodePreviewUrl(activeJobId ?? undefined, status.gcode_file ?? undefined);
  }, [status?.gcode_ready, status?.gcode_stale, status?.cad_stale, status?.gcode_file, activeJobId]);

  const thumbnailUrl = useMemo(() => {
    if (!status?.gcode_has_thumbnail) return null;
    return gcodeThumbnailUrl(activeJobId ?? undefined, status.gcode_file ?? undefined);
  }, [status?.gcode_has_thumbnail, status?.gcode_file, activeJobId]);

  const effectiveMode =
    previewMode === "sliced" && gcodeUrl ? "sliced" : "solid";

  // Always use full re-slice (export STL → wipe old files → slice for K2).
  const onPrimarySlice = onReslice;

  return (
    <section className="panel print-panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Print Pipeline</h2>
          <p className="panel-subtitle">
            {status?.active_job_title
              ? `Job: ${status.active_job_title}`
              : "Export, slice, and send to your Creality printer"}
          </p>
        </div>
      </div>

      <div className="print-layout">
        <div className="print-preview-panel">
          <div className="print-preview-header">
            <div className="preview-mode-tabs">
              <button
                type="button"
                className={`preview-mode-tab ${effectiveMode === "solid" ? "active" : ""}`}
                onClick={() => setPreviewMode("solid")}
              >
                Solid (STL)
              </button>
              <button
                type="button"
                className={`preview-mode-tab ${effectiveMode === "sliced" ? "active" : ""}`}
                disabled={!gcodeUrl}
                onClick={() => setPreviewMode("sliced")}
              >
                Sliced (toolpaths)
              </button>
            </div>
            <div className="print-preview-header-meta">
              {gcodeUrl && (
                <div className="slice-stats">
                  {status?.gcode_print_time && <span>{status.gcode_print_time}</span>}
                  {status?.gcode_filament_g != null && <span>{status.gcode_filament_g.toFixed(1)} g</span>}
                  {status?.gcode_layer_count != null && <span>{status.gcode_layer_count} layers</span>}
                </div>
              )}
              {gcodeUrl && (
                <SliceTopBarControl
                  status={status}
                  busy={busy}
                  onSlice={onReslice}
                  onStartAll={onStartAll}
                  onGoDesign={onGoDesign}
                  onGoSettings={onGoSettings}
                />
              )}
            </div>
          </div>

          <div className="preview-viewport print-preview-viewport">
            {effectiveMode === "sliced" ? (
              <div className="print-preview-stack">
                {thumbnailUrl && (
                  <img className="gcode-thumbnail" src={thumbnailUrl} alt="Slicer preview thumbnail" />
                )}
                <GcodeViewer gcodeUrl={gcodeUrl} />
              </div>
            ) : (
              <ModelViewer
                stlUrl={stlUrl}
                fallbackImage={null}
                printBed={
                  status?.bed_width_mm && status?.bed_depth_mm && status?.bed_height_mm
                    ? {
                        widthMm: status.bed_width_mm,
                        depthMm: status.bed_depth_mm,
                        heightMm: status.bed_height_mm,
                        label: status.printer_label,
                      }
                    : null
                }
              />
            )}
          </div>

          <p className="print-preview-note">
            {gcodeUrl
              ? "Toolpath preview from your slice file."
              : "After slicing, switch to Sliced to preview toolpaths."}
          </p>

          <section className="printer-camera-panel printer-camera-panel--below-preview">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">Live camera</h3>
                <p className="panel-subtitle">WebRTC feed from your K2</p>
              </div>
            </div>
            <PrinterCamera printerIp={status?.printer_ip} online={status?.printer_online} />
          </section>
        </div>

        <div className="print-steps-panel">
          <PrintPipelineGuide status={status} busy={busy} />

          <div className="print-grid">
            <PrintCard
              step="1"
              title="Export STL (optional)"
              detail={
                status?.stl_ready
                  ? `${status.stl_count} file(s) already exported`
                  : "Skip this if you use Slice for printer — it exports automatically"
              }
              status={status?.stl_ready ? "ready" : "pending"}
              actionLabel="Export STL only"
              onAction={onExport}
              disabled={!guide.canExport}
              disabledReason={guide.exportDisabledReason}
            />

            <PrintCard
              step="2"
              title="Slice for printer"
              detail={
                status?.gcode_ready && !status?.gcode_stale && !status?.cad_stale
                  ? `Ready: ${status.gcode_file}`
                    : status?.cad_stale_reason ||
                    status?.gcode_stale_reason ||
                    "Auto-orients and centers on the K2 bed (like Creality Print), then slices"
              }
              status={
                status?.gcode_ready && !status?.gcode_stale && !status?.cad_stale
                  ? "ready"
                  : guide.canSlice
                    ? "active"
                    : "pending"
              }
              actionLabel="Slice for printer"
              onAction={onPrimarySlice}
              disabled={!guide.canSlice}
              disabledReason={guide.sliceDisabledReason}
              secondaryLabel="Open Orca manually"
              onSecondary={onSlicer}
              secondaryDisabled={!guide.canExport}
              secondaryDisabledReason={guide.exportDisabledReason}
            />

            <PrintCard
              step="3"
              title="Send over WiFi"
              detail={
                status?.printer_online
                  ? `${status.printer_label} @ ${status.printer_ip}`
                  : "Printer not found on network"
              }
              status={guide.canSend ? "ready" : status?.printer_online ? "active" : "pending"}
              actionLabel="Send to Printer"
              onAction={onSend}
              disabled={!guide.canSend}
              disabledReason={guide.sendDisabledReason}
              icon={<IconPrint3d size={16} />}
            />
          </div>

          <div className="print-status-row">
            <div className={`status-card ${status?.printer_online ? "ok" : "dim"}`}>
              <IconWifi size={18} />
              <div>
                <div className="status-card-title">Printer WiFi</div>
                <div className="status-card-detail">{status?.printer_detail ?? "Scanning…"}</div>
              </div>
            </div>
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={onDiscover}>
              Find Printer
            </button>
          </div>

          {!status?.orca_installed && (
            <div className="notice">
              Install OrcaSlicer for one-click <strong>Slice for printer</strong>, or use{" "}
              <a href={status?.slicer_download} target="_blank" rel="noreferrer">
                Creality Print
              </a>{" "}
              manually.
            </div>
          )}

          <PrinterStatusPanel />
        </div>
      </div>
    </section>
  );
}

function PrintCard({
  step,
  title,
  detail,
  status,
  actionLabel,
  onAction,
  disabled,
  disabledReason,
  icon,
  secondaryLabel,
  onSecondary,
  secondaryDisabled,
  secondaryDisabledReason,
}: {
  step: string;
  title: string;
  detail: string;
  status: "ready" | "active" | "pending";
  actionLabel: string;
  onAction: () => void;
  disabled: boolean;
  disabledReason?: string | null;
  icon?: ReactNode;
  secondaryLabel?: string;
  onSecondary?: () => void;
  secondaryDisabled?: boolean;
  secondaryDisabledReason?: string | null;
}) {
  return (
    <article className={`print-card ${status}`}>
      <div className="print-card-step">{step}</div>
      <h3 className="print-card-title">{title}</h3>
      <p className="print-card-detail">{detail}</p>
      {disabled && disabledReason && (
        <p className="print-card-lock-reason">{disabledReason}</p>
      )}
      <div className="print-card-actions">
        <button
          type="button"
          className="btn btn-primary btn-compact"
          disabled={disabled}
          title={disabled ? disabledReason ?? undefined : undefined}
          onClick={onAction}
        >
          {icon}
          {actionLabel}
        </button>
        {secondaryLabel && onSecondary && (
          <>
            {secondaryDisabled && secondaryDisabledReason && (
              <p className="print-card-lock-reason secondary">{secondaryDisabledReason}</p>
            )}
            <button
              type="button"
              className="btn btn-ghost btn-compact"
              disabled={secondaryDisabled}
              title={secondaryDisabled ? secondaryDisabledReason ?? undefined : undefined}
              onClick={onSecondary}
            >
              {secondaryLabel}
            </button>
          </>
        )}
      </div>
    </article>
  );
}
