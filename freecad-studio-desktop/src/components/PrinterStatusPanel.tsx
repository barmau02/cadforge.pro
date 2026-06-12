import { useEffect, useState } from "react";
import { api, type PrinterStatusResponse } from "../api";

export function PrinterStatusPanel() {
  const [data, setData] = useState<PrinterStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const next = await api.printerStatus();
      setData(next);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const ready = data?.ready_to_print ?? false;
  const printer = data?.printer;
  const local = data?.local;

  return (
    <section className="printer-status-panel">
      <div className="printer-status-head">
        <h3 className="printer-status-title">Printer status</h3>
        <span className={`printer-ready-badge ${ready ? "ready" : "blocked"}`}>
          {ready ? "Ready to print" : "Not ready"}
        </span>
      </div>

      {error && <p className="printer-status-error">{error}</p>}

      {data?.blockers?.length ? (
        <ul className="printer-blockers">
          {data.blockers.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}

      {data?.warnings?.length ? (
        <ul className="printer-warnings">
          {data.warnings.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}

      <div className="printer-status-grid">
        <StatusRow
          label="Filament"
          value={printer?.filament_label ?? (data?.online ? "Unknown" : "Printer offline")}
          ok={printer?.filament_loaded ? true : null}
        />
        <StatusRow
          label="CFS"
          value={printer?.cfs_connected ? "Connected" : "Not connected"}
          ok={printer?.cfs_connected ? true : null}
        />
        <StatusRow
          label="Printer"
          value={printer?.print_state_label ?? "—"}
          ok={printer?.print_state === 0}
        />
        <StatusRow
          label="Nozzle"
          value={fmtTemp(printer?.nozzle_temp)}
          ok={null}
        />
        <StatusRow
          label="Bed"
          value={fmtTemp(printer?.bed_temp)}
          ok={null}
        />
        <StatusRow
          label="Slice file"
          value={
            local?.gcode_file
              ? `${local.gcode_file}${local.gcode_print_time ? ` · ${local.gcode_print_time}` : ""}`
              : "None — slice first"
          }
          ok={Boolean(local?.gcode_ready && !local?.gcode_stale && !local?.cad_stale)}
        />
        <StatusRow
          label="CAD export"
          value={local?.cad_stale ? "Out of date — Re-slice" : "Up to date"}
          ok={!local?.cad_stale}
        />
      </div>
    </section>
  );
}

function fmtTemp(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(n)}°C` : String(value);
}

function StatusRow({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok: boolean | null | undefined;
}) {
  const cls = ok === true ? "ok" : ok === false ? "bad" : "";
  return (
    <div className={`printer-status-row ${cls}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
