import type { TaskFixture } from "../../app/fixtures";
import { StatusBadge } from "../StatusBadge";

interface ChecksPanelProps {
  active: boolean;
  task: TaskFixture;
}

export function ChecksPanel({ active, task }: ChecksPanelProps) {
  return (
    <section
      aria-labelledby="tab-checks"
      className={`panel ${active ? "active" : ""}`}
      hidden={!active}
      id="tabpanel-checks"
      role="tabpanel"
    >
      <div className="simple-panel">
        <div className="simple-list">
          {task.checks.map((check) => (
            <div className="simple-row" key={check.label}>
              <strong>{check.label}</strong>
              <span className="row-spacer" />
              <StatusBadge tone={check.tone}>{check.state}</StatusBadge>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
