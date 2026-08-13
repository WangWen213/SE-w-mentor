import type { DiffTrace, TaskStatus } from "../../api/mentorApi";
import { EmptyState } from "../EmptyState";

const emptyTitle = "\u5c1a\u672a\u4ea7\u751f\u771f\u5b9e\u6539\u52a8";
const waitingBody = "\u6b63\u5728\u7b49\u5f85\u9996\u4e2a\u6587\u4ef6\u6539\u52a8\u3002";
const pendingBody = "\u786e\u8ba4\u65b9\u6848\u5e76\u5b8c\u6210\u6cbb\u7406\u68c0\u67e5\u524d\uff0cMentor \u4e0d\u4f1a\u4fee\u6539\u6587\u4ef6\u3002";
const failedBody = "\u672c\u6b21\u6267\u884c\u672a\u4ea7\u751f\u6587\u4ef6\u6539\u52a8\u3002";

interface ChangesPanelProps {
  active: boolean;
  changes: DiffTrace[];
  error?: string | null;
  hasLoaded?: boolean;
  loading?: boolean;
  taskStatus: TaskStatus;
}

export function ChangesPanel({
  active,
  changes,
  error = null,
  hasLoaded = false,
  loading = false,
  taskStatus,
}: ChangesPanelProps) {
  const initialLoading = loading && !hasLoaded && changes.length === 0;
  const empty = hasLoaded && !loading && changes.length === 0;
  return (
    <section
      aria-labelledby="tab-changes"
      className={`panel ${active ? "active" : ""}`}
      hidden={!active}
      id="tabpanel-changes"
      role="tabpanel"
    >
      <div className="simple-panel">
        {initialLoading ? (
          <EmptyState title="\u6b63\u5728\u8bfb\u53d6\u771f\u5b9e\u6539\u52a8" body="\u6b63\u5728\u4ece\u540e\u7aef FileChange \u8bb0\u5f55\u8bfb\u53d6\u3002" />
        ) : error && changes.length === 0 ? (
          <EmptyState title="\u6539\u52a8\u8bfb\u53d6\u5931\u8d25" body={error} />
        ) : empty ? (
          <EmptyState title={emptyTitle} body={emptyBodyFor(taskStatus)} />
        ) : (
          <div className="simple-list">
            {error ? <div className="subtle-refresh error">{error}</div> : null}
            {changes.map((change) => (
              <div className="file-change-row" key={change.changeId}>
                <div className="simple-row file-row">
                <span className="file-dot" aria-hidden="true" />
                <span>
                    <strong>{change.filePath}</strong>
                    <span className="file-state">
                      {changeOperation(change)} · {change.changeId}
                    </span>
                </span>
                <span className="row-spacer" />
                <span className="diff-stat">
                    <span className="plus">+{countDiffLines(change.diff, "+")}</span>{" "}
                    <span className="minus">-{countDiffLines(change.diff, "-")}</span>
                </span>
                </div>
                <pre className="inline-diff" aria-label={`${change.filePath} diff`}>
                  {change.diff}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function emptyBodyFor(status: TaskStatus) {
  if (status === "EXECUTING") {
    return waitingBody;
  }
  if (status === "FAILED") {
    return failedBody;
  }
  return pendingBody;
}

function changeOperation(change: DiffTrace) {
  if (change.operation) {
    return change.operation;
  }
  if (!change.modified) {
    return "\u672a\u4fee\u6539";
  }
  return change.backedUp ? "MODIFY" : "CREATE";
}

function countDiffLines(diff: string, marker: "+" | "-") {
  return diff
    .split("\n")
    .filter((line) => line.startsWith(marker) && !line.startsWith(`${marker}${marker}${marker}`))
    .length;
}
