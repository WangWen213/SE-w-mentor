import type { TaskFixture } from "../../app/fixtures";

interface ChangesPanelProps {
  active: boolean;
  task: TaskFixture;
}

export function ChangesPanel({ active, task }: ChangesPanelProps) {
  return (
    <section
      aria-labelledby="tab-changes"
      className={`panel ${active ? "active" : ""}`}
      hidden={!active}
      id="tabpanel-changes"
      role="tabpanel"
    >
      <div className="simple-panel">
        <div className="simple-list">
          {task.changes.map((change) => (
            <button className="simple-row file-row" key={change.file} type="button">
              <span className="file-dot" aria-hidden="true" />
              <span>
                <strong>{change.file}</strong>
                <span className="file-state">{change.state}</span>
              </span>
              <span className="row-spacer" />
              <span className="diff-stat">
                <span className="plus">+{change.added}</span>{" "}
                <span className="minus">-{change.removed}</span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
