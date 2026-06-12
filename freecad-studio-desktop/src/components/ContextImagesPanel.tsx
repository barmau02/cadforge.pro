import { IconRefresh } from "./icons";
import type { ContextViewSpec, GeneratedContextImage } from "../hooks/useStudio";

export function ContextImagesPanel({
  grokReady,
  imageGenEnabled,
  globalContext,
  globalContextHint,
  viewSpecs,
  generated,
  busy,
  generating,
  onGlobalContextChange,
  onViewSpecChange,
  onToggleView,
  onGenerateAll,
  onRegenerateOne,
}: {
  grokReady: boolean;
  imageGenEnabled: boolean;
  globalContext: string;
  globalContextHint: string;
  viewSpecs: ContextViewSpec[];
  generated: GeneratedContextImage[];
  busy: boolean;
  generating: boolean;
  onGlobalContextChange: (value: string) => void;
  onViewSpecChange: (label: string, prompt: string) => void;
  onToggleView: (label: string, enabled: boolean) => void;
  onGenerateAll: () => void;
  onRegenerateOne: (label: string) => void;
}) {
  const generatedByLabel = new Map(generated.map((g) => [g.label, g]));
  const readyCount = generated.filter((g) => g.base64).length;

  if (!grokReady) {
    return (
      <div className="context-images-panel context-images-panel--disabled">
        <p className="context-images-note">
          Add a Grok API key in <strong>Settings</strong> to generate synthetic reference views before CAD build.
        </p>
      </div>
    );
  }

  return (
    <div className="context-images-panel">
      <div className="context-images-head">
        <div>
          <h4 className="context-images-title">Synthetic reference views</h4>
          <p className="context-images-sub">
            Grok Imagine guesses extra angles — often wrong. Fill in shared context, uncheck bad views,
            and try <strong>grok-imagine-image-quality</strong> in Settings for better results.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-compact"
          disabled={busy || generating || !imageGenEnabled}
          onClick={onGenerateAll}
        >
          <IconRefresh size={14} />
          {generating ? "Generating…" : readyCount ? "Regenerate all" : "Generate previews"}
        </button>
      </div>

      {!imageGenEnabled && (
        <p className="context-images-warning">Enable Grok image expansion in Settings to generate previews.</p>
      )}

      <label className="context-global-field">
        <span className="field-label">Shared context (applied to every view)</span>
        <textarea
          className="context-global-input"
          rows={2}
          value={globalContext}
          disabled={busy || generating}
          placeholder={globalContextHint}
          onChange={(e) => onGlobalContextChange(e.target.value)}
        />
      </label>

      <div className="context-view-grid">
        {viewSpecs.map((spec) => {
          const shot = generatedByLabel.get(spec.label);
          return (
            <article
              key={spec.label}
              className={`context-view-card ${spec.enabled ? "" : "context-view-card--off"} ${shot?.error ? "context-view-card--error" : ""}`}
            >
              <div className="context-view-card-head">
                <label className="context-view-enable">
                  <input
                    type="checkbox"
                    checked={spec.enabled}
                    disabled={busy || generating}
                    onChange={(e) => onToggleView(spec.label, e.target.checked)}
                  />
                  <span>{spec.title || spec.label}</span>
                </label>
                <button
                  type="button"
                  className="btn btn-ghost btn-compact"
                  disabled={busy || generating || !spec.enabled || !imageGenEnabled}
                  title={`Regenerate ${spec.title || spec.label}`}
                  onClick={() => onRegenerateOne(spec.label)}
                >
                  <IconRefresh size={13} />
                </button>
              </div>

              <div className="context-view-thumb">
                {shot?.preview ? (
                  <img src={shot.preview} alt={`Synthetic ${spec.title || spec.label}`} />
                ) : (
                  <div className="context-view-placeholder">
                    {shot?.error ? "Failed" : "No preview yet"}
                  </div>
                )}
              </div>

              <textarea
                className="context-view-prompt"
                rows={3}
                value={spec.prompt}
                disabled={busy || generating || !spec.enabled}
                onChange={(e) => onViewSpecChange(spec.label, e.target.value)}
              />
              {shot?.error && <p className="context-view-error">{shot.error}</p>}
            </article>
          );
        })}
      </div>

      {readyCount > 0 && (
        <p className="context-images-ready">
          {readyCount} synthetic view(s) ready — these will be sent with your CAD prompt on build.
        </p>
      )}
    </div>
  );
}
