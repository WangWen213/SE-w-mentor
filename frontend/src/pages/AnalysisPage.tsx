import type { GovernanceReport } from "../api/mentorApi";
import { EmptyState } from "../components/EmptyState";
import { GovernanceDecision } from "../components/GovernanceDecision";
import { ImpactReport } from "../components/ImpactReport";

interface AnalysisPageProps {
  error: string | null;
  loading: boolean;
  onAllowOnce: () => Promise<void>;
  onDeny: () => Promise<void>;
  onReload: () => void;
  pendingAction: string | null;
  report: GovernanceReport | null;
}

export function AnalysisPage({
  error,
  loading,
  onAllowOnce,
  onDeny,
  onReload,
  pendingAction,
  report,
}: AnalysisPageProps) {
  if (loading) {
    return (
      <section className="view active">
        <div className="page">
          <EmptyState title="正在加载治理结果" body="Mentor 正在读取当前任务的影响分析和治理决策。" />
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="view active">
        <div className="page">
          <div className="page-head">
            <h1 className="page-title">治理</h1>
          </div>
          <div className="action-error" role="alert">
            <div>
              <strong>无法加载治理结果</strong>
              <span>{error}。当前任务的影响分析暂时不可用，请重新加载。</span>
            </div>
            <button className="btn" type="button" onClick={onReload}>
              重新加载
            </button>
          </div>
        </div>
      </section>
    );
  }

  if (!report) {
    return (
      <section className="view active">
        <div className="page">
          <div className="page-head">
            <h1 className="page-title">治理</h1>
          </div>
          <EmptyState title="当前没有需要处理的治理事项" body="打开并确认一个方案后，Mentor 会展示真实治理结果。" />
          <GrantPlaceholder />
        </div>
      </section>
    );
  }

  return (
    <section className="view active">
      <div className="page">
        <div className="page-head">
          <h1 className="page-title">治理</h1>
        </div>
        <div className="section-label">待你处理</div>
        <GovernanceDecision
          pendingAction={pendingAction}
          report={report}
          onAllowOnce={onAllowOnce}
          onDeny={onDeny}
        />
        <ImpactReport report={report} />
        <PolicyList report={report} />
        <GrantPlaceholder />
        <div className="section-label" style={{ marginTop: 22 }}>
          最近阻止记录
        </div>
        {report.decision === "BLOCK" ? (
          <div className="block-card">
            <div className="block-icon">×</div>
            <div>
              <div className="block-title">已阻止危险操作</div>
              <div className="block-meta">{report.ruleHits[0]?.reason ?? "后端治理已阻止该操作"}</div>
            </div>
          </div>
        ) : (
          <EmptyState title="暂无最近阻止记录" body="审计和回放将在后续阶段接入。" />
        )}
      </div>
    </section>
  );
}

function PolicyList({ report }: { report: GovernanceReport }) {
  return (
    <div className="policy-list">
      {report.ruleHits.map((hit) => (
        <div className="policy-row" key={`${hit.level}:${hit.reason}`}>
          <div className="policy-level">
            <span className={`level-dot ${hit.level === "ALLOW" ? "allow" : hit.level === "WARN" ? "ask" : "block"}`} />
            {hit.label}
          </div>
          <div className="policy-items">
            <span className="policy-chip">{hit.reason}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function GrantPlaceholder() {
  return (
    <div className="grant-card">
      <div>
        <div className="grant-title">本次授权</div>
        <div className="grant-meta">暂无本次授权 · T096 接入真实授权生命周期</div>
      </div>
      <button className="btn small" disabled type="button">
        撤销授权
      </button>
    </div>
  );
}
