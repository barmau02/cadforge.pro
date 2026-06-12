import type { Status } from "../api";

export type SliceRequirementAction = "design" | "start-all" | "slice" | "settings";

export type SliceRequirement = {
  id: string;
  label: string;
  ok: boolean;
  fix: string;
  action?: SliceRequirementAction;
};

export type SliceReadiness = {
  requirements: SliceRequirement[];
  readyCount: number;
  totalCount: number;
  canSlice: boolean;
  sliceDisabledReason: string | null;
  sliceStale: boolean;
  gcodeReady: boolean;
  buttonLabel: string;
  buttonHint: string;
  highlight: boolean;
};

export function buildSliceReadiness(status: Status | null, busy: boolean): SliceReadiness {
  const hasJob = Boolean(status?.active_job_id);
  const hasModel = Boolean(status?.has_model);
  const cadReady = Boolean(status?.cad_ready ?? status?.rpc_connected);
  const orca = Boolean(status?.orca_installed);
  const sliceStale = Boolean(status?.cad_stale || status?.gcode_stale);
  const gcodeReady = Boolean(status?.gcode_ready);

  const requirements: SliceRequirement[] = [
    {
      id: "job",
      label: "Active job",
      ok: hasJob,
      fix: "Create or select a job in Design",
      action: "design",
    },
    {
      id: "model",
      label: "3D model built",
      ok: hasModel,
      fix: "Build your part in the Design tab",
      action: "design",
    },
    {
      id: "cad",
      label: "FreeCAD running",
      ok: cadReady,
      fix: "Click Start All in the top bar",
      action: "start-all",
    },
    {
      id: "orca",
      label: "OrcaSlicer installed",
      ok: orca,
      fix: "Install OrcaSlicer for one-click K2 slicing",
      action: "settings",
    },
    {
      id: "output",
      label: "Fresh slice on bed",
      ok: gcodeReady && !sliceStale,
      fix: sliceStale
        ? status?.cad_stale_reason ||
          status?.gcode_stale_reason ||
          "Slice again — CAD changed or slice is stale"
        : "Slice exports STL, auto-orients, centers on bed, creates K2 .gcode.3mf",
      action: "slice",
    },
  ];

  const readyCount = requirements.filter((r) => r.ok).length;
  const totalCount = requirements.length;

  let sliceDisabledReason: string | null = null;
  if (busy) sliceDisabledReason = "Wait for the current action to finish";
  else if (!orca) sliceDisabledReason = "Install OrcaSlicer for one-click slicing";
  else if (!hasJob) sliceDisabledReason = "Create a job in the Design tab";
  else if (!hasModel) sliceDisabledReason = "Build a model in the Design tab first";
  else if (!cadReady) sliceDisabledReason = "Start FreeCAD (Start All Services)";

  const canSlice = sliceDisabledReason === null;
  const needsSlice = canSlice && (sliceStale || !gcodeReady);

  let buttonLabel = "Slice for printer";
  if (busy) buttonLabel = "Slicing…";
  else if (!canSlice) buttonLabel = "Slice unavailable";
  else if (needsSlice) buttonLabel = "Slice for printer";
  else buttonLabel = "Re-slice";

  let buttonHint = "Auto-export, orient, center on K2 bed, slice to .gcode.3mf";
  if (sliceDisabledReason) buttonHint = sliceDisabledReason;
  else if (needsSlice && sliceStale) {
    buttonHint =
      status?.cad_stale_reason ||
      status?.gcode_stale_reason ||
      "Your model changed — slice again for correct placement";
  } else if (!needsSlice && status?.gcode_file) {
    buttonHint = `Current slice: ${status.gcode_file}`;
  }

  return {
    requirements,
    readyCount,
    totalCount,
    canSlice,
    sliceDisabledReason,
    sliceStale,
    gcodeReady,
    buttonLabel,
    buttonHint,
    highlight: needsSlice,
  };
}
