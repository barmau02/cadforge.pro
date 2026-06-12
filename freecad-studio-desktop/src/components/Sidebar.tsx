import type { ReactNode } from "react";
import { IconBox, IconDesign, IconPrint3d, IconSettings, IconTerminal, IconWorkflow } from "./icons";
import type { Section } from "../hooks/useStudio";

const NAV: { id: Section; label: string; icon: ReactNode }[] = [
  { id: "workflow", label: "Workflow", icon: <IconWorkflow size={16} /> },
  { id: "design", label: "Design", icon: <IconDesign size={16} /> },
  { id: "print", label: "Print", icon: <IconPrint3d size={16} /> },
  { id: "settings", label: "Settings", icon: <IconSettings size={16} /> },
  { id: "logs", label: "Activity", icon: <IconTerminal size={16} /> },
];

export function Sidebar({
  active,
  onSelect,
  progress,
  progressLabel = "Workflow",
}: {
  active: Section;
  onSelect: (s: Section) => void;
  progress: number;
  progressLabel?: string;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-logo">
          <IconBox size={20} />
        </div>
        <div>
          <div className="sidebar-title">PromptForge</div>
          <div className="sidebar-tagline">Concept to print</div>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Main">
        {NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`nav-item ${active === item.id ? "active" : ""}`}
            onClick={() => onSelect(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-progress-label">
          <span>{progressLabel}</span>
          <span>{progress}%</span>
        </div>
        <div className="sidebar-progress-track">
          <div
            className={`sidebar-progress-fill ${progressLabel === "Build" ? "sidebar-progress-fill--live" : ""}`}
            style={{ width: `${Math.min(100, progress)}%` }}
          />
        </div>
      </div>
    </aside>
  );
}