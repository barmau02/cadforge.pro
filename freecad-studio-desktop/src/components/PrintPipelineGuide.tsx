import { buildPrintPipelineGuide } from "../lib/printPipeline";
import type { Status } from "../api";

export function PrintPipelineGuide({
  status,
  busy,
}: {
  status: Status | null;
  busy: boolean;
}) {
  const guide = buildPrintPipelineGuide(status, busy);

  return (
    <section className="print-pipeline-guide">
      <div className="print-pipeline-guide-head">
        <h3 className="print-pipeline-guide-title">{guide.headline}</h3>
        <p className="print-pipeline-guide-detail">{guide.detail}</p>
      </div>
      <ul className="print-pipeline-checklist">
        {guide.blockers.map((item) => (
          <li key={item.id} className={item.ok ? "ok" : "todo"}>
            <span className="print-pipeline-check">{item.ok ? "✓" : "○"}</span>
            <div>
              <strong>{item.label}</strong>
              {!item.ok && <span className="print-pipeline-fix">{item.fix}</span>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
