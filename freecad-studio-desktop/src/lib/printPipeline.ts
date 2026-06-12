import type { Status } from "../api";
import { buildSliceReadiness } from "./sliceReadiness";

export type PipelineBlocker = {
  id: string;
  label: string;
  ok: boolean;
  fix: string;
};

export type PipelineGuide = {
  headline: string;
  detail: string;
  blockers: PipelineBlocker[];
  canExport: boolean;
  canSlice: boolean;
  canSend: boolean;
  sliceMode: "fresh" | "existing-stl" | "none";
  exportDisabledReason: string | null;
  sliceDisabledReason: string | null;
  sendDisabledReason: string | null;
};

export function buildPrintPipelineGuide(
  status: Status | null,
  busy: boolean,
): PipelineGuide {
  const cadReady = Boolean(status?.cad_ready ?? status?.rpc_connected);
  const hasModel = Boolean(status?.has_model);
  const hasJob = Boolean(status?.active_job_id);
  const sliceFresh = Boolean(status?.cad_stale || status?.gcode_stale);
  const gcodeReady = Boolean(status?.gcode_ready);
  const printerOnline = Boolean(status?.printer_online);
  const sliceReadiness = buildSliceReadiness(status, busy);

  const blockers: PipelineBlocker[] = [
    ...sliceReadiness.requirements.map((item) => ({
      id: item.id,
      label: item.label,
      ok: item.ok,
      fix: item.fix,
    })),
    {
      id: "printer",
      label: "Printer on WiFi",
      ok: printerOnline,
      fix: 'Turn printer on and click "Find Printer"',
    },
  ];

  let exportDisabledReason: string | null = null;
  if (busy) exportDisabledReason = "Wait for the current action to finish";
  else if (!hasJob) exportDisabledReason = "Create a job in the Design tab";
  else if (!hasModel) exportDisabledReason = "Build a model in the Design tab first";
  else if (!cadReady) exportDisabledReason = "Start FreeCAD (Start All Services)";

  let sliceDisabledReason = sliceReadiness.sliceDisabledReason;

  let sendDisabledReason: string | null = null;
  if (busy) sendDisabledReason = "Wait for the current action to finish";
  else if (!gcodeReady || sliceFresh)
    sendDisabledReason =
      status?.gcode_stale_reason ||
      status?.cad_stale_reason ||
      'Slice for printer first — your slice file is missing or out of date';
  else if (!printerOnline) sendDisabledReason = "Printer offline — click Find Printer";

  const canExport = exportDisabledReason === null;
  const canSlice = sliceReadiness.canSlice;
  const canSend = sendDisabledReason === null;

  let headline = "Prepare your model for printing";
  let detail = "Follow the checklist — locked buttons show what's still needed.";
  let sliceMode: PipelineGuide["sliceMode"] = "none";

  if (!hasJob || !hasModel) {
    headline = "Start in the Design tab";
    detail = "Create a job, describe your part, and click Build it in FreeCAD.";
  } else if (!cadReady) {
    headline = "Connect FreeCAD";
    detail = "Start All Services, then come back here to slice and send.";
  } else if (!canSlice) {
    headline = "Slicing unavailable";
    detail = sliceDisabledReason ?? detail;
  } else if (sliceFresh || !gcodeReady) {
    headline = "Ready to slice";
    detail =
      sliceFresh && gcodeReady
        ? "Your CAD changed since the last slice — click Slice for printer to refresh."
        : "Auto-orients, centers on the bed, and slices for your K2 (like Creality Print).";
    sliceMode = "fresh";
  } else if (!canSend) {
    headline = "Slice is ready — finish printer setup";
    detail = sendDisabledReason ?? "Check printer status below (filament, WiFi).";
    sliceMode = "existing-stl";
  } else {
    headline = "Ready to send";
    detail = `${status?.gcode_file ?? "Slice file"} · ${status?.printer_label ?? "Printer"} @ ${status?.printer_ip ?? ""}`;
    sliceMode = "existing-stl";
  }

  return {
    headline,
    detail,
    blockers,
    canExport,
    canSlice,
    canSend,
    sliceMode,
    exportDisabledReason,
    sliceDisabledReason,
    sendDisabledReason,
  };
}
