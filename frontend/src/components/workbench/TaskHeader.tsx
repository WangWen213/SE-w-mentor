import type { TaskFixture } from "../../app/fixtures";
import { Button } from "../Button";
import { StatusBadge } from "../StatusBadge";

interface TaskHeaderProps {
  task: TaskFixture;
  onStop: () => void;
}

export function TaskHeader({ task, onStop }: TaskHeaderProps) {
  return (
    <header className="task-head">
      <div className="task-name-wrap">
        <div className="task-state">
          <StatusBadge tone="warn">{task.status}</StatusBadge>
        </div>
        <h1 className="task-name">{task.title}</h1>
      </div>
      <div className="task-head-actions">
        <Button>查看范围</Button>
        <Button variant="danger" onClick={onStop}>
          停止
        </Button>
      </div>
    </header>
  );
}
