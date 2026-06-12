export const API = "http://127.0.0.1:8787";

export function previewDataUrl(image: string, mime = "image/png") {
  const binary = atob(image);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes], { type: mime }));
}

export function previewImageUrl(jobId?: string) {
  const params = new URLSearchParams({ t: String(Date.now()) });
  if (jobId) params.set("job_id", jobId);
  return `${API}/api/screenshot.png?${params}`;
}

export function stlPreviewUrl(jobId?: string) {
  const params = new URLSearchParams({ t: String(Date.now()) });
  if (jobId) params.set("job_id", jobId);
  return `${API}/api/preview/stl?${params}`;
}

export function gcodePreviewUrl(jobId?: string, file?: string) {
  const params = new URLSearchParams({ t: String(Date.now()) });
  if (jobId) params.set("job_id", jobId);
  if (file) params.set("file", file);
  return `${API}/api/preview/gcode?${params}`;
}

export function gcodeThumbnailUrl(jobId?: string, file?: string) {
  const params = new URLSearchParams({ t: String(Date.now()) });
  if (jobId) params.set("job_id", jobId);
  if (file) params.set("file", file);
  return `${API}/api/preview/gcode/thumbnail?${params}`;
}

export function cameraViewerUrl(printerIp: string) {
  const params = new URLSearchParams({ ip: printerIp, t: String(Date.now()) });
  return `${API}/static/camera-viewer.html?${params}`;
}

export function cameraSnapshotUrl(cacheBust?: number) {
  return `${API}/api/printer/camera/snapshot?t=${cacheBust ?? Date.now()}`;
}

export interface FeatureAuditItem {
  feature: string;
  status: "ok" | "wrong" | "missing" | string;
  expected?: string;
  observed?: string;
  fix?: string;
}

export interface LoopIteration {
  iteration: number;
  score: number | null;
  issues: string[];
  reasoning?: string;
  feature_audit?: FeatureAuditItem[];
  reference_match?: { provided?: boolean; score?: number; notes?: string };
}

export interface LoopProgress {
  state?: "running" | "done" | "error" | "idle";
  iteration?: number;
  max_iterations?: number;
  phase?: string;
  progress_percent?: number;
  code?: string;
  score?: number | null;
  issues?: string[];
  lessons_used?: number;
  required_features?: string[];
  feature_audit?: FeatureAuditItem[];
  reasoning?: string;
  reference_score?: number | null;
  thinking_log?: string[];
  result?: {
    ok: boolean;
    message?: string;
    error?: string;
    data?: {
      code?: string;
      job_id?: string;
      job?: Job;
      run_id?: number;
      iterations?: LoopIteration[];
      final_score?: number | null;
      lessons_used?: number;
      required_features?: { summary?: string; features?: { name: string; description: string }[] };
      preview_image?: string;
      preview_mime?: string;
    };
  };
}

export interface WorkflowStep {
  id: string;
  title: string;
  description: string;
  status: "done" | "active" | "pending" | "error";
  detail: string;
  action: string | null;
  optional: boolean;
}

export interface Workflow {
  steps: WorkflowStep[];
  progress_percent: number;
  done_count: number;
  total_count: number;
  current_step_id: string;
  current_step_title: string;
  current_step_detail: string;
  current_action: string | null;
}

export interface AiModelOption {
  id: string;
  name: string;
  vision: boolean;
  hint: string;
  size?: number;
}

export interface AiModelsResponse {
  models: AiModelOption[];
  current: string;
  current_vision?: boolean;
  provider: string;
  label: string;
  error?: string;
}

export interface JobSummary {
  id: string;
  title: string;
  freecad_doc: string;
  status: string;
  created_at: number;
  updated_at: number;
}

export interface Job extends JobSummary {
  prompt: string;
  code: string;
  prompt_history?: { prompt: string; kind: string; at: number }[];
  required_features?: { summary?: string; features?: { name: string; description?: string }[] };
}

export interface JobsResponse {
  active_job_id: string | null;
  jobs: JobSummary[];
  active_job: Job | null;
}

export interface FeatureTreeNode {
  id: string;
  kind: string;
  name: string;
  label?: string;
  value?: string | number | boolean | null;
  line?: number;
  editable?: boolean;
  operation?: string;
  type?: string;
  source?: string;
  children?: FeatureTreeNode[];
}

export interface FeatureTreeResponse {
  tree: FeatureTreeNode[];
  parameters: { name: string; value: string | number | null; line: number; editable: boolean }[];
  parameter_count: number;
  operation_count: number;
  doc_name?: string | null;
}

export interface ContextViewSpecDto {
  label: string;
  title: string;
  prompt: string;
  enabled: boolean;
}

export interface GeneratedContextImageDto {
  label: string;
  base64: string;
  prompt: string;
  error?: string;
}

export interface ContextImageDefaults {
  views: ContextViewSpecDto[];
  global_context_hint: string;
  grok_configured: boolean;
  image_gen_enabled: boolean;
}

export interface AppSettings {
  ai_provider: string;
  api_url: string;
  model: string;
  ollama_api_key_set: boolean;
  ollama_api_key_masked: string;
  grok_api_key_set: boolean;
  grok_api_key_masked: string;
  grok_image_model: string;
  grok_api_url: string;
  image_gen_enabled: boolean;
  ollama_key_url: string;
  grok_key_url: string;
}

export interface Status {
  rpc_connected: boolean;
  rpc_bridge_live?: boolean;
  cad_ready?: boolean;
  freecad_mode?: string;
  headless_ready?: boolean;
  freecad_cmd_path?: string | null;
  active_job_id?: string | null;
  active_job_title?: string | null;
  active_job_doc?: string | null;
  ai_configured: boolean;
  ai_provider?: string;
  ai_model?: string;
  ai_vision?: boolean;
  ai_label?: string;
  grok_configured?: boolean;
  image_gen_enabled?: boolean;
  grok_image_model?: string;
  has_model: boolean;
  object_count: number;
  stl_ready: boolean;
  stl_count: number;
  job_stl_dir?: string | null;
  job_stl_files?: string[];
  job_stl_ready?: boolean;
  job_stl_count?: number;
  background_freecad?: boolean;
  documents: string[];
  slicer_installed?: boolean;
  slicer_name?: string | null;
  printer_label?: string;
  bed_width_mm?: number;
  bed_depth_mm?: number;
  bed_height_mm?: number;
  bed_source?: string;
  slicer_download?: string;
  printer_online?: boolean;
  printer_ip?: string | null;
  printer_detail?: string;
  local_subnet?: string;
  gcode_ready?: boolean;
  gcode_file?: string | null;
  gcode_path?: string | null;
  gcode_dir?: string | null;
  job_output_dir?: string | null;
  gcode_print_time?: string | null;
  gcode_filament_g?: number | null;
  gcode_filament_mm?: number | null;
  gcode_layer_height?: number | null;
  gcode_layer_count?: number | null;
  gcode_has_thumbnail?: boolean;
  gcode_stale?: boolean;
  gcode_stale_reason?: string | null;
  cad_stale?: boolean;
  cad_stale_reason?: string | null;
  camera_available?: boolean;
  orca_installed?: boolean;
}

export interface PrinterLiveStatus {
  filament_loaded?: boolean;
  filament_label?: string;
  cfs_connected?: boolean;
  print_state?: number;
  print_state_label?: string;
  nozzle_temp?: number | string;
  bed_temp?: number | string;
  printer_ready?: boolean;
}

export interface PrinterStatusResponse {
  online: boolean;
  ready_to_print: boolean;
  blockers: string[];
  warnings?: string[];
  local?: {
    gcode_ready?: boolean;
    gcode_stale?: boolean;
    cad_stale?: boolean;
    cad_stale_reason?: string | null;
    gcode_file?: string | null;
    gcode_print_time?: string | null;
    gcode_filament_cm3?: number | null;
    gcode_layer_count?: number | null;
  };
  printer?: PrinterLiveStatus & { ip?: string; label?: string };
}

export interface ServiceItem {
  id: string;
  name: string;
  ok: boolean;
  detail: string;
}

export interface Services {
  studio_api: boolean;
  freecad_installed: boolean;
  freecad_running: boolean;
  rpc_bridge: boolean;
  orca_installed: boolean;
  creality_print_installed?: boolean;
  slicer_installed?: boolean;
  slicer_name?: string | null;
  printer_label?: string;
  printer_online?: boolean;
  printer_ip?: string | null;
  printer_detail?: string;
  all_ready: boolean;
  items: ServiceItem[];
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail || `HTTP ${res.status}`);
  return data as T;
}

export const api = {
  workflow: () => request<Workflow>("/api/workflow"),
  status: () => request<Status>("/api/status"),
  services: () => request<Services>("/api/services"),
  startAll: () =>
    request<{ message: string; data?: { services?: Services } }>("/api/start-all", { method: "POST" }),
  openRpc: () =>
    request<{ message: string; data?: { services?: Services } }>("/api/open/rpc", { method: "POST" }),
  focusFreecad: () => request<{ message: string }>("/api/freecad/focus", { method: "POST" }),
  openFreecad: () => request<{ message: string }>("/api/open/freecad", { method: "POST" }),
  settings: () => request<AppSettings>("/api/settings"),
  updateSettings: (patch: Record<string, unknown>) =>
    request<{ message: string; data?: { settings?: AppSettings; updated?: string[] } }>(
      "/api/settings",
      { method: "POST", body: JSON.stringify(patch) },
    ),
  aiModels: () => request<AiModelsResponse>("/api/ai/models"),
  setAiModel: (model: string) =>
    request<{ message: string; data?: { model?: string; vision?: boolean } }>("/api/ai/model", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
  jobs: () => request<JobsResponse>("/api/jobs"),
  createJob: (title = "Untitled part", prompt = "") =>
    request<{ message: string; data?: { job?: Job } }>("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ title, prompt }),
    }),
  activateJob: (jobId: string) =>
    request<{ message: string; data?: { job?: Job } }>(`/api/jobs/${jobId}/activate`, {
      method: "POST",
    }),
  updateJob: (jobId: string, patch: Partial<Pick<Job, "title" | "prompt" | "code" | "status">>) =>
    request<{ message: string; data?: { job?: Job } }>(`/api/jobs/${jobId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteJob: (jobId: string) =>
    request<{ message: string; data?: { job_id?: string } }>(`/api/jobs/${jobId}`, {
      method: "DELETE",
    }),
  promptGenerate: (
    prompt: string,
    opts?: {
      imageBase64?: string;
      imageMime?: string;
      existingCode?: string;
      editMode?: boolean;
      jobId?: string;
      globalImageContext?: string;
      contextViewSpecs?: ContextViewSpecDto[];
      contextImages?: Array<{ label: string; base64: string; prompt: string }>;
    },
  ) =>
    request<{
      message: string;
      data?: {
        code?: string;
        used_image?: boolean;
        edit_mode?: boolean;
        used_scene_preview?: boolean;
        spatial_views?: string[];
        job_id?: string;
        job?: Job;
      };
    }>("/api/prompt", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        execute: false,
        edit_mode: Boolean(opts?.editMode),
        use_scene_preview: true,
        ...(opts?.jobId ? { job_id: opts.jobId } : {}),
        ...(opts?.existingCode ? { existing_code: opts.existingCode } : {}),
        ...(opts?.imageBase64
          ? { image_base64: opts.imageBase64, image_mime: opts.imageMime }
          : {}),
        ...(opts?.globalImageContext !== undefined
          ? { global_image_context: opts.globalImageContext }
          : {}),
        ...(opts?.contextViewSpecs ? { context_view_specs: opts.contextViewSpecs } : {}),
        ...(opts?.contextImages?.length ? { context_images: opts.contextImages } : {}),
      }),
    }),
  execute: (code: string, jobId?: string, focusWindow?: boolean) =>
    request<{
      message: string;
      data?: {
        preview_image?: string;
        preview_mime?: string;
        job_id?: string;
        job?: Job;
        progress?: string;
        execution_output?: string;
        code?: string;
        auto_fixed?: boolean;
      };
    }>("/api/execute", {
      method: "POST",
      body: JSON.stringify({
        code,
        capture_preview: true,
        ...(jobId ? { job_id: jobId } : {}),
        ...(focusWindow === false ? { focus_window: false } : {}),
      }),
    }),
  exportStl: (jobId?: string) =>
    request<{ message: string; data?: { files?: string[]; dir?: string; job_id?: string } }>(
      "/api/export/stl",
      {
        method: "POST",
        body: JSON.stringify(jobId ? { job_id: jobId } : {}),
      },
    ),
  discoverPrinter: () =>
    request<{ ok: boolean; message: string; data?: Record<string, unknown> }>("/api/printer/discover", {
      method: "POST",
    }),
  openSlicer: () => request<{ message: string }>("/api/open/slicer", { method: "POST" }),
  sliceGcode: () =>
    request<{ message: string; data?: Record<string, unknown> }>("/api/slice/gcode", {
      method: "POST",
    }),
  resliceGcode: () =>
    request<{ message: string; data?: Record<string, unknown> }>("/api/slice/reslice", {
      method: "POST",
    }),
  printerStatus: () => request<PrinterStatusResponse>("/api/printer/status"),
  preflightPrint: (jobId?: string, file?: string) => {
    const params = new URLSearchParams();
    if (jobId) params.set("job_id", jobId);
    if (file) params.set("file", file);
    const q = params.toString();
    return request<{ ok: boolean; blockers?: string[]; warnings?: string[] }>(
      `/api/printer/preflight${q ? `?${q}` : ""}`,
    );
  },
  exchangeCameraWebRtc: (offer: string) =>
    request<{ answer: string }>("/api/printer/camera/webrtc", {
      method: "POST",
      body: JSON.stringify({ offer }),
    }),
  sendPrint: (gcodeFile?: string) =>
    request<{
      message: string;
      data?: { preflight?: { warnings?: string[] } };
    }>("/api/send/print", {
      method: "POST",
      body: JSON.stringify(gcodeFile ? { gcode_file: gcodeFile } : {}),
    }),
  openOrca: () => request<{ message: string }>("/api/open/orcaslicer", { method: "POST" }),
  buildLoop: (
    prompt: string,
    opts?: {
      jobId?: string;
      maxIterations?: number;
      imageBase64?: string;
      imageMime?: string;
      editMode?: boolean;
      existingCode?: string;
      globalImageContext?: string;
      contextViewSpecs?: ContextViewSpecDto[];
      contextImages?: Array<{ label: string; base64: string; prompt: string }>;
    },
  ) =>
    request<{
      message: string;
      data?: {
        job_id?: string;
        async?: boolean;
        vision?: boolean;
      };
    }>("/api/build/loop", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        ...(opts?.jobId ? { job_id: opts.jobId } : {}),
        ...(opts?.maxIterations ? { max_iterations: opts.maxIterations } : {}),
        ...(opts?.editMode ? { edit_mode: true } : {}),
        ...(opts?.existingCode ? { existing_code: opts.existingCode } : {}),
        ...(opts?.imageBase64
          ? { image_base64: opts.imageBase64, image_mime: opts.imageMime }
          : {}),
        ...(opts?.globalImageContext !== undefined
          ? { global_image_context: opts.globalImageContext }
          : {}),
        ...(opts?.contextViewSpecs ? { context_view_specs: opts.contextViewSpecs } : {}),
        ...(opts?.contextImages?.length ? { context_images: opts.contextImages } : {}),
      }),
    }),
  contextImageDefaults: () => request<ContextImageDefaults>("/api/image/context/defaults"),
  generateContextImages: (opts: {
    imageBase64: string;
    imageMime?: string;
    globalContext?: string;
    views?: ContextViewSpecDto[];
    onlyLabel?: string;
    chainAnchorBase64?: string;
    chainAnchorMime?: string;
  }) =>
    request<{ ok: boolean; message: string; data?: { images?: GeneratedContextImageDto[] } }>(
      "/api/image/context/generate",
      {
        method: "POST",
        body: JSON.stringify({
          image_base64: opts.imageBase64,
          image_mime: opts.imageMime,
          global_context: opts.globalContext ?? "",
          views: opts.views,
          only_label: opts.onlyLabel,
          chain_anchor_base64: opts.chainAnchorBase64,
          chain_anchor_mime: opts.chainAnchorMime,
        }),
      },
    ),
  buildLoopStatus: (jobId: string) =>
    request<LoopProgress>(`/api/build/loop/status?job_id=${encodeURIComponent(jobId)}`),
  screenshot: (jobId?: string) => {
    const params = new URLSearchParams({ view: "Isometric" });
    if (jobId) params.set("job_id", jobId);
    return request<{ image: string; mime: string; preview_url?: string }>(
      `/api/screenshot?${params}`,
    );
  },
  featureTree: (jobId?: string) => {
    const params = jobId ? `?job_id=${encodeURIComponent(jobId)}` : "";
    return request<FeatureTreeResponse>(`/api/features/tree${params}`);
  },
  patchFeatureParam: (name: string, value: number | string, opts?: { jobId?: string; rerun?: boolean }) =>
    request<{ ok: boolean; message: string; data?: { code?: string; tree?: FeatureTreeResponse } }>(
      "/api/features/param",
      {
        method: "POST",
        body: JSON.stringify({
          name,
          value,
          rerun: opts?.rerun ?? true,
          ...(opts?.jobId ? { job_id: opts.jobId } : {}),
        }),
      },
    ),
  patchFeatureConfig: (key: string, value: string) =>
    request<{ ok: boolean; message: string; data?: { tree?: FeatureTreeResponse } }>(
      "/api/features/config",
      {
        method: "POST",
        body: JSON.stringify({ key, value }),
      },
    ),
};