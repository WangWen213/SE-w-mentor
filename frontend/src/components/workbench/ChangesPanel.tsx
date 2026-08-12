import type { TaskFixture } from "../../app/fixtures";
import { EmptyState } from "../EmptyState";

const emptyTitle = "\u5c1a\u672a\u4ea7\u751f\u771f\u5b9e\u6539\u52a8";
const emptyBody = "\u786e\u8ba4\u65b9\u6848\u5e76\u5b8c\u6210\u6cbb\u7406\u68c0\u67e5\u524d\uff0cMentor \u4e0d\u4f1a\u4fee\u6539\u6587\u4ef6\u3002";

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
        {task.changes.length === 0 ? (
          <EmptyState title={emptyTitle} body={emptyBody} />
        ) : (
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
        )}
      </div>
    </section>
  );
}
