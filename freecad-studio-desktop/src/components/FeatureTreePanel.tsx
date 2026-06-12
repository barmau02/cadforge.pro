import { useCallback, useEffect, useState } from "react";
import { FeatureTreeNode, FeatureTreeResponse } from "../api";
import { IconRefresh } from "./icons";

function TreeNodeRow({
  node,
  depth,
  editingId,
  draft,
  busy,
  onStartEdit,
  onDraftChange,
  onCommit,
  onCancel,
}: {
  node: FeatureTreeNode;
  depth: number;
  editingId: string | null;
  draft: string;
  busy: boolean;
  onStartEdit: (node: FeatureTreeNode) => void;
  onDraftChange: (value: string) => void;
  onCommit: (node: FeatureTreeNode) => void;
  onCancel: () => void;
}) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = Boolean(node.children?.length);
  const isEditing = editingId === node.id;
  const showValue = node.value !== undefined && node.value !== null && node.kind !== "group";

  return (
    <li className={`feature-tree-node feature-tree-node--${node.kind}`}>
      <div className="feature-tree-row" style={{ paddingLeft: `${8 + depth * 14}px` }}>
        {hasChildren ? (
          <button
            type="button"
            className="feature-tree-toggle"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="feature-tree-toggle feature-tree-toggle--spacer" />
        )}
        <span className="feature-tree-label" title={node.label ?? node.name}>
          {node.label ?? node.name}
        </span>
        {node.editable && node.kind === "parameter" && !isEditing && (
          <button
            type="button"
            className="feature-tree-edit"
            disabled={busy}
            onClick={() => onStartEdit(node)}
          >
            Edit
          </button>
        )}
        {node.editable && node.kind === "slicer_meta" && node.source === "config.toml" && !isEditing && (
          <button
            type="button"
            className="feature-tree-edit"
            disabled={busy}
            onClick={() => onStartEdit(node)}
          >
            Edit
          </button>
        )}
        {isEditing ? (
          <span className="feature-tree-inline-edit">
            <input
              className="feature-tree-input"
              value={draft}
              autoFocus
              disabled={busy}
              onChange={(e) => onDraftChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onCommit(node);
                if (e.key === "Escape") onCancel();
              }}
            />
            <button type="button" className="btn btn-primary btn-compact" disabled={busy} onClick={() => onCommit(node)}>
              Apply
            </button>
          </span>
        ) : (
          showValue && <span className="feature-tree-value">{String(node.value)}</span>
        )}
        {node.line != null && node.kind === "parameter" && (
          <span className="feature-tree-line">L{node.line}</span>
        )}
      </div>
      {hasChildren && open && (
        <ul className="feature-tree-children">
          {node.children!.map((child) => (
            <TreeNodeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              editingId={editingId}
              draft={draft}
              busy={busy}
              onStartEdit={onStartEdit}
              onDraftChange={onDraftChange}
              onCommit={onCommit}
              onCancel={onCancel}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function FeatureTreePanel({
  tree,
  loading,
  busy,
  onRefresh,
  onPatchParameter,
  onPatchConfig,
}: {
  tree: FeatureTreeResponse | null;
  loading: boolean;
  busy: boolean;
  onRefresh: () => void;
  onPatchParameter: (name: string, value: number | string, rerun: boolean) => Promise<void>;
  onPatchConfig: (key: string, value: string) => Promise<void>;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setEditingId(null);
    setDraft("");
  }, [tree?.parameter_count, tree?.operation_count]);

  const startEdit = useCallback((node: FeatureTreeNode) => {
    setEditingId(node.id);
    setDraft(node.value != null ? String(node.value) : "");
  }, []);

  const commit = useCallback(
    async (node: FeatureTreeNode) => {
      const trimmed = draft.trim();
      if (!trimmed) return;
      if (node.kind === "parameter") {
        const num = Number(trimmed);
        const value = Number.isFinite(num) && /^-?\d/.test(trimmed) ? num : trimmed;
        await onPatchParameter(node.name, value, true);
      } else if (node.kind === "slicer_meta" && node.source === "config.toml") {
        await onPatchConfig(node.name, trimmed);
      }
      setEditingId(null);
      setDraft("");
    },
    [draft, onPatchConfig, onPatchParameter],
  );

  return (
    <section className="panel feature-tree-panel" aria-label="Feature tree">
      <div className="panel-header compact feature-tree-header">
        <div>
          <h3 className="panel-title-sm">Feature tree</h3>
          <p className="feature-tree-subtitle">
            {tree
              ? `${tree.parameter_count} params · ${tree.operation_count} ops`
              : "Parameters, build steps, slicer metadata"}
          </p>
        </div>
        <button type="button" className="btn btn-ghost btn-compact" disabled={busy || loading} onClick={onRefresh}>
          <IconRefresh size={14} />
          Refresh
        </button>
      </div>

      <div className="feature-tree-body">
        {loading && <p className="feature-tree-empty">Loading feature tree…</p>}
        {!loading && !tree?.tree.length && (
          <p className="feature-tree-empty">Build a model to populate the feature tree.</p>
        )}
        {!loading && tree?.tree.length ? (
          <ul className="feature-tree-root">
            {tree.tree.map((node) => (
              <TreeNodeRow
                key={node.id}
                node={node}
                depth={0}
                editingId={editingId}
                draft={draft}
                busy={busy}
                onStartEdit={startEdit}
                onDraftChange={setDraft}
                onCommit={commit}
                onCancel={() => {
                  setEditingId(null);
                  setDraft("");
                }}
              />
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
