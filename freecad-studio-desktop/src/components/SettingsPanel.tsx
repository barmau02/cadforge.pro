import { useCallback, useEffect, useState } from "react";
import { api, AppSettings } from "../api";
import type { Status } from "../api";

export function SettingsPanel({
  status,
  onSaved,
}: {
  status: Status | null;
  onSaved?: () => void;
}) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [ollamaKey, setOllamaKey] = useState("");
  const [grokKey, setGrokKey] = useState("");
  const [grokModel, setGrokModel] = useState("grok-imagine-image");
  const [imageGenEnabled, setImageGenEnabled] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await api.settings();
      setSettings(s);
      setGrokModel(s.grok_image_model || "grok-imagine-image");
      setImageGenEnabled(s.image_gen_enabled);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const patch: Record<string, unknown> = {
        grok_image_model: grokModel,
        image_gen_enabled: imageGenEnabled,
      };
      if (ollamaKey.trim()) patch.ollama_api_key = ollamaKey.trim();
      if (grokKey.trim()) patch.grok_api_key = grokKey.trim();
      const res = await api.updateSettings(patch);
      setMessage(res.message || "Settings saved");
      setOllamaKey("");
      setGrokKey("");
      if (res.data?.settings) setSettings(res.data.settings);
      await load();
      onSaved?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const clearGrok = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.updateSettings({ grok_api_key: "" });
      setGrokKey("");
      await load();
      onSaved?.();
      setMessage("Grok API key cleared");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Clear failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading && !settings) {
    return (
      <section className="panel settings-panel">
        <p className="muted">Loading settings…</p>
      </section>
    );
  }

  return (
    <section className="panel settings-panel">
      <header className="panel-header">
        <div>
          <h2>Settings</h2>
          <p className="panel-sub">
            API keys for Ollama Cloud (vision + code). Grok Imagine is optional — off by default.
          </p>
        </div>
      </header>

      {error && <p className="settings-error">{error}</p>}
      {message && <p className="settings-ok">{message}</p>}

      <div className="settings-grid">
        <div className="settings-card">
          <h3>Ollama Cloud</h3>
          <p className="muted">
            Used for feature planning, FreeCAD code generation, and visual critique.{" "}
            <a href={settings?.ollama_key_url || "https://ollama.com/settings/keys"} target="_blank" rel="noreferrer">
              Get API key
            </a>
          </p>
          <p className="settings-status">
            Status:{" "}
            <strong>{settings?.ollama_api_key_set || status?.ai_configured ? "Configured" : "Not set"}</strong>
            {settings?.ollama_api_key_masked ? ` (${settings.ollama_api_key_masked})` : ""}
          </p>
          <label className="settings-label">
            Ollama API key
            <input
              type="password"
              placeholder={settings?.ollama_api_key_set ? "Leave blank to keep current key" : "Paste Ollama API key"}
              value={ollamaKey}
              onChange={(e) => setOllamaKey(e.target.value)}
              autoComplete="off"
            />
          </label>
          <p className="muted small">Model in use: {status?.ai_model || settings?.model || "—"}</p>
        </div>

        <div className="settings-card">
          <h3>Grok Imagine (optional)</h3>
          <label className="settings-check settings-check--primary">
            <input
              type="checkbox"
              checked={imageGenEnabled}
              onChange={(e) => setImageGenEnabled(e.target.checked)}
            />
            Enable synthetic reference views
          </label>
          <p className="muted">
            Off by default. When enabled, Grok generates extra angles from your concept photo before
            build (experimental — often inconsistent). Requires an xAI API key.
          </p>
          {imageGenEnabled && (
            <>
              <p className="muted">
                ~$0.02–0.05 per image.{" "}
                <a href={settings?.grok_key_url || "https://console.x.ai/"} target="_blank" rel="noreferrer">
                  Get API key
                </a>
              </p>
              <p className="settings-status">
                Status:{" "}
                <strong>{settings?.grok_api_key_set || status?.grok_configured ? "Configured" : "Not set"}</strong>
                {settings?.grok_api_key_masked ? ` (${settings.grok_api_key_masked})` : ""}
              </p>
              <label className="settings-label">
                Grok API key
                <input
                  type="password"
                  placeholder={settings?.grok_api_key_set ? "Leave blank to keep current key" : "Paste xAI API key"}
                  value={grokKey}
                  onChange={(e) => setGrokKey(e.target.value)}
                  autoComplete="off"
                />
              </label>
              <label className="settings-label">
                Image model
                <select value={grokModel} onChange={(e) => setGrokModel(e.target.value)}>
                  <option value="grok-imagine-image">grok-imagine-image ($0.02/image)</option>
                  <option value="grok-imagine-image-quality">grok-imagine-image-quality ($0.05/image)</option>
                </select>
              </label>
              {settings?.grok_api_key_set && (
                <button type="button" className="btn ghost" onClick={() => void clearGrok()} disabled={saving}>
                  Clear Grok key
                </button>
              )}
            </>
          )}
        </div>
      </div>

      <div className="settings-actions">
        <button type="button" className="btn primary" onClick={() => void save()} disabled={saving}>
          {saving ? "Saving…" : "Save settings"}
        </button>
      </div>
    </section>
  );
}
