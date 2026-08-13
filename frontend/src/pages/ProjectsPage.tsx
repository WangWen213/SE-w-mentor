import type { LockStatus, Project, Task } from "../api/mentorApi";
import { taskStateLabel } from "../api/mentorApi";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";

interface ProjectsPageProps {
  error: string | null;
  loading: boolean;
  lockStatus: LockStatus | null;
  onOpenTask: (taskId: string) => void;
  onStartNewTask: () => void;
  project: Project | null;
  tasks: Task[];
}

export function ProjectsPage({
  error,
  loading,
  lockStatus,
  onOpenTask,
  onStartNewTask,
  project,
  tasks,
}: ProjectsPageProps) {
  return (
    <section className="view active">
      <div className="page">
        <div className="page-head">
          <h1 className="page-title">任务</h1>
          <div className="page-actions">
            <Button onClick={onStartNewTask}>新建任务</Button>
          </div>
        </div>
        {loading ? <EmptyState title="正在加载任务" body="Mentor 正在读取后端任务列表。" /> : null}
        {error ? (
          <div className="action-error" role="alert">
            <div>
              <strong>无法加载任务</strong>
              <span>{error}。请重新打开项目或稍后重试。</span>
            </div>
          </div>
        ) : null}
        {!loading && !error && project && tasks.length === 0 ? (
          <EmptyState title="还没有任务" body="创建一个任务后，Mentor 会先整理方案，不会立即修改文件。" action="新建任务" />
        ) : null}
        {!loading && !error && !project ? (
          <EmptyState title="先打开本地项目" body="选择已授权的 Git 项目后才能创建任务。" />
        ) : null}
        {tasks.length > 0 ? (
          <div className="task-list">
            {tasks.map((task) => (
              <button className="task-card" key={task.id} type="button" onClick={() => onOpenTask(task.id)}>
                <span>
                  <span className="task-card-title">{task.request}</span>
                  <span className="task-card-meta">
                    {project?.id ?? "当前项目"} · 锁状态 {lockStatus?.status ?? "未知"}
                  </span>
                </span>
                <span className="status review">{taskStateLabel(task.status)}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
