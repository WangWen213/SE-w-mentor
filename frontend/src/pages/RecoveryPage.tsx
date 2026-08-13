import type { RecoveryItem } from "../api/mentorApi";
import { Button } from "../components/Button";

interface RecoveryPageProps {
  items: RecoveryItem[];
  pendingTaskId: string | null;
  onKeep: (taskId: string) => Promise<void>;
  onRollback: (taskId: string) => Promise<void>;
}

export function RecoveryPage({ items, onKeep, onRollback, pendingTaskId }: RecoveryPageProps) {
  return (
    <section className="view active workbench" aria-label="恢复处理">
      <header className="task-head">
        <div className="task-name-wrap">
          <div className="task-state">恢复</div>
          <h1 className="task-name">需要后端恢复决策的任务</h1>
        </div>
      </header>
      <div className="memory-list">
        {items.map((item) => (
          <div className="memory-card" key={item.taskId}>
            <span className="memory-icon" aria-hidden="true">
              R
            </span>
            <span>
              <span className="memory-title">{item.taskId}</span>
              <span className="memory-text">
                {item.conflict ? "检测到恢复冲突，需要人工处理。" : item.sideEffects}
              </span>
              <span className="memory-meta">
                <span className={item.conflict ? "memory-tag warn" : "memory-tag ok"}>
                  {item.status}
                </span>
                {item.conflict ? <span>人工处理</span> : null}
              </span>
            </span>
            {item.conflict ? null : (
              <span className="page-actions">
                <Button
                  disabled={pendingTaskId === item.taskId}
                  size="small"
                  onClick={() => void onKeep(item.taskId)}
                >
                  保留
                </Button>
                <Button
                  disabled={pendingTaskId === item.taskId}
                  size="small"
                  variant="danger"
                  onClick={() => void onRollback(item.taskId)}
                >
                  回滚
                </Button>
              </span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
