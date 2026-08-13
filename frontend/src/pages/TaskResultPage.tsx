import type { CompletionGate, DiffTrace, EvaluationValue, Task, TaskEvaluation, ValidationResult } from "../api/mentorApi";
import { EmptyState } from "../components/EmptyState";

const text = {
  changeQuality: "改动质量",
  covered: "已覆盖",
  evidence: "证据 / 技术详情",
  evaluation: "评估",
  failed: "失败",
  governance: "治理结果",
  loading: "正在读取评估",
  loadingBody: "Mentor 正在读取已持久化的任务评估记录。",
  noEvaluationBody: "任务完成并产生评估记录后会显示在这里。",
  noEvaluationTitle: "暂无评估结果",
  notRun: "未执行",
  planned: "已计划",
  readFailed: "评估读取失败",
  requirementCoverage: "需求覆盖",
  requiresApproval: "该结果需要人工授权。",
  scope: "实际改动",
  status: "总体状态",
  testsExecuted: "已执行",
  unknown: "暂未确定",
  uncovered: "尚未覆盖",
  validationStatus: "验证情况",
  validationSummary: "验证状态来自真实 validation plan 和 validation run。",
};

interface TaskResultPageProps {
  completionGate: CompletionGate[];
  diffTrace: DiffTrace | null;
  error: string | null;
  evaluations: TaskEvaluation[];
  loading: boolean;
  task: Task | null;
  validationResults: ValidationResult[];
}

export function TaskResultPage({
  error,
  evaluations,
  loading,
  task,
}: TaskResultPageProps) {
  const activeEvaluation =
    (task ? evaluations.find((item) => item.taskId === task.id) : null) ?? evaluations[0] ?? null;
  return (
    <section className="view active workbench evaluation-page" aria-label={text.evaluation}>
      <header className="task-head">
        <div className="task-name-wrap">
          <div className="task-state">{text.evaluation}</div>
          <h1 className="task-name">{activeEvaluation?.taskTitle ?? task?.request ?? text.evaluation}</h1>
        </div>
      </header>
      {loading ? <EmptyState title={text.loading} body={text.loadingBody} /> : null}
      {!loading && error ? <EmptyState title={text.readFailed} body={error} /> : null}
      {!loading && !error && evaluations.length === 0 ? (
        <EmptyState title={text.noEvaluationTitle} body={text.noEvaluationBody} />
      ) : null}
      {!loading && !error && evaluations.length > 0 ? (
        <div className="evaluation-list">
          {evaluations.map((evaluation) => (
            <EvaluationSurface evaluation={evaluation} key={evaluation.taskId} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function EvaluationSurface({ evaluation }: { evaluation: TaskEvaluation }) {
  if (!evaluation.hasEvaluation) {
    return <EmptyState title={text.noEvaluationTitle} body={presentUnknown(evaluation.overall.summary)} />;
  }
  return (
    <div className="evaluation-surface">
      <section className="result-card">
        <div className="result-title">{text.status}</div>
        <h2>{presentUnknown(evaluation.overall.title)}</h2>
        <p className="detail-text">{presentUnknown(evaluation.overall.summary)}</p>
      </section>
      <EvaluationSection
        title={text.requirementCoverage}
        summary={presentUnknown(evaluation.requirementCoverage.summary)}
        groups={[
          [text.covered, evaluation.requirementCoverage.covered],
          [text.uncovered, evaluation.requirementCoverage.uncovered],
        ]}
      />
      <EvaluationSection
        title={text.changeQuality}
        summary={presentUnknown(evaluation.changeQuality.summary)}
        groups={[
          [text.scope, evaluation.changeQuality.scope],
          ["风险", evaluation.changeQuality.risks],
        ]}
      />
      <section className="result-card">
        <div className="result-title">{text.governance}</div>
        <div className="evaluation-line">
          <strong>{presentUnknown(evaluation.governance.decision)}</strong>
          <span>{presentUnknown(evaluation.governance.reason)}</span>
        </div>
        {evaluation.governance.requiresApproval ? (
          <p className="detail-text">{text.requiresApproval}</p>
        ) : null}
      </section>
      <EvaluationSection
        title={text.validationStatus}
        summary={text.validationSummary}
        groups={[
          [text.planned, evaluation.validation.planned],
          [text.testsExecuted, evaluation.validation.executed],
          [text.failed, evaluation.validation.failed],
          [text.notRun, evaluation.validation.notRun],
        ]}
      />
      <details className="evaluation-details">
        <summary>{text.evidence}</summary>
        <div className="memory-chips">
          {evaluation.evidence.summary.map((item) => (
            <span key={item}>{presentUnknown(item)}</span>
          ))}
        </div>
        <pre>{JSON.stringify(evaluation.evidence.technical, null, 2)}</pre>
      </details>
    </div>
  );
}

function EvaluationSection({
  groups,
  summary,
  title,
}: {
  groups: Array<[string, EvaluationValue[]]>;
  summary: string;
  title: string;
}) {
  return (
    <section className="result-card">
      <div className="result-title">{title}</div>
      <p className="detail-text">{presentUnknown(summary)}</p>
      <div className="evaluation-groups">
        {groups.map(([label, values]) => (
          <div className="evaluation-group" key={label}>
            <h3>{label}</h3>
            {values.length > 0 ? (
              <ul>
                {values.map((value, index) => (
                  <li key={itemKey(value, index)}>{renderEvaluationValue(value)}</li>
                ))}
              </ul>
            ) : (
              <p className="detail-text">{text.unknown}</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function presentUnknown(value: string) {
  const trimmed = value.trim();
  return !trimmed || trimmed.toUpperCase() === "UNKNOWN" || /^scope is unknown$/i.test(trimmed)
    ? text.unknown
    : value;
}

function renderEvaluationValue(value: EvaluationValue) {
  if (typeof value === "string") {
    return presentUnknown(value);
  }
  const file = field(value, "relative_path") ?? field(value, "path") ?? field(value, "file");
  const kind = field(value, "kind");
  const symbol = field(value, "symbol_name") ?? field(value, "symbol");
  const confidence = field(value, "confidence");
  const summary = field(value, "summary") ?? field(value, "narrative");
  const refs = arrayField(value, "evidence_refs") ?? arrayField(value, "fact_refs");
  return (
    <span className="evaluation-value">
      {file ? <span>文件：{file}</span> : null}
      {kind ? <span>类型：{kind}</span> : null}
      {symbol ? <span>符号：{symbol}</span> : null}
      {confidence ? <span>置信度：{confidence}</span> : null}
      {summary ? <span>说明：{presentUnknown(summary)}</span> : null}
      {refs && refs.length > 0 ? <span>依据：{refs.join("、")}</span> : null}
      {!file && !kind && !symbol && !confidence && !summary && !refs ? (
        <span>{Object.entries(value).map(([key, item]) => `${presentKey(key)}：${String(item)}`).join("；")}</span>
      ) : null}
    </span>
  );
}

function itemKey(value: EvaluationValue, index: number) {
  return `${index}:${typeof value === "string" ? value : JSON.stringify(value)}`;
}

function field(value: Record<string, unknown>, key: string) {
  const item = value[key];
  return typeof item === "string" && item.trim() ? item : null;
}

function arrayField(value: Record<string, unknown>, key: string) {
  const item = value[key];
  return Array.isArray(item) ? item.map((entry) => String(entry)).filter(Boolean) : null;
}

function presentKey(key: string) {
  const labels: Record<string, string> = {
    evidence_refs: "依据",
    fact_refs: "事实依据",
    kind: "类型",
    narrative: "分析说明",
    relative_path: "文件",
    risks: "风险",
    symbol_name: "符号",
  };
  return labels[key] ?? key;
}
