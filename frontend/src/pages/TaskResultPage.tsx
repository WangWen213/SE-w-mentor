import type { CompletionGate, DiffTrace, EvaluationValue, Task, TaskEvaluation, ValidationResult } from "../api/mentorApi";
import { EmptyState } from "../components/EmptyState";

const text = {
  changeQuality: "\u4fee\u6539\u8d28\u91cf",
  covered: "\u5df2\u8986\u76d6",
  evidence: "\u8bc1\u636e / \u6280\u672f\u8be6\u60c5",
  evaluation: "\u8bc4\u4f30",
  failed: "\u5931\u8d25",
  governance: "\u6cbb\u7406\u7ed3\u679c",
  noEvaluationBody: "\u4efb\u52a1\u5b8c\u6210\u5e76\u4ea7\u751f\u8bc4\u4f30\u8bb0\u5f55\u540e\u4f1a\u663e\u793a\u5728\u8fd9\u91cc\u3002",
  noEvaluationTitle: "\u6682\u65e0\u8bc4\u4f30\u7ed3\u679c",
  notRun: "\u672a\u6267\u884c",
  planned: "\u5df2\u8ba1\u5212",
  readFailed: "\u8bc4\u4f30\u8bfb\u53d6\u5931\u8d25",
  requirementCoverage: "\u9700\u6c42\u8986\u76d6",
  requiresApproval: "\u8be5\u7ed3\u679c\u9700\u8981\u4eba\u5de5\u6388\u6743\u3002",
  scope: "\u4fee\u6539\u8303\u56f4",
  selectTask: "\u9009\u62e9\u4e00\u4e2a\u4efb\u52a1\u67e5\u770b\u7ed3\u679c",
  status: "\u603b\u4f53\u72b6\u6001",
  testsExecuted: "\u5df2\u6267\u884c",
  unknown: "\u6682\u672a\u786e\u5b9a",
  uncovered: "\u5c1a\u672a\u8986\u76d6",
  validationStatus: "\u9a8c\u8bc1\u72b6\u6001",
  validationSummary: "\u9a8c\u8bc1\u72b6\u6001\u6765\u81ea\u771f\u5b9e validation plan \u548c validation run\u3002",
};

interface TaskResultPageProps {
  completionGate: CompletionGate[];
  diffTrace: DiffTrace | null;
  error: string | null;
  evaluation: TaskEvaluation | null;
  task: Task | null;
  validationResults: ValidationResult[];
}

export function TaskResultPage({
  error,
  evaluation,
  task,
}: TaskResultPageProps) {
  return (
    <section className="view active workbench evaluation-page" aria-label={text.evaluation}>
      <header className="task-head">
        <div className="task-name-wrap">
          <div className="task-state">{text.evaluation}</div>
          <h1 className="task-name">{task?.request ?? text.selectTask}</h1>
        </div>
      </header>
      {error ? <EmptyState title={text.readFailed} body={error} /> : null}
      {!error && !evaluation ? (
        <EmptyState title={text.noEvaluationTitle} body={text.noEvaluationBody} />
      ) : null}
      {!error && evaluation ? <EvaluationSurface evaluation={evaluation} /> : null}
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
          ["\u98ce\u9669", evaluation.changeQuality.risks],
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
