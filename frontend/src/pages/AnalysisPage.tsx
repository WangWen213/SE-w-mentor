import type { ReactNode } from "react";

import type { GovernanceReport } from "../api/mentorApi";
import { governanceDecisionLabel } from "../api/mentorApi";
import { EmptyState } from "../components/EmptyState";
import { GovernanceDecision } from "../components/GovernanceDecision";
import { ImpactReport } from "../components/ImpactReport";

const text = {
  blockedAction: "已阻止危险操作",
  blockedFallback: "后端治理已阻止该操作",
  blockLog: "阻止记录",
  errorBody: "当前任务的治理结果读取失败，请重新加载。",
  errorTitle: "治理结果读取失败",
  governance: "治理",
  loadingBody: "Mentor 正在读取当前任务的影响分析和治理决策。",
  loadingTitle: "正在加载治理结果",
  noBlockBody: "当前治理结果没有阻止该任务。",
  noBlockTitle: "暂无阻止记录",
  noReportBody: "当前任务还没有完成方案确认与影响分析。治理完成后，可在这里查看决策依据。",
  noReportTitle: "尚未生成治理结果",
  pending: "治理决策",
  reload: "重新加载",
  unknown: "暂未确定",
};

interface AnalysisPageProps {
  approved: boolean;
  error: string | null;
  loading: boolean;
  onAllowOnce: () => Promise<void>;
  onDeny: () => Promise<void>;
  onReload: () => void;
  pendingAction: string | null;
  report: GovernanceReport | null;
  state: "LOADING" | "READY" | "NOT_GENERATED" | "ERROR";
}

export function AnalysisPage({
  approved,
  error,
  loading,
  onAllowOnce,
  onDeny,
  onReload,
  pendingAction,
  report,
  state,
}: AnalysisPageProps) {
  if (loading || state === "LOADING") {
    return <GovernanceShell><EmptyState title={text.loadingTitle} body={text.loadingBody} /></GovernanceShell>;
  }

  if (state === "ERROR" && !report) {
    return (
      <GovernanceShell>
        <GovernanceError message={error ?? text.errorBody} onReload={onReload} />
      </GovernanceShell>
    );
  }

  if (state === "NOT_GENERATED" || !report) {
    return (
      <GovernanceShell>
        <EmptyState title={text.noReportTitle} body={text.noReportBody} />
      </GovernanceShell>
    );
  }

  return (
    <GovernanceShell>
      {error ? <GovernanceError message={`${error}。已保留当前可用的治理结果。`} onReload={onReload} /> : null}
      <div className="section-label">{text.pending}</div>
      <GovernanceDecision
        approved={approved}
        pendingAction={pendingAction}
        report={report}
        onAllowOnce={onAllowOnce}
        onDeny={onDeny}
      />
      <ImpactReport report={report} />
      <PolicyList report={report} />
      <div className="section-label" style={{ marginTop: 22 }}>
        {text.blockLog}
      </div>
      {report.decision === "BLOCK" ? (
        <div className="block-card">
          <div className="block-icon">!</div>
          <div>
            <div className="block-title">{text.blockedAction}</div>
            <div className="block-meta">{report.ruleHits[0]?.reason ?? text.blockedFallback}</div>
          </div>
        </div>
      ) : (
        <EmptyState title={text.noBlockTitle} body={text.noBlockBody} />
      )}
    </GovernanceShell>
  );
}

function GovernanceShell({ children }: { children: ReactNode }) {
  return (
    <section className="view active">
      <div className="page">
        <div className="page-head">
          <h1 className="page-title">{text.governance}</h1>
        </div>
        {children}
      </div>
    </section>
  );
}

function GovernanceError({ message, onReload }: { message: string; onReload: () => void }) {
  return (
    <div className="action-error" role="alert">
      <div>
        <strong>{text.errorTitle}</strong>
        <span>{message}</span>
      </div>
      <button className="btn" type="button" onClick={onReload}>
        {text.reload}
      </button>
    </div>
  );
}

function PolicyList({ report }: { report: GovernanceReport }) {
  return (
    <div className="policy-list">
      {report.ruleHits.map((hit) => (
        <div className="policy-row" key={`${hit.level}:${hit.reason}`}>
          <div className="policy-level">
            <span className={`level-dot ${hit.level === "ALLOW" ? "allow" : hit.level === "WARN" ? "ask" : "block"}`} />
            {governanceDecisionLabel(hit.level)}
          </div>
          <div className="policy-items">
            <span className="policy-chip">{presentReason(hit.reason)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function presentReason(value: string) {
  const trimmed = value.trim();
  if (!trimmed || trimmed.toUpperCase() === "UNKNOWN") {
    return text.unknown;
  }
  const labels: Record<string, string> = {
    "Allowed within finite changed path scope.": "修改范围有限，符合当前批准范围。",
    "Public or authentication-related changes require user approval.": "公共接口或认证相关修改需要你的确认。",
    "Sensitive credential or environment files are blocked.": "敏感凭据或环境文件修改已被阻止。",
  };
  return labels[trimmed] ?? trimmed;
}
