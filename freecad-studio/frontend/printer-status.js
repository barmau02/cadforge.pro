(() => {
  const panel = document.getElementById("printerStatusPanel");
  const readyEl = document.getElementById("printerReadyBadge");
  const blockersEl = document.getElementById("printerBlockers");
  const gridEl = document.getElementById("printerStatusGrid");
  if (!panel || !readyEl || !gridEl) return;

  function fmtTemp(value) {
    if (value === null || value === undefined || value === "") return "—";
    const n = Number(value);
    return Number.isFinite(n) ? `${Math.round(n)}°C` : String(value);
  }

  function row(label, value, ok) {
    const cls = ok === true ? "ok" : ok === false ? "bad" : "";
    return `<div class="status-row ${cls}"><span>${label}</span><strong>${value}</strong></div>`;
  }

  function render(data) {
    const local = data.local || {};
    const printer = data.printer || {};
    const ready = !!data.ready_to_print;
    readyEl.textContent = ready ? "Ready to print" : "Not ready";
    readyEl.dataset.state = ready ? "ready" : "blocked";

    const blockers = data.blockers || [];
    if (blockersEl) {
      if (blockers.length) {
        blockersEl.hidden = false;
        blockersEl.innerHTML = blockers.map((b) => `<li>${b}</li>`).join("");
      } else {
        blockersEl.hidden = true;
        blockersEl.innerHTML = "";
      }
    }

    if (!data.online) {
      gridEl.innerHTML = row("Printer", "Offline", false);
      return;
    }

    const sliceLabel = local.gcode_file
      ? `${local.gcode_file}${local.gcode_print_time ? ` · ${local.gcode_print_time}` : ""}`
      : "None — slice first";

    gridEl.innerHTML = [
      row("Filament", printer.filament_label || "Unknown", printer.filament_loaded),
      row("CFS", printer.cfs_connected ? "Connected" : "Not connected", printer.cfs_connected ? true : null),
      row("Printer", printer.print_state_label || "Unknown", printer.print_state === 0),
      row("Nozzle", fmtTemp(printer.nozzle_temp), null),
      row("Bed", fmtTemp(printer.bed_temp), null),
      row(
        "Slice file",
        sliceLabel,
        local.gcode_ready && !local.gcode_stale && !local.cad_stale
      ),
      row(
        "CAD export",
        local.cad_stale ? "Out of date — Re-slice" : "Up to date",
        !local.cad_stale
      ),
    ].join("");
  }

  async function refresh() {
    try {
      const data = await fetch("/api/printer/status").then((r) => r.json());
      render(data);
    } catch (_) {
      readyEl.textContent = "Status unavailable";
      readyEl.dataset.state = "blocked";
    }
  }

  window.printerStatus = { refresh, render };
  refresh();
})();
