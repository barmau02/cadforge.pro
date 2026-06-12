import { useState } from "react";
import { JobSummary } from "../api";
import { IconBox, IconPencil, IconPlus, IconTrash } from "./icons";

export function JobPanel({
  jobs,
  activeJobId,
  busy,
  onCreate,
  onSelect,
  onRename,
  onDelete,
}: {
  jobs: JobSummary[];
  activeJobId: string | null;
  busy: boolean;
  onCreate: () => void;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const startRename = (job: JobSummary) => {
    setEditingId(job.id);
    setEditTitle(job.title);
  };

  const commitRename = (jobId: string) => {
    const title = editTitle.trim();
    if (title) onRename(jobId, title);
    setEditingId(null);
    setEditTitle("");
  };

  return (
    <section className="panel job-panel">
      <div className="panel-header compact">
        <div>
          <h2 className="panel-title-sm">Jobs</h2>
          <p className="panel-subtitle">One FreeCAD document per part</p>
        </div>
        <button type="button" className="btn btn-secondary btn-compact" disabled={busy} onClick={onCreate}>
          <IconPlus size={14} />
          New job
        </button>
      </div>

      <div className="job-list">
        {jobs.length === 0 ? (
          <p className="job-empty">No jobs yet — create one before building a new part.</p>
        ) : (
          jobs.map((job) => (
            <div
              key={job.id}
              className={`job-card-wrap ${job.id === activeJobId ? "active" : ""}`}
            >
              {editingId === job.id ? (
                <div className="job-rename-row">
                  <input
                    className="job-rename-input"
                    value={editTitle}
                    autoFocus
                    disabled={busy}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitRename(job.id);
                      if (e.key === "Escape") setEditingId(null);
                    }}
                  />
                  <button
                    type="button"
                    className="btn btn-primary btn-compact"
                    disabled={busy}
                    onClick={() => commitRename(job.id)}
                  >
                    Save
                  </button>
                </div>
              ) : (
                <>
                  <button
                    type="button"
                    className={`job-card ${job.id === activeJobId ? "active" : ""}`}
                    disabled={busy}
                    onClick={() => onSelect(job.id)}
                  >
                    <span className="job-card-icon">
                      <IconBox size={14} />
                    </span>
                    <span className="job-card-body">
                      <span className="job-card-title">{job.title}</span>
                      <span className="job-card-meta">
                        {job.freecad_doc}
                        <span className={`job-status job-status--${job.status}`}>{job.status}</span>
                      </span>
                    </span>
                  </button>
                  <div className="job-card-actions">
                    <button
                      type="button"
                      className="btn btn-ghost btn-compact job-action-btn"
                      disabled={busy}
                      title="Rename job"
                      onClick={() => startRename(job)}
                    >
                      <IconPencil size={13} />
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-compact job-action-btn"
                      disabled={busy}
                      title="Delete job"
                      onClick={() => {
                        if (window.confirm(`Delete job "${job.title}"?`)) onDelete(job.id);
                      }}
                    >
                      <IconTrash size={13} />
                    </button>
                  </div>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </section>
  );
}