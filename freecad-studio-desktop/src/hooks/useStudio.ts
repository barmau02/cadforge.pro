import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  previewDataUrl,
  previewImageUrl,
  stlPreviewUrl,
  Workflow,
  Status,
  Services,
  AiModelsResponse,
  Job,
  JobSummary,
  LoopProgress,
  FeatureTreeResponse,
} from "../api";

export type ConceptImage = {
  base64: string;
  mime: string;
  preview: string;
  name: string;
};

export type ContextViewSpec = {
  label: string;
  title: string;
  prompt: string;
  enabled: boolean;
};

export type GeneratedContextImage = {
  label: string;
  base64: string;
  prompt: string;
  preview?: string;
  error?: string;
};

const ACTION_LABELS: Record<string, string> = {
  "start-all": "Start All Services",
  "open-rpc": "Connect FreeCAD",
  "prompt-build": "Build Model",
  "export-stl": "Export STL",
  "open-slicer": "Open Slicer",
  "open-orca": "Open Slicer",
  "slice-gcode": "Auto-Slice",
  "reslice-gcode": "Regenerate slice",
  "send-print": "Send to Printer",
  screenshot: "Refresh Preview",
};

export type Section = "workflow" | "design" | "print" | "settings" | "logs";

const INITIAL_CODE = "# Python appears here after you prompt\n";

function hasEditableCode(code: string) {
  const trimmed = code.trim();
  return Boolean(trimmed) && trimmed !== INITIAL_CODE.trim();
}

function isVisionBuild(status: Status | null, aiModels: AiModelsResponse | null): boolean {
  if (status?.ai_vision != null) return status.ai_vision;
  if (aiModels?.current_vision != null) return aiModels.current_vision;
  const current = aiModels?.models.find((m) => m.id === aiModels.current);
  return Boolean(current?.vision);
}

export function useStudio() {
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [services, setServices] = useState<Services | null>(null);
  const [prompt, setPrompt] = useState("");
  const [aiModels, setAiModels] = useState<AiModelsResponse | null>(null);
  const [conceptImage, setConceptImage] = useState<ConceptImage | null>(null);
  const [contextGlobal, setContextGlobal] = useState("");
  const [contextGlobalHint, setContextGlobalHint] = useState(
    "Scale (mm), material/color, must-keep features, style…",
  );
  const [contextViewSpecs, setContextViewSpecs] = useState<ContextViewSpec[]>([]);
  const [generatedContextImages, setGeneratedContextImages] = useState<GeneratedContextImage[]>([]);
  const [contextGenerating, setContextGenerating] = useState(false);
  const [code, setCode] = useState(INITIAL_CODE);
  const [modelReady, setModelReady] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [stlUrl, setStlUrl] = useState<string | null>(null);
  const [loopProgress, setLoopProgress] = useState<LoopProgress | null>(null);
  const [featureTree, setFeatureTree] = useState<FeatureTreeResponse | null>(null);
  const [featureTreeLoading, setFeatureTreeLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>(["PromptForge ready."]);
  const [busy, setBusy] = useState(false);
  const [buildPhase, setBuildPhase] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("design");
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const previewObjectUrl = useRef<string | null>(null);

  const clearPreview = useCallback(() => {
    if (previewObjectUrl.current) {
      URL.revokeObjectURL(previewObjectUrl.current);
      previewObjectUrl.current = null;
    }
    setPreview(null);
    setPreviewError(null);
    setStlUrl(null);
  }, []);

  const refreshStl = useCallback((jobId?: string | null) => {
    setStlUrl(stlPreviewUrl(jobId ?? undefined));
    setPreviewError(null);
  }, []);

  const setPreviewFromBase64 = useCallback((image: string, mime = "image/png") => {
    if (previewObjectUrl.current) {
      URL.revokeObjectURL(previewObjectUrl.current);
      previewObjectUrl.current = null;
    }
    const url = previewDataUrl(image, mime);
    previewObjectUrl.current = url;
    setPreview(url);
    setPreviewError(null);
  }, []);

  useEffect(() => () => {
    if (previewObjectUrl.current) URL.revokeObjectURL(previewObjectUrl.current);
  }, []);

  const log = useCallback((msg: string) => {
    const t = new Date().toLocaleTimeString();
    setLogs((prev) => [`[${t}] ${msg}`, ...prev].slice(0, 80));
  }, []);

  const capturePreview = useCallback(async (jobId?: string | null) => {
    const resolvedJobId = jobId ?? activeJobId ?? undefined;
    setBuildPhase("Capturing 3D preview from FreeCAD…");
    try {
      const res = await fetch(previewImageUrl(resolvedJobId));
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || `Preview failed (HTTP ${res.status})`);
      }
      const blob = await res.blob();
      if (blob.size < 100) {
        throw new Error("FreeCAD returned an empty preview image.");
      }
      if (previewObjectUrl.current) {
        URL.revokeObjectURL(previewObjectUrl.current);
        previewObjectUrl.current = null;
      }
      const url = URL.createObjectURL(blob);
      previewObjectUrl.current = url;
      setPreview(url);
      setPreviewError(null);
      refreshStl(resolvedJobId);
      log("Preview updated.");
    } catch (shotErr) {
      const msg = (shotErr as Error).message;
      if (previewObjectUrl.current) {
        URL.revokeObjectURL(previewObjectUrl.current);
        previewObjectUrl.current = null;
      }
      setPreview(null);
      setPreviewError(msg);
      log(`Preview: ${msg}`);
    } finally {
      setBuildPhase(null);
    }
  }, [activeJobId, clearPreview, log, refreshStl]);

  const refreshPreviewMesh = useCallback(
    async (jobId?: string | null) => {
      const resolvedJobId = jobId ?? activeJobId ?? undefined;
      setBuildPhase("Refreshing 3D mesh from FreeCAD…");
      try {
        refreshStl(resolvedJobId);
        log("3D preview mesh refreshed.");
      } catch (e) {
        const msg = (e as Error).message;
        setPreviewError(msg);
        log(`3D preview: ${msg}`);
      } finally {
        setBuildPhase(null);
      }
    },
    [activeJobId, log, refreshStl],
  );

  const applyJob = useCallback((job: Job) => {
    setActiveJobId(job.id);
    setPrompt(job.prompt || "");
    setCode(job.code || INITIAL_CODE);
    setModelReady(job.status === "built" || job.status === "draft" || hasEditableCode(job.code || ""));
    setConceptImage(null);
  }, []);

  const loadJobs = useCallback(async () => {
    try {
      const data = await api.jobs();
      setJobs(data.jobs);
      setActiveJobId(data.active_job_id);
      if (data.active_job) {
        setPrompt(data.active_job.prompt || "");
        setCode(data.active_job.code || INITIAL_CODE);
        setModelReady(
          data.active_job.status === "built"
            || data.active_job.status === "draft"
            || hasEditableCode(data.active_job.code || ""),
        );
      }
    } catch (e) {
      log(`Jobs: ${(e as Error).message}`);
    }
  }, [log]);

  const ensureFreecadReady = useCallback(
    async (background = true) => {
      const st = await api.status().catch(() => null);
      if (st?.cad_ready ?? st?.rpc_connected) return;
      if (st?.freecad_mode === "headless") {
        log("Starting headless CAD engine…");
        await api.startAll();
        const next = await api.status();
        if (next.cad_ready ?? next.rpc_connected) {
          log("Headless CAD ready.");
          return;
        }
        throw new Error("FreeCADCmd not found — install FreeCAD or set freecad_cmd_path in config.toml.");
      }
      log(background ? "Starting FreeCAD in background…" : "Starting FreeCAD…");
      await api.startAll();
      for (let i = 0; i < 15; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const next = await api.status();
        if (next.cad_ready ?? next.rpc_connected) {
          log("FreeCAD connected.");
          return;
        }
      }
      throw new Error("FreeCAD RPC not ready — check the FreeCAD window.");
    },
    [log],
  );

  const runPythonInFreecad = useCallback(
    async (python: string, phase?: string, jobId?: string | null) => {
      if (!python.trim()) throw new Error("No Python code to run.");
      if (phase) setBuildPhase(phase);
      const background = status?.background_freecad !== false;
      await ensureFreecadReady(background);
      const resolvedJobId = jobId ?? activeJobId ?? undefined;
      setBuildPhase(phase ?? "Running Python in FreeCAD…");
      const r = await api.execute(python, resolvedJobId, background ? false : undefined);
      if (r.data?.auto_fixed && r.data?.code) {
        setCode(r.data.code);
        log("AI auto-repaired the script after an execution error.");
      }
      if (r.data?.execution_output) log(r.data.execution_output);
      if (r.data?.progress) setBuildPhase(r.data.progress);
      if (r.data?.preview_image && r.data.preview_image.length > 100) {
        setPreviewFromBase64(r.data.preview_image, r.data.preview_mime ?? "image/png");
        log("Preview captured from FreeCAD.");
      } else {
        setBuildPhase("Capturing 3D preview…");
        await capturePreview(resolvedJobId);
      }
      refreshStl(resolvedJobId);
      return r;
    },
    [activeJobId, capturePreview, ensureFreecadReady, log, refreshStl, setPreviewFromBase64, status?.background_freecad],
  );

  const refresh = useCallback(async () => {
    try {
      const [wf, st, sv] = await Promise.all([api.workflow(), api.status(), api.services()]);
      setWorkflow(wf);
      setStatus(st);
      setServices(sv);
      if (st.active_job_id) setActiveJobId(st.active_job_id);
    } catch (e) {
      log(`Connection error: ${(e as Error).message}`);
    }
  }, [log]);

  const loadAiModels = useCallback(async () => {
    try {
      const models = await api.aiModels();
      setAiModels(models);
    } catch (e) {
      log(`AI models: ${(e as Error).message}`);
    }
  }, [log]);

  useEffect(() => {
    refresh();
    loadAiModels();
    loadJobs();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [refresh, loadAiModels, loadJobs]);

  useEffect(() => {
    if (!conceptImage || status?.image_gen_enabled !== true) {
      setContextViewSpecs([]);
      setGeneratedContextImages([]);
      setContextGlobal("");
      return;
    }
    let cancelled = false;
    void api.contextImageDefaults().then((defaults) => {
      if (cancelled) return;
      setContextViewSpecs(defaults.views);
      if (defaults.global_context_hint) setContextGlobalHint(defaults.global_context_hint);
    }).catch((e) => log(`Context defaults: ${(e as Error).message}`));
    return () => {
      cancelled = true;
    };
  }, [conceptImage, status?.image_gen_enabled, log]);

  const contextBuildPayload = useCallback(
    () => {
      if (status?.image_gen_enabled !== true) {
        return {};
      }
      return {
        globalImageContext: contextGlobal,
        contextViewSpecs: contextViewSpecs.map(({ label, title, prompt, enabled }) => ({
          label,
          title,
          prompt,
          enabled,
        })),
        contextImages: generatedContextImages
          .filter((g) => g.base64)
          .map(({ label, base64, prompt }) => ({ label, base64, prompt })),
      };
    },
    [status?.image_gen_enabled, contextGlobal, contextViewSpecs, generatedContextImages],
  );

  const generateContextPreviews = useCallback(
    async (onlyLabel?: string) => {
      if (!conceptImage || status?.image_gen_enabled !== true) return;
      setContextGenerating(true);
      try {
        const payload = contextBuildPayload();
        const iso = generatedContextImages.find(
          (g) => g.label === "generated_isometric" && g.base64,
        );
        const useChainAnchor =
          onlyLabel && onlyLabel !== "generated_isometric" && iso?.base64;
        const r = await api.generateContextImages({
          imageBase64: conceptImage.base64,
          imageMime: conceptImage.mime,
          globalContext: payload.globalImageContext,
          views: payload.contextViewSpecs,
          onlyLabel,
          chainAnchorBase64: useChainAnchor ? iso.base64 : undefined,
          chainAnchorMime: useChainAnchor ? conceptImage.mime : undefined,
        });
        const images = (r.data?.images ?? []) as GeneratedContextImage[];
        const withPreview = images.map((img) => ({
          ...img,
          preview: img.base64 ? previewDataUrl(img.base64) : undefined,
        }));
        if (onlyLabel) {
          setGeneratedContextImages((prev) => {
            const map = new Map(prev.map((p) => [p.label, p]));
            for (const img of withPreview) map.set(img.label, img);
            return Array.from(map.values());
          });
        } else {
          setGeneratedContextImages(withPreview);
        }
        log(r.message);
      } catch (e) {
        log(`Context images: ${(e as Error).message}`);
      } finally {
        setContextGenerating(false);
      }
    },
    [conceptImage, status?.image_gen_enabled, contextBuildPayload, generatedContextImages, log],
  );

  const updateContextViewSpec = useCallback((label: string, prompt: string) => {
    setContextViewSpecs((prev) =>
      prev.map((v) => (v.label === label ? { ...v, prompt } : v)),
    );
  }, []);

  const toggleContextView = useCallback((label: string, enabled: boolean) => {
    setContextViewSpecs((prev) =>
      prev.map((v) => (v.label === label ? { ...v, enabled } : v)),
    );
  }, []);

  useEffect(() => {
    if (status?.has_model) setModelReady(true);
  }, [status?.has_model]);

  useEffect(() => {
    const cadReady = status?.cad_ready ?? status?.rpc_connected;
    if (!activeJobId || !cadReady) return;
    if (!modelReady && !status?.has_model) return;
    refreshStl(activeJobId);
  }, [activeJobId, modelReady, refreshStl, status?.has_model, status?.rpc_connected, status?.cad_ready]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await new Promise((r) => setTimeout(r, 1500));
      try {
        const st = await api.status();
        if (cancelled || st.cad_ready || st.rpc_connected) return;
        if (st.freecad_mode === "headless") {
          log("Headless CAD offline — checking FreeCADCmd…");
        } else {
          log("FreeCAD offline — starting services…");
        }
        const r = await api.startAll();
        if (cancelled) return;
        log(r.message);
        for (let i = 0; i < 15; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          if (cancelled) return;
          const next = await api.status();
          if (next.cad_ready || next.rpc_connected) {
            log(st.freecad_mode === "headless" ? "Headless CAD ready." : "FreeCAD connected.");
            await refresh();
            return;
          }
        }
        log(
          st.freecad_mode === "headless"
            ? "FreeCADCmd not ready — check config.toml freecad_cmd_path."
            : "Still waiting for FreeCAD RPC — check the FreeCAD window.",
        );
      } catch {
        /* backend not up yet */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [log, refresh]);

  const runAction = async (action: string) => {
    if (busy) return;
    setBusy(true);
    try {
      if (action === "start-all" || action === "open-rpc") {
        const r = action === "start-all" ? await api.startAll() : await api.openRpc();
        log(r.message);
        if (r.data?.services) setServices(r.data.services);
        for (let i = 0; i < 12; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          await refresh();
          const st = await api.status();
          if (st.cad_ready || st.rpc_connected) {
            log("All services ready.");
            break;
          }
        }
        return;
      }
      if (action === "prompt-build") {
        if (!prompt.trim()) {
          throw new Error(modelReady ? "Describe what you want to change." : "Describe what you want to build.");
        }
        if (conceptImage && !status?.ai_vision) {
          throw new Error("Pick a vision model (Vision group) before building from an image.");
        }

        const isEdit = Boolean(activeJobId) && hasEditableCode(code);
        const buildLabel = isEdit
          ? `Applying change: ${prompt}`
          : conceptImage
            ? `Building from image + prompt: ${prompt}`
            : `Building: ${prompt}`;
        log(buildLabel);
        const background = status?.background_freecad !== false;
        setLoopProgress(null);
        setBuildPhase(background ? "Preparing FreeCAD in background…" : "Opening FreeCAD…");
        await ensureFreecadReady(background);

        const useVisionLoop = isVisionBuild(status, aiModels);
        if (useVisionLoop) {
          let jobId = activeJobId;
          if (!jobId) {
            const created = await api.createJob(prompt.trim().slice(0, 48) || "New part");
            const job = created.data?.job;
            if (!job) throw new Error("Could not create a job for the AI loop.");
            jobId = job.id;
            setActiveJobId(jobId);
            applyJob(job);
            await loadJobs();
          }

          setBuildPhase("Starting AI vision loop…");
          setLoopProgress({
            state: "running",
            phase: "Starting…",
            progress_percent: 2,
            thinking_log: [],
          });
          setSection("design");

          const ctxPayload = contextBuildPayload();
          const start = await api.buildLoop(prompt, {
            jobId,
            imageBase64: conceptImage?.base64,
            imageMime: conceptImage?.mime,
            editMode: isEdit,
            existingCode: isEdit ? code : undefined,
            ...ctxPayload,
          });
          jobId = start.data?.job_id ?? jobId;
          setActiveJobId(jobId);

          let lastLogLen = 0;
          let lastReasoning = "";
          let finalProgress: LoopProgress | null = null;

          for (let wait = 0; wait < 600; wait++) {
            await new Promise((r) => setTimeout(r, 800));
            const p = await api.buildLoopStatus(jobId);
            finalProgress = p;
            setLoopProgress(p);
            if (p.phase) setBuildPhase(p.phase);
            if (p.code?.trim()) setCode(p.code);
            if (p.reasoning && p.reasoning !== lastReasoning) {
              lastReasoning = p.reasoning;
              log(`Reasoning: ${p.reasoning}`);
            }
            const thinking = p.thinking_log ?? [];
            for (let i = lastLogLen; i < thinking.length; i++) {
              log(thinking[i]);
            }
            lastLogLen = thinking.length;
            if (p.state === "done" || p.state === "error") break;
          }

          const result = finalProgress?.result;
          if (!result?.ok) {
            throw new Error(result?.error ?? finalProgress?.phase ?? "AI vision loop failed");
          }
          const data = result.data;
          if (data?.code) setCode(data.code);
          if (data?.job_id) setActiveJobId(data.job_id);
          if (data?.job) applyJob(data.job);
          setModelReady(true);
          if (data?.preview_image && data.preview_image.length > 100) {
            setPreviewFromBase64(data.preview_image, data.preview_mime ?? "image/png");
          }
          refreshStl(data?.job_id ?? jobId);
          if (data?.required_features?.summary) log(`Plan: ${data.required_features.summary}`);
          for (const it of data?.iterations ?? []) {
            if (it.score != null) log(`Final inspection ${it.iteration}: score ${it.score}/100`);
          }
          if (data?.lessons_used) log(`Used ${data.lessons_used} lesson(s) from past builds.`);
          if ((data as { incomplete?: boolean }).incomplete) {
            const missing = (data as { missing_features?: string[] }).missing_features ?? [];
            log(`Build incomplete — still missing: ${missing.join(", ")}`);
            log("Tip: use Apply changes to request specific fillets, or edit the Python directly.");
          }
          log(result.message ?? "Build complete");
          setLoopProgress(finalProgress);
          await loadJobs();
          await refresh();
          return;
        }
        log(
          isEdit
            ? "Editing with full job context (prior prompts + existing Python)…"
            : background
            ? "FreeCAD runs minimized — progress shows here, preview appears when done."
            : isEdit
              ? "Updating model from your description — Python will regenerate, run, and refresh preview."
              : "FreeCAD is open — Python will generate, run automatically, then you can edit with more prompts or code.",
        );

        setBuildPhase(isEdit ? "Updating model from your description…" : "Generating Python from AI…");
        setLoopProgress({
          state: "running",
          phase: isEdit ? "Updating model from your description…" : "Generating Python from AI…",
          progress_percent: 12,
          thinking_log: [],
        });
        const ctxPayload = contextBuildPayload();
        const gen = await api.promptGenerate(prompt, {
          imageBase64: conceptImage?.base64,
          imageMime: conceptImage?.mime,
          existingCode: isEdit ? code : undefined,
          editMode: isEdit,
          jobId: activeJobId ?? undefined,
          ...ctxPayload,
        });
        const generated = gen.data?.code;
        if (!generated) throw new Error("AI did not return Python code.");
        setCode(generated);
        setLoopProgress({
          state: "running",
          phase: isEdit ? "Running updated Python in FreeCAD…" : "Running Python in FreeCAD…",
          progress_percent: 55,
          code: generated,
        });
        log(
          isEdit
            ? "Updated Python generated — running automatically in FreeCAD…"
            : "Python generated — running automatically in FreeCAD…",
        );

        const run = await runPythonInFreecad(
          generated,
          isEdit ? "Applying changes in FreeCAD…" : "Running Python in FreeCAD…",
          gen.data?.job_id ?? activeJobId,
        );
        if (gen.data?.job_id) setActiveJobId(gen.data.job_id);
        if (gen.data?.job) applyJob(gen.data.job);
        setModelReady(true);
        setLoopProgress({
          state: "done",
          phase: run.message || "Build complete",
          progress_percent: 100,
          code: generated,
        });
        const extras: string[] = [];
        if (gen.data?.used_image) extras.push("concept image");
        if (gen.data?.spatial_views?.length) {
          extras.push(`${gen.data.spatial_views.length} angles (${gen.data.spatial_views.join(", ")})`);
        } else if (gen.data?.used_scene_preview) {
          extras.push("current 3D view");
        }
        const suffix = extras.length ? ` (used ${extras.join(" + ")})` : "";
        log(
          isEdit
            ? `${run.message || "Model updated."}${suffix}`
            : gen.data?.used_image
              ? `${run.message} (built from concept image)`
              : run.message || "Model built in FreeCAD.",
        );
        await loadJobs();
        await refresh();
        return;
      }
      if (action === "show-freecad") {
        const r = await api.focusFreecad().catch(() => api.openFreecad());
        log(r.message);
        return;
      }
      if (action === "run-code") {
        log("Rerunning your edited Python in FreeCAD…");
        const r = await runPythonInFreecad(code, "Running edited Python in FreeCAD…", activeJobId);
        setModelReady(true);
        if (r.data?.job) applyJob(r.data.job);
        log(r.message || "Rerun complete.");
        await loadJobs();
        await refresh();
        return;
      }
      if (action === "export-stl") {
        const r = await api.exportStl(activeJobId ?? undefined);
        const dir = r.data?.dir;
        const count = r.data?.files?.length ?? 0;
        log(dir ? `${r.message} — ${count} file(s) in ${dir}` : r.message);
        await refresh();
        return;
      }
      if (action === "open-slicer" || action === "open-orca") {
        const r = await api.openSlicer();
        log(r.message);
        return;
      }
      if (action === "slice-gcode") {
        log(
          status?.cad_stale
            ? "Slicing with fresh STL export (model changed since last export)…"
            : "Slicing with OrcaSlicer…",
        );
        const r = await api.sliceGcode();
        log(r.message);
        refreshStl(activeJobId);
        await refresh();
        return;
      }
      if (action === "reslice-gcode") {
        log("Regenerating slice from latest FreeCAD model (export STL, wipe old slice)…");
        const r = await api.resliceGcode();
        log(r.message);
        refreshStl(activeJobId);
        await refresh();
        return;
      }
      if (action === "send-print") {
        log(`Sending ${status?.gcode_file ?? "slice file"} to ${status?.printer_ip ?? "printer"}…`);
        const r = await api.sendPrint(status?.gcode_file ?? undefined);
        const notes = r.data?.preflight?.warnings;
        if (notes?.length) {
          log(`Preflight note: ${notes.join("; ")}`);
        }
        log(r.message);
        await refresh();
        return;
      }
      if (action === "screenshot" || action === "refresh-preview") {
        await refreshPreviewMesh();
        return;
      }
    } catch (e) {
      const message = (e as Error).message;
      log(`Error: ${message}`);
      setLoopProgress((prev) =>
        prev?.state === "running"
          ? { ...prev, state: "error", phase: message, progress_percent: prev.progress_percent ?? 0 }
          : prev,
      );
    } finally {
      setBuildPhase(null);
      setBusy(false);
    }
  };

  const setAiModel = async (model: string) => {
    setBusy(true);
    try {
      const r = await api.setAiModel(model);
      log(r.message);
      await loadAiModels();
      await refresh();
    } catch (e) {
      log(`Error: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const attachConceptImage = (file: File) => {
    if (!file.type.startsWith("image/")) {
      log("Please upload a PNG, JPG, or WebP image.");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      log("Image too large — use a file under 8 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.includes(",") ? result.split(",", 2)[1] : result;
      setConceptImage({
        base64,
        mime: file.type,
        preview: result,
        name: file.name,
      });
      log(`Concept image attached: ${file.name}`);
      const visionDefault = aiModels?.models.find((m) => m.id === "qwen3-vl:235b-instruct")
        ?? aiModels?.models.find((m) => m.vision);
      if (visionDefault && !aiModels?.current_vision && aiModels?.current !== visionDefault.id) {
        void setAiModel(visionDefault.id);
      }
    };
    reader.readAsDataURL(file);
  };

  const clearConceptImage = () => setConceptImage(null);

  const createJob = async (title = "New part") => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.createJob(title);
      const job = r.data?.job;
      if (!job) throw new Error("Job was not created.");
      clearPreview();
      applyJob(job);
      await loadJobs();
      log(`New job: ${job.title} (${job.freecad_doc})`);
    } catch (e) {
      log(`Error: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const renameJob = async (jobId: string, title: string) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.updateJob(jobId, { title });
      const job = r.data?.job;
      if (job) applyJob(job);
      await loadJobs();
      log(`Renamed job to: ${title}`);
    } catch (e) {
      log(`Error: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const deleteJob = async (jobId: string) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.deleteJob(jobId);
      log(r.message);
      await loadJobs();
      const data = await api.jobs();
      if (data.active_job) {
        applyJob(data.active_job);
      } else {
        setActiveJobId(null);
        setPrompt("");
        setCode(INITIAL_CODE);
        setModelReady(false);
        clearPreview();
      }
      await refresh();
    } catch (e) {
      log(`Error: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const selectJob = async (jobId: string) => {
    if (busy || jobId === activeJobId) return;
    setBusy(true);
    try {
      const r = await api.activateJob(jobId);
      const job = r.data?.job;
      if (!job) throw new Error("Job not found.");
      clearPreview();
      applyJob(job);
      await loadJobs();
      log(`Switched to job: ${job.title}`);
      if (job.status === "built" || hasEditableCode(job.code || "")) {
        refreshStl(jobId);
      }
    } catch (e) {
      log(`Error: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const discoverPrinter = async () => {
    setBusy(true);
    try {
      const r = await api.discoverPrinter();
      log(r.message);
      await refresh();
    } catch (e) {
      log(`Error: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const loadFeatureTree = useCallback(async (jobId?: string | null) => {
    if (!hasEditableCode(code) && !jobId && !activeJobId) {
      setFeatureTree(null);
      return;
    }
    setFeatureTreeLoading(true);
    try {
      const data = await api.featureTree(jobId ?? activeJobId ?? undefined);
      setFeatureTree(data);
    } catch (e) {
      log(`Feature tree: ${(e as Error).message}`);
    } finally {
      setFeatureTreeLoading(false);
    }
  }, [activeJobId, code, log]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadFeatureTree();
    }, 400);
    return () => clearTimeout(timer);
  }, [code, activeJobId, loadFeatureTree]);

  const patchFeatureParam = useCallback(
    async (name: string, value: number | string, rerun = true) => {
      setBusy(true);
      try {
        const r = await api.patchFeatureParam(name, value, {
          jobId: activeJobId ?? undefined,
          rerun,
        });
        if (r.data?.code) setCode(r.data.code);
        if (r.data?.tree) setFeatureTree(r.data.tree);
        log(r.message);
        setModelReady(true);
        refreshStl(activeJobId);
        await refresh();
        await loadJobs();
      } catch (e) {
        log(`Error: ${(e as Error).message}`);
      } finally {
        setBusy(false);
      }
    },
    [activeJobId, loadJobs, log, refresh, refreshStl],
  );

  const patchFeatureConfig = useCallback(
    async (key: string, value: string) => {
      setBusy(true);
      try {
        const r = await api.patchFeatureConfig(key, value);
        if (r.data?.tree) setFeatureTree(r.data.tree);
        log(r.message);
        await refresh();
      } catch (e) {
        log(`Error: ${(e as Error).message}`);
      } finally {
        setBusy(false);
      }
    },
    [log, refresh],
  );

  const activeJob = jobs.find((j) => j.id === activeJobId) ?? null;

  const buildProgressPercent =
    loopProgress?.progress_percent ?? (busy ? 8 : 0);
  const sidebarProgress = busy
    ? Math.max(workflow?.progress_percent ?? 0, buildProgressPercent)
    : workflow?.progress_percent ?? 0;

  return {
    workflow,
    status,
    services,
    activeJobTitle: activeJob?.title ?? status?.active_job_title ?? null,
    activeJobDoc: activeJob?.freecad_doc ?? status?.active_job_doc ?? null,
    prompt,
    setPrompt,
    aiModels,
    conceptImage,
    contextGlobal,
    setContextGlobal,
    contextGlobalHint,
    contextViewSpecs,
    generatedContextImages,
    contextGenerating,
    generateContextPreviews,
    updateContextViewSpec,
    toggleContextView,
    setAiModel,
    attachConceptImage,
    clearConceptImage,
    code,
    setCode,
    modelReady,
    preview,
    previewError,
    stlUrl,
    loopProgress,
    featureTree,
    featureTreeLoading,
    loadFeatureTree,
    patchFeatureParam,
    patchFeatureConfig,
    logs,
    busy,
    buildPhase,
    buildProgressPercent,
    sidebarProgress,
    section,
    setSection,
    log,
    refresh,
    loadAiModels,
    runAction,
    discoverPrinter,
    jobs,
    activeJobId,
    createJob,
    selectJob,
    renameJob,
    deleteJob,
    loadJobs,
    actionLabel: (a: string) => ACTION_LABELS[a] ?? a,
  };
}