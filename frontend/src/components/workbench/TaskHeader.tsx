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
        <Button>{"\u67e5\u770b\u8303\u56f4"}</Button>
        <Button variant="danger" onClick={onStop}>
          {"\u505c\u6b62"}
        </Button>
      </div>
    </header>
  );
}
