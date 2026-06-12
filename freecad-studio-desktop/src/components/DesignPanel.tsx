import { useEffect, useRef, useState } from "react";
import { AiModelsResponse, LoopProgress, Status } from "../api";
import { ConceptImage } from "../hooks/useStudio";
import { ContextImagesPanel } from "./ContextImagesPanel";
import { IconImage, IconPlay, IconRefresh, IconX } from "./icons";
import { ModelViewer, PrintBed } from "./ModelViewer";
import { ParametersPanel } from "./ParametersPanel";
import { FeatureTreeResponse } from "../api";

const BUILD_EXAMPLES = [
  { label: "Boat", prompt: "A toy boat with hull, deck, small cabin, and rudder, 200mm long" },
  { label: "Phone stand", prompt: "A phone stand angled at 60 degrees, 80mm wide, stable base" },
  { label: "Gear", prompt: "A simple gear with 20 teeth, 40mm diameter, 8mm thick" },
  { label: "Wall hook", prompt: "A wall hook for coats, 60mm tall, with two screw holes" },
  { label: "Vase", prompt: "A hollow cube vase, 80mm tall, 5mm wall thickness" },
];

const EDIT_EXAMPLES = [
  { label: "Wider", prompt: "Make the main body 20mm wider" },
  { label: "Taller", prompt: "Increase the overall height by 15mm" },
  { label: "Add hole", prompt: "Add a 6mm diameter mounting hole near each corner" },
  { label: "Round edges", prompt: "Add a 3mm fillet on all top outer edges" },
  { label: "Hollow", prompt: "Make it hollow with 4mm wall thickness" },
];

export function DesignPanel({
  prompt,
  code,
  previewError,
  stlUrl,
  loopProgress,
  status,
  aiModels,
  conceptImage,
  busy,
  buildPhase,
  modelReady,
  activeJobTitle,
  activeJobDoc,
  onPromptChange,
  onCodeChange,
  onModelChange,
  onImageAttach,
  onImageClear,
  onBuild,
  onShowFreecad,
  onRunCode,
  onRefreshPreview,
  featureTree,
  featureTreeLoading,
  onRefreshFeatureTree,
  onPatchFeatureParam,
  contextGlobal,
  onContextGlobalChange,
  contextGlobalHint,
  contextViewSpecs,
  generatedContextImages,
  contextGenerating,
  onGenerateContextPreviews,
  onContextViewSpecChange,
  onToggleContextView,
}: {
  prompt: string;
  code: string;
  previewError: string | null;
  stlUrl: string | null;
  loopProgress: LoopProgress | null;
  status: Status | null;
  aiModels: AiModelsResponse | null;
  conceptImage: ConceptImage | null;
  busy: boolean;
  buildPhase: string | null;
  modelReady: boolean;
  activeJobTitle: string | null;
  activeJobDoc: string | null;
  onPromptChange: (v: string) => void;
  onCodeChange: (v: string) => void;
  onModelChange: (model: string) => void;
  onImageAttach: (file: File) => void;
  onImageClear: () => void;
  onBuild: () => void;
  onShowFreecad: () => void;
  onRunCode: () => void;
  onRefreshPreview: () => void;
  featureTree: FeatureTreeResponse | null;
  featureTreeLoading: boolean;
  onRefreshFeatureTree: () => void;
  onPatchFeatureParam: (name: string, value: number | string, rerun?: boolean) => Promise<void>;
  contextGlobal: string;
  onContextGlobalChange: (value: string) => void;
  contextGlobalHint: string;
  contextViewSpecs: import("../hooks/useStudio").ContextViewSpec[];
  generatedContextImages: import("../hooks/useStudio").GeneratedContextImage[];
  contextGenerating: boolean;
  onGenerateContextPreviews: (onlyLabel?: string) => void;
  onContextViewSpecChange: (label: string, prompt: string) => void;
  onToggleContextView: (label: string, enabled: boolean) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLTextAreaElement>(null);
  const [paramsCollapsed, setParamsCollapsed] = useState(false);

  useEffect(() => {
    if (!busy || !code.trim() || code.trim() === "# Python appears here after you prompt") return;
    codeRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [busy, code]);
  const visionModels = aiModels?.models.filter((m) => m.vision) ?? [];
  const textModels = aiModels?.models.filter((m) => !m.vision) ?? [];
  const currentModel = aiModels?.current ?? status?.ai_model ?? "";
  const needsVision = Boolean(conceptImage) && !status?.ai_vision;
  const isEditMode = modelReady;
  const examples = isEditMode ? EDIT_EXAMPLES : BUILD_EXAMPLES;
  const showBuildProgress = busy || (loopProgress != null && loopProgress.state === "running");
  const progressPct = loopProgress?.progress_percent ?? (busy ? 8 : 0);
  const progressPhase =
    loopProgress?.phase ?? buildPhase ?? (isEditMode ? "Applying changes…" : "Building model…");
  const codeReady =
    Boolean(code.trim()) && code.trim() !== "# Python appears here after you prompt";
  const codeStatus = busy && !codeReady ? "generating" : codeReady ? "ready" : "idle";
  const showAiInspection =
    Boolean(loopProgress && loopProgress.state !== "idle")
    || Boolean(loopProgress?.reasoning)
    || Boolean(loopProgress?.feature_audit?.length)
    || Boolean(loopProgress?.issues?.length)
    || Boolean(loopProgress?.thinking_log?.length);

  const printBed: PrintBed | null =
    status?.bed_width_mm && status?.bed_depth_mm && status?.bed_height_mm
      ? {
          widthMm: status.bed_width_mm,
          depthMm: status.bed_depth_mm,
          heightMm: status.bed_height_mm,
          label: status.printer_label,
        }
      : null;

  return (
    <div className="design-layout">
      <section className="panel design-prompt-panel">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">AI Design</h2>
            <p className="panel-subtitle">
              {activeJobTitle
                ? `${activeJobTitle}${activeJobDoc ? ` · ${activeJobDoc}` : ""}`
                : "No active job — create one before building"}
              {" · "}
              {isEditMode
                ? "describe changes in plain English"
                : status?.ai_configured
                  ? `new model via ${status.ai_label}`
                  : "configure Ollama in config.toml"}
            </p>
          </div>
          <span className={`ai-status ${status?.ai_configured ? "ready" : "off"}`}>
            {activeJobTitle
              ? isEditMode
                ? "Editing job"
                : "New build"
              : status?.ai_configured
                ? "AI ready"
                : "Manual mode"}
          </span>
        </div>

        <div className="ai-model-row">
          <label className="field-label" htmlFor="ai-model-select">
            AI model
          </label>
          <select
            id="ai-model-select"
            className="model-select"
            value={currentModel}
            disabled={busy || !aiModels?.models.length}
            onChange={(e) => onModelChange(e.target.value)}
          >
            {!aiModels?.models.length && <option value={currentModel}>{currentModel || "Loading…"}</option>}
            {visionModels.length > 0 && (
              <optgroup label="Vision — concept images & 3D view">
                {visionModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} — {m.hint}
                  </option>
                ))}
              </optgroup>
            )}
            {textModels.length > 0 && (
              <optgroup label="Text — prompts only (stronger coding)">
                {textModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} — {m.hint}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </div>

        <div className="concept-upload-row">
          <label className="field-label">3D concept image (optional)</label>
          <div className="concept-upload-zone">
            {conceptImage ? (
              <div className="concept-preview">
                <img src={conceptImage.preview} alt="3D concept reference" />
                <div className="concept-meta">
                  <span>{conceptImage.name}</span>
                  <button type="button" className="btn btn-ghost btn-compact" onClick={onImageClear}>
                    <IconX size={14} />
                    Remove
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className="concept-drop"
                disabled={busy}
                onClick={() => fileRef.current?.click()}
              >
                <IconImage size={22} />
                <span>Upload sketch, render, or photo</span>
                <span className="concept-drop-hint">PNG, JPG, WebP · max 8 MB · needs a vision model</span>
              </button>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onImageAttach(file);
                e.target.value = "";
              }}
            />
          </div>
          {needsVision && (
            <p className="concept-warning">
              Image attached — switch to a vision model (top group) to build from it.
            </p>
          )}
        </div>

        {conceptImage && status?.image_gen_enabled === true && (
          <ContextImagesPanel
            grokReady={Boolean(status?.grok_configured)}
            imageGenEnabled
            globalContext={contextGlobal}
            globalContextHint={contextGlobalHint}
            viewSpecs={contextViewSpecs}
            generated={generatedContextImages}
            busy={busy}
            generating={contextGenerating}
            onGlobalContextChange={onContextGlobalChange}
            onViewSpecChange={onContextViewSpecChange}
            onToggleView={onToggleContextView}
            onGenerateAll={() => onGenerateContextPreviews()}
            onRegenerateOne={(label) => onGenerateContextPreviews(label)}
          />
        )}

        <label className="field-label" htmlFor="prompt-input">
          {isEditMode ? "Describe changes to the 3D model" : "Describe your model"}
        </label>
        <textarea
          id="prompt-input"
          className="prompt-field"
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          placeholder={
            isEditMode
              ? "e.g. Make it 20mm wider, add a chamfer on top, move the holes closer together…"
              : conceptImage
                ? "e.g. Recreate this bracket at 80mm wide, 5mm thick, with two M4 holes…"
                : "A bracket with two mounting holes, 60mm wide, 3mm thick…"
          }
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              onBuild();
            }
          }}
        />

        <div className="example-row">
          {examples.map((ex) => (
            <button key={ex.label} type="button" className="example-chip" onClick={() => onPromptChange(ex.prompt)}>
              {ex.label}
            </button>
          ))}
        </div>

        <div className="build-actions">
          <button type="button" className="btn btn-primary btn-wide" disabled={busy || needsVision} onClick={onBuild}>
            <IconPlay size={16} />
            {busy
              ? buildPhase ?? (isEditMode ? "Applying changes…" : "Building in FreeCAD…")
              : isEditMode
                ? "Apply changes"
                : conceptImage
                  ? "Build from image"
                  : "Build in FreeCAD"}
          </button>
          <button type="button" className="btn btn-secondary btn-wide" disabled={busy} onClick={onShowFreecad}>
            Show FreeCAD
          </button>
        </div>

        {showBuildProgress && (
          <div
            className={`build-progress ${loopProgress?.state === "error" ? "build-progress--error" : ""}`}
            role="status"
            aria-live="polite"
          >
            <div className="build-progress-head">
              <span className="build-progress-label">
                {loopProgress?.state === "running" || busy ? "Building model" : "Build status"}
                {loopProgress?.iteration
                  ? ` · iteration ${loopProgress.iteration}/${loopProgress.max_iterations ?? 6}`
                  : ""}
              </span>
              <span className="build-progress-pct">{progressPct}%</span>
            </div>
            <div className="build-progress-bar">
              <div className="build-progress-fill" style={{ width: `${progressPct}%` }} />
            </div>
            <p className="build-progress-phase">{progressPhase}</p>
          </div>
        )}
        {busy ? (
          <p className="build-progress-hint">
            {isEditMode
              ? "Updating from your prompt — Python and preview refresh automatically."
              : "Building — watch the progress bar; Python fills in as the AI generates it."}
          </p>
        ) : (
          <p className="build-progress-hint">
            {isEditMode
              ? "Describe a change — prior prompts and Python are sent to the AI as context."
              : "New job → describe part → Build. Headless batch export lives in forgeprompt/batch/."}
          </p>
        )}
      </section>

      <div className="workspace-code-row">
        <ParametersPanel
          tree={featureTree}
          loading={featureTreeLoading}
          busy={busy}
          collapsed={paramsCollapsed}
          onToggleCollapsed={() => setParamsCollapsed((v) => !v)}
          onRefresh={onRefreshFeatureTree}
          onPatchParameter={(name, value, rerun = true) => onPatchFeatureParam(name, value, rerun)}
        />

        <section className={`panel code-panel code-panel--${codeStatus}`}>
          <div className="panel-header compact">
            <div className="code-panel-title">
              <h3 className="panel-title-sm">Generated Python</h3>
              <span className={`code-status code-status--${codeStatus}`}>
                {codeStatus === "generating" ? "Generating…" : codeStatus === "ready" ? "Ready" : "Waiting"}
              </span>
            </div>
            <button type="button" className="btn btn-primary btn-compact" disabled={busy || !codeReady} onClick={onRunCode}>
              <IconPlay size={14} />
              Rerun in FreeCAD
            </button>
          </div>
          <textarea
            ref={codeRef}
            className="code-editor"
            value={code}
            onChange={(e) => onCodeChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                onRunCode();
              }
            }}
            spellCheck={false}
            aria-label="Python code editor"
            placeholder="# Python appears here after you build…"
          />
        </section>

        {showAiInspection && loopProgress ? (
          <AiInspectionPanel loopProgress={loopProgress} />
        ) : (
          <section className="panel ai-inspection-panel ai-inspection-panel--idle" aria-label="AI reasoning and corrections">
            <div className="panel-header compact ai-inspection-header">
              <h3 className="panel-title-sm">AI reasoning &amp; corrections</h3>
            </div>
            <div className="ai-inspection-body ai-inspection-idle">
              <p>
                {busy
                  ? "Vision loop reasoning and feature checks will appear here during the build."
                  : "Run a vision-model build to see reasoning, issues, and suggested fixes here."}
              </p>
            </div>
          </section>
        )}
      </div>

      <section className="panel preview-panel preview-panel--hero">
        <div className="panel-header compact">
          <h3 className="panel-title-sm">
            3D Preview — drag to orbit, scroll to zoom
            {printBed ? (
              <span className="preview-bed-meta">
                {" · "}
                {printBed.label ?? "Printer"} bed {Math.round(printBed.widthMm)}×{Math.round(printBed.depthMm)}×
                {Math.round(printBed.heightMm)} mm
              </span>
            ) : null}
          </h3>
          <button type="button" className="btn btn-ghost btn-compact" disabled={busy} onClick={onRefreshPreview}>
            <IconRefresh size={14} />
            Refresh mesh
          </button>
        </div>
        <div className="preview-viewport preview-viewport--3d">
          <ModelViewer stlUrl={stlUrl} fallbackImage={null} printBed={printBed} />
        </div>
      </section>
    </div>
  );
}

function AiInspectionPanel({ loopProgress }: { loopProgress: LoopProgress }) {
  const missing = loopProgress.feature_audit?.filter((a) => a.status !== "ok") ?? [];
  const corrections = missing.filter((a) => a.fix);

  return (
    <section
      className={`panel ai-inspection-panel loop-progress loop-progress--${loopProgress.state ?? "running"}`}
      aria-label="AI reasoning and corrections"
    >
      <div className="panel-header compact ai-inspection-header">
        <div>
          <h3 className="panel-title-sm">AI reasoning &amp; corrections</h3>
          <span className="loop-progress-badge">
            Vision loop
            {loopProgress.state === "running"
              ? ` · ${loopProgress.iteration ?? 0}/${loopProgress.max_iterations ?? 6}`
              : ` · ${loopProgress.state ?? "running"}`}
            {loopProgress.score != null ? ` · score ${loopProgress.score}/100` : ""}
            {loopProgress.reference_score != null ? ` · ref ${loopProgress.reference_score}/100` : ""}
          </span>
        </div>
      </div>

      {loopProgress.phase && (
        <p className="loop-progress-phase ai-inspection-phase">{loopProgress.phase}</p>
      )}

      <div className="ai-inspection-body">
        {loopProgress.reasoning && (
          <div className="loop-reasoning-box">
            <span className="loop-reasoning-label">Reasoning</span>
            <p>{loopProgress.reasoning}</p>
          </div>
        )}

        {(loopProgress.required_features?.length ?? 0) > 0 && (
          <p className="loop-progress-plan">
            Target features: {loopProgress.required_features!.join(", ")}
          </p>
        )}

        {(loopProgress.issues?.length ?? 0) > 0 && (
          <ul className="loop-progress-issues ai-inspection-issues">
            {loopProgress.issues!.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        )}

        {(loopProgress.feature_audit?.length ?? 0) > 0 && (
          <div className="ai-inspection-audit">
            <span className="loop-reasoning-label">
              Feature check{corrections.length ? ` · ${corrections.length} fix(es) suggested` : ""}
            </span>
            <ul className="loop-progress-audit">
              {loopProgress.feature_audit!.map((a) => (
                <li key={a.feature} data-status={a.status}>
                  <strong>{a.feature}</strong>
                  <span className={`audit-status audit-status--${a.status}`}>{a.status}</span>
                  {a.status !== "ok" && (
                    <span className="audit-detail">
                      expected {a.expected}; saw {a.observed}
                      {a.fix ? ` — fix: ${a.fix}` : ""}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {(loopProgress.thinking_log?.length ?? 0) > 0 && (
          <details className="loop-thinking-log" open={loopProgress.state === "running"}>
            <summary>Step log ({loopProgress.thinking_log!.length})</summary>
            <ol>
              {loopProgress.thinking_log!.map((line, i) => (
                <li key={`${i}-${line.slice(0, 24)}`}>{line}</li>
              ))}
            </ol>
          </details>
        )}
      </div>
    </section>
  );
}

function IconBoxPlaceholder() {
  return (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
      <path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5M2 12l10 5 10-5" />
    </svg>
  );
}