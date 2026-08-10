import type { CompletionGate, DiffTrace, Task, ValidationResult } from "../api/mentorApi";
import { DiffViewer } from "../components/DiffViewer";
import { ValidationReport } from "../components/ValidationReport";

interface TaskResultPageProps {
  completionGate: CompletionGate[];
  diffTrace: DiffTrace | null;
  task: Task | null;
  validationResults: ValidationResult[];
}

export function TaskResultPage({
  completionGate,
  diffTrace,
  task,
  validationResults,
}: TaskResultPageProps) {
  return (
    <section className="view active workbench" aria-label="任务结果">
      <header className="task-head">
        <div className="task-name-wrap">
          <div className="task-state">结果</div>
          <h1 className="task-name">{task?.request ?? "选择一个任务查看结果"}</h1>
        </div>
      </header>
      <DiffViewer trace={diffTrace} />
      <ValidationReport gates={completionGate} results={validationResults} />
    </section>
  );
}
