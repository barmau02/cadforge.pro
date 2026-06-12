import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FeatureTreeNode, FeatureTreeResponse } from "../api";
import { IconRefresh } from "./icons";

type ParamState = {
  name: string;
  value: number;
  min: number;
  max: number;
  step: number;
  line?: number;
};

function inferRange(value: number): { min: number; max: number; step: number } {
  const abs = Math.abs(value) || 1;
  const step =
    abs >= 100 ? 1 : abs >= 10 ? 0.5 : abs >= 1 ? 0.1 : abs >= 0.1 ? 0.01 : 0.001;
  const min = value >= 0 ? 0 : -abs * 4;
  const max = Math.max(abs * 4, min + step * 10);
  return { min, max, step };
}

function ParamRow({
  param,
  suppressed,
  busy,
  onValueCommit,
  onToggleSuppress,
}: {
  param: ParamState;
  suppressed: boolean;
  busy: boolean;
  onValueCommit: (name: string, value: number) => void;
  onToggleSuppress: (name: string, suppressed: boolean, current: number) => void;
}) {
  const [local, setLocal] = useState(param.value);
  const dragging = useRef(false);

  useEffect(() => {
    if (!dragging.current) setLocal(param.value);
  }, [param.value]);

  const commit = useCallback(
    (next: number) => {
      const clamped = Math.min(param.max, Math.max(param.min, next));
      setLocal(clamped);
      if (!suppressed) onValueCommit(param.name, clamped);
    },
    [onValueCommit, param.max, param.min, param.name, suppressed],
  );

  return (
    <div className={`param-row ${suppressed ? "param-row--suppressed" : ""}`}>
      <button
        type="button"
        className={`param-eye ${suppressed ? "param-eye--off" : ""}`}
        title={suppressed ? "Unsuppress parameter" : "Suppress parameter"}
        disabled={busy}
        onClick={() => onToggleSuppress(param.name, !suppressed, local)}
        aria-pressed={suppressed}
      >
        {suppressed ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
            <line x1="1" y1="1" x2="23" y2="23" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
      </button>

      <div className="param-meta">
        <span className="param-name">{param.name}</span>
        <span className="param-unit">mm</span>
      </div>

      <div className="param-controls">
        <div className="param-stepper">
          <button
            type="button"
            className="param-step"
            disabled={busy || suppressed}
            onClick={() => commit(local - param.step)}
            aria-label={`Decrease ${param.name}`}
          >
            −
          </button>
          <input
            type="number"
            className="param-number"
            value={Number(local.toFixed(4)).toString()}
            disabled={busy || suppressed}
            min={param.min}
            max={param.max}
            step={param.step}
            onChange={(e) => setLocal(Number(e.target.value))}
            onBlur={(e) => commit(Number(e.target.value))}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit(Number((e.target as HTMLInputElement).value));
            }}
          />
          <button
            type="button"
            className="param-step"
            disabled={busy || suppressed}
            onClick={() => commit(local + param.step)}
            aria-label={`Increase ${param.name}`}
          >
            +
          </button>
        </div>
        <input
          type="range"
          className="param-slider"
          disabled={busy || suppressed}
          min={param.min}
          max={param.max}
          step={param.step}
          value={local}
          onChange={(e) => {
            dragging.current = true;
            setLocal(Number(e.target.value));
          }}
          onMouseUp={(e) => {
            dragging.current = false;
            commit(Number((e.target as HTMLInputElement).value));
          }}
          onTouchEnd={(e) => {
            dragging.current = false;
            commit(Number((e.target as HTMLInputElement).value));
          }}
        />
      </div>
    </div>
  );
}

function FeatureOpRow({ node, depth }: { node: FeatureTreeNode; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = Boolean(node.children?.length);

  return (
    <li className="param-feature-node">
      <div className="param-feature-row" style={{ paddingLeft: `${depth * 12}px` }}>
        {hasChildren ? (
          <button type="button" className="param-feature-toggle" onClick={() => setOpen((v) => !v)}>
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="param-feature-dot" />
        )}
        <span className="param-feature-label">{node.label ?? node.name}</span>
      </div>
      {hasChildren && open && (
        <ul className="param-feature-children">
          {node.children!.map((child) => (
            <FeatureOpRow key={child.id} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ParametersPanel({
  tree,
  loading,
  busy,
  collapsed,
  onToggleCollapsed,
  onRefresh,
  onPatchParameter,
}: {
  tree: FeatureTreeResponse | null;
  loading: boolean;
  busy: boolean;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onRefresh: () => void;
  onPatchParameter: (name: string, value: number | string, rerun: boolean) => Promise<void>;
}) {
  const [suppressed, setSuppressed] = useState<Set<string>>(() => new Set());
  const [savedValues, setSavedValues] = useState<Record<string, number>>({});
  const [showFeatures, setShowFeatures] = useState(false);

  const params = useMemo((): ParamState[] => {
    const raw = tree?.parameters ?? [];
    return raw
      .filter((p) => p.editable && typeof p.value === "number")
      .map((p) => {
        const value = Number(p.value);
        const range = inferRange(value);
        return { name: p.name, value, line: p.line, ...range };
      });
  }, [tree?.parameters]);

  useEffect(() => {
    setSuppressed(new Set());
    setSavedValues({});
  }, [tree?.parameter_count, tree?.doc_name]);

  const operations = useMemo(() => {
    const group = tree?.tree.find((n) => n.id === "group:operations");
    return group?.children ?? [];
  }, [tree?.tree]);

  const handleCommit = useCallback(
    async (name: string, value: number) => {
      await onPatchParameter(name, value, true);
    },
    [onPatchParameter],
  );

  const handleSuppress = useCallback(
    async (name: string, next: boolean, current: number) => {
      if (next) {
        setSavedValues((prev) => ({ ...prev, [name]: current }));
        setSuppressed((prev) => new Set(prev).add(name));
        await onPatchParameter(name, 0.001, true);
      } else {
        setSuppressed((prev) => {
          const s = new Set(prev);
          s.delete(name);
          return s;
        });
        const restore = savedValues[name] ?? current;
        await onPatchParameter(name, restore, true);
      }
    },
    [onPatchParameter, savedValues],
  );

  return (
    <section
      className={`panel params-panel ${collapsed ? "params-panel--collapsed" : ""}`}
      aria-label="Model parameters"
    >
      <div className="params-panel-head">
        <button
          type="button"
          className="params-panel-collapse"
          onClick={onToggleCollapsed}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand parameters" : "Collapse parameters"}
        >
          {collapsed ? "▸" : "▾"}
        </button>
        {!collapsed && (
          <>
            <div className="params-panel-title-wrap">
              <h3 className="panel-title-sm">Parameters</h3>
              <span className="params-panel-count">{params.length}</span>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-compact"
              disabled={busy || loading}
              onClick={onRefresh}
              title="Refresh from Python"
            >
              <IconRefresh size={14} />
            </button>
          </>
        )}
        {collapsed && <span className="params-panel-collapsed-label">Params</span>}
      </div>

      {!collapsed && (
        <div className="params-panel-body">
          {loading && <p className="params-empty">Loading parameters…</p>}
          {!loading && params.length === 0 && (
            <p className="params-empty">Build a model — editable dimensions appear here.</p>
          )}
          <div className="params-list">
            {params.map((p) => (
              <ParamRow
                key={p.name}
                param={p}
                suppressed={suppressed.has(p.name)}
                busy={busy}
                onValueCommit={handleCommit}
                onToggleSuppress={handleSuppress}
              />
            ))}
          </div>

          {operations.length > 0 && (
            <div className="params-features-section">
              <button
                type="button"
                className="params-features-toggle"
                onClick={() => setShowFeatures((v) => !v)}
              >
                {showFeatures ? "▾" : "▸"} Build history
                <span className="params-panel-count">{tree?.operation_count ?? 0}</span>
              </button>
              {showFeatures && (
                <ul className="param-feature-list">
                  {operations.map((node) => (
                    <FeatureOpRow key={node.id} node={node} depth={0} />
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
