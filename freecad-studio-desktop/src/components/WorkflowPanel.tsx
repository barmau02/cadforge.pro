import { Workflow } from "../api";
import { IconCheck } from "./icons";

export function WorkflowPanel({
  workflow,
  busy,
  actionLabel,
  onAction,
}: {
  workflow: Workflow | null;
  busy: boolean;
  actionLabel: (a: string) => string;
  onAction: (a: string) => void;
}) {
  if (!workflow) {
    return <div className="panel-empty">Loading workflow…</div>;
  }

  return (
    <section className="panel workflow-panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Pipeline</h2>
          <p className="panel-subtitle">
            {workflow.done_count} of {workflow.total_count} steps complete
          </p>
        </div>
        <div className="progress-ring-wrap">
          <span className="progress-value">{workflow.progress_percent}%</span>
        </div>
      </div>

      <div className="current-step">
        <span className="current-step-kicker">Current step</span>
        <h3 className="current-step-title">{workflow.current_step_title}</h3>
        <p className="current-step-detail">{workflow.current_step_detail}</p>
        {workflow.current_action && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => onAction(workflow.current_action!)}
          >
            {actionLabel(workflow.current_action)}
          </button>
        )}
      </div>

      <div className="step-timeline">
        {workflow.steps.map((step, i) => (
          <article key={step.id} className={`step-card ${step.status}`}>
            <div className="step-rail">
              <div className="step-node">
                {step.status === "done" ? <IconCheck size={12} /> : <span>{i + 1}</span>}
              </div>
              {i < workflow.steps.length - 1 && <div className="step-line" />}
            </div>
            <div className="step-body">
              <div className="step-head">
                <h4 className="step-title">
                  {step.title}
                  {step.optional && <em>optional</em>}
                </h4>
                <span className={`step-pill ${step.status}`}>{step.status}</span>
              </div>
              <p className="step-desc">{step.description}</p>
              <p className="step-detail">{step.detail}</p>
              {step.action && step.status === "active" && (
                <button
                  type="button"
                  className="btn btn-secondary btn-compact"
                  disabled={busy}
                  onClick={() => onAction(step.action!)}
                >
                  {actionLabel(step.action)}
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}