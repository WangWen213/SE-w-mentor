import type { Task, TaskEvent } from "../api/mentorApi";
import { Button } from "../components/Button";
import { ExecutionTimeline } from "../components/ExecutionTimeline";

interface ExecutionPageProps {
  cancelPending: boolean;
  error: string | null;
  events: TaskEvent[];
  onCancel: () => Promise<void>;
  onReconnect: () => Promise<void>;
  reconnecting: boolean;
  task: Task;
}

export function ExecutionPage({
  cancelPending,
  error,
  events,
  onCancel,
  onReconnect,
  reconnecting,
  task,
}: ExecutionPageProps) {
  return (
    <section className="view active workbench" aria-label="执行中的任务">
      <header className="task-head">
        <div className="task-name-wrap">
          <div className="task-state">{cancelPending ? "正在停止" : "正在执行"}</div>
          <h1 className="task-name">{task.request}</h1>
        </div>
        <div className="task-head-actions">
          <Button disabled={cancelPending} variant="danger" onClick={onCancel}>
            {cancelPending ? "正在停止" : "停止任务"}
          </Button>
        </div>
      </header>
      {error ? (
        <div className="action-error" role="alert">
          <div>
            <strong>任务暂时无法开始</strong>
            <span>{error}。请查看任务状态后重试。</span>
          </div>
          <Button onClick={onReconnect}>重新连接</Button>
        </div>
      ) : null}
      <ExecutionTimeline events={events} reconnecting={reconnecting} />
      <div className="composer-wrap show">
        <div className="composer">
          <label className="sr-only" htmlFor="execution-note">
            执行中说明
          </label>
          <textarea
            aria-label="执行中说明"
            disabled
            id="execution-note"
            placeholder="任务执行中。扩大范围的输入会在后续阶段由后端重新治理。"
          />
          <div className="composer-bottom">
            <span className="ghost">安全点、保留和回滚由后端决定；真实回滚将在 T097 接入。</span>
          </div>
        </div>
      </div>
    </section>
  );
}
