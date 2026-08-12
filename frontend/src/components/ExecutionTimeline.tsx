import type { TaskEvent } from "../api/mentorApi";
import { taskEventLabel } from "../api/mentorApi";

interface ExecutionTimelineProps {
  events: TaskEvent[];
  reconnecting: boolean;
}

export function ExecutionTimeline({ events, reconnecting }: ExecutionTimelineProps) {
  return (
    <section className="simple-panel" aria-label="执行进度">
      {reconnecting ? (
        <div className="recovery-banner" role="status">
          <strong>正在重新连接任务进度</strong>
          <span>Mentor 会从上次事件继续读取。</span>
        </div>
      ) : null}
      <div className="simple-list">
        {events.length === 0 ? (
          <div className="simple-row">
            <strong>等待后端执行状态</strong>
            <span className="file-state">进入执行后会显示真实任务事件。</span>
          </div>
        ) : null}
        {events.map((event) => (
          <div className="simple-row" key={event.eventId}>
            <span className="file-dot" aria-hidden="true" />
            <span>
              <strong>{taskEventLabel(event.eventType)}</strong>
              <span className="file-state">{presentEventMessage(event)}</span>
            </span>
            <span className="row-spacer" />
            <span className="diff-stat">#{event.eventId}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function presentEventMessage(event: TaskEvent) {
  const value = event.payload.message ?? event.payload.state ?? "状态已更新";
  const labels: Record<string, string> = {
    "cancel requested": "已请求停止",
    "execution started": "执行已开始",
  };
  return labels[value] ?? value;
}
