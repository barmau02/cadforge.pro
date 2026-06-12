import { useEffect, useRef, useState } from "react";
import type { Status } from "../api";
import { buildSliceReadiness } from "../lib/sliceReadiness";
import { IconPrint3d } from "./icons";

export function SliceTopBarControl({
  status,
  busy,
  onSlice,
  onStartAll,
  onGoDesign,
  onGoSettings,
}: {
  status: Status | null;
  busy: boolean;
  onSlice: () => void;
  onStartAll: () => void;
  onGoDesign: () => void;
  onGoSettings: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const readiness = buildSliceReadiness(status, busy);

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const runFix = (action?: string) => {
    setOpen(false);
    if (action === "start-all") onStartAll();
    else if (action === "slice") onSlice();
    else if (action === "design") onGoDesign();
    else if (action === "settings") onGoSettings();
  };

  const missing = readiness.requirements.filter((r) => !r.ok);

  return (
    <div className="slice-topbar" ref={rootRef}>
      <button
        type="button"
        className={`btn btn-compact slice-topbar-btn ${
          readiness.highlight ? "btn-primary" : readiness.canSlice ? "btn-ghost" : ""
        }`}
        disabled={busy || !readiness.canSlice}
        title={readiness.buttonHint}
        onClick={() => {
          if (readiness.canSlice && !busy) onSlice();
          else setOpen((v) => !v);
        }}
      >
        <IconPrint3d size={15} />
        {readiness.buttonLabel}
      </button>
      <button
        type="button"
        className="slice-topbar-toggle"
        aria-expanded={open}
        aria-label="Show slice requirements"
        onClick={() => setOpen((v) => !v)}
      >
        {readiness.readyCount}/{readiness.totalCount}
      </button>

      {open && (
        <div className="slice-topbar-popover" role="dialog" aria-label="Slice requirements">
          <div className="slice-topbar-popover-head">
            <strong>Slice checklist</strong>
            <span className="slice-topbar-popover-meta">
              {readiness.readyCount} of {readiness.totalCount} ready
            </span>
          </div>
          <p className="slice-topbar-popover-detail">
            Like Creality Print: export → auto-orient → center on bed → K2 .gcode.3mf
          </p>
          <ul className="slice-topbar-checklist">
            {readiness.requirements.map((item) => (
              <li key={item.id} className={item.ok ? "ok" : "todo"}>
                <span className="slice-topbar-check">{item.ok ? "✓" : "○"}</span>
                <div className="slice-topbar-check-body">
                  <strong>{item.label}</strong>
                  {!item.ok && <span>{item.fix}</span>}
                  {!item.ok && item.action && (
                    <button
                      type="button"
                      className="slice-topbar-fix-btn"
                      onClick={() => runFix(item.action)}
                    >
                      {item.action === "start-all"
                        ? "Start All"
                        : item.action === "design"
                          ? "Open Design"
                          : item.action === "settings"
                            ? "Settings"
                            : "Slice now"}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {missing.length > 0 ? (
            <p className="slice-topbar-popover-foot">
              Fix {missing.length} item{missing.length === 1 ? "" : "s"} above, then slice.
            </p>
          ) : (
            <div className="slice-topbar-popover-actions">
              <button
                type="button"
                className="btn btn-primary btn-compact"
                disabled={busy}
                onClick={() => runFix("slice")}
              >
                {readiness.highlight ? "Slice for printer" : "Re-slice"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
