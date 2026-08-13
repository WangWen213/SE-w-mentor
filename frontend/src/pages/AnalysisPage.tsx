import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import type { GovernanceDecisionKind, GovernanceReport, ProjectGovernanceHistoryItem } from "../api/mentorApi";
import { governanceDecisionLabel } from "../api/mentorApi";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { GovernanceDecision } from "../components/GovernanceDecision";
import { ImpactReport } from "../components/ImpactReport";

const text = {
  all: "全部",
  allow: "自动允许",
  blocked: "已阻止",
  detail: "查看详情",
  detailError: "治理详情读取失败",
  detailLoading: "正在读取详情",
  emptyBody: "项目中的治理结果会在任务完成影响分析后记录在这里。",
  emptyTitle: "暂无治理记录",
  errorBody: "项目治理历史读取失败，请重新加载。",
  errorTitle: "治理历史读取失败",
  files: "影响",
  governance: "治理",
  history: "治理历史记录",
  loadMore: "加载更多",
  loadingTitle: "正在读取治理历史",
  projectBody: "当前项目中的治理记录都会保留在这里。",
  refreshing: "正在更新",
  reload: "重新加载",
  selectedDetail: "治理详情",
  warn: "需要确认",
};

interface AnalysisPageProps {
  approved: boolean;
  detail: GovernanceReport | null;
  detailError: string | null;
  detailLoading: boolean;
  error: string | null;
  hasMore: boolean;
  history: ProjectGovernanceHistoryItem[];
  loading: boolean;
  loadingMore: boolean;
  onAllowOnce: () => Promise<void>;
  onDeny: () => Promise<void>;
  onLoadMore: () => void;
  onReload: () => void;
  onSelectDecision: (decision: ProjectGovernanceHistoryItem) => void;
  pendingAction: string | null;
  refreshing: boolean;
  selectedDecisionId: string | null;
  state: "UNINITIALIZED" | "LOADING" | "READY" | "ERROR";
}

export function AnalysisPage({
  approved,
  detail,
  detailError,
  detailLoading,
  error,
  hasMore,
  history,
  loading,
  loadingMore,
  onAllowOnce,
  onDeny,
  onLoadMore,
  onReload,
  onSelectDecision,
  pendingAction,
  refreshing,
  selectedDecisionId,
  state,
}: AnalysisPageProps) {
  const [filter, setFilter] = useState<"ALL" | GovernanceDecisionKind>("ALL");
  const filteredHistory = useMemo(
    () => history.filter((item) => filter === "ALL" || item.decision === filter),
    [filter, history],
  );

  if ((loading || state === "LOADING") && history.length === 0) {
    return (
      <GovernanceShell>
        <div className="governance-skeleton" aria-label={text.loadingTitle}>
          <div />
          <div />
          <div />
        </div>
      </GovernanceShell>
    );
  }

  if (state === "ERROR" && history.length === 0) {
    return (
      <GovernanceShell>
        <GovernanceError message={error ?? text.errorBody} onReload={onReload} />
      </GovernanceShell>
    );
  }

  return (
    <GovernanceShell>
      {error ? <GovernanceError message={`${error}。已保留当前可用的治理历史。`} onReload={onReload} /> : null}
      <p className="page-subtitle">{text.projectBody}</p>
      <div className="governance-filter" role="tablist" aria-label="治理筛选">
        <FilterButton active={filter === "ALL"} label={text.all} onClick={() => setFilter("ALL")} />
        <FilterButton active={filter === "ALLOW"} label={text.allow} onClick={() => setFilter("ALLOW")} />
        <FilterButton active={filter === "WARN"} label={text.warn} onClick={() => setFilter("WARN")} />
        <FilterButton active={filter === "BLOCK"} label={text.blocked} onClick={() => setFilter("BLOCK")} />
        {refreshing ? <span className="governance-refreshing">{text.refreshing}</span> : null}
      </div>
      <div className="section-label">{text.history}</div>
      {history.length === 0 ? <EmptyState title={text.emptyTitle} body={text.emptyBody} /> : null}
      {history.length > 0 && filteredHistory.length === 0 ? (
        <EmptyState title={text.emptyTitle} body={text.emptyBody} />
      ) : null}
      <div className="governance-history-list">
        {filteredHistory.map((item) => (
          <button
            className={`governance-history-row ${selectedDecisionId === item.governanceDecisionId ? "selected" : ""}`}
            key={item.governanceDecisionId}
            type="button"
            onClick={() => onSelectDecision(item)}
          >
            <div className="governance-row-status">
              <span className={`governance-status-dot ${statusClass(item.decision)}`} />
              <span>{governanceDecisionLabel(item.decision)}</span>
            </div>
            <div className="governance-row-main">
              <div className="governance-row-title">{item.taskTitle}</div>
              <div className="governance-row-summary">{item.displaySummary || item.summary}</div>
              {item.proposalVersion ? (
                <div className="governance-row-version">Proposal v{item.proposalVersion}</div>
              ) : null}
            </div>
            <div className="governance-row-meta">
              <span>
                {text.files} {item.affectedFileCount} 个文件
              </span>
              <time dateTime={item.createdAt}>{formatTime(item.createdAt)}</time>
              <span className="governance-detail-link">{text.detail} →</span>
            </div>
          </button>
        ))}
      </div>
      {hasMore ? (
        <div className="governance-load-more">
          <Button disabled={loadingMore} onClick={onLoadMore}>
            {loadingMore ? text.refreshing : text.loadMore}
          </Button>
        </div>
      ) : null}
      {selectedDecisionId ? (
        <section className="governance-detail-section">
          <div className="section-label">{text.selectedDetail}</div>
          {detailLoading ? <EmptyState title={text.detailLoading} body="" /> : null}
          {detailError ? <GovernanceError message={detailError} onReload={onReload} /> : null}
          {detail && !detailLoading ? (
            <>
              <GovernanceDecision
                approved={approved}
                pendingAction={pendingAction}
                report={detail}
                onAllowOnce={onAllowOnce}
                onDeny={onDeny}
              />
              <ImpactReport report={detail} />
            </>
          ) : null}
        </section>
      ) : null}
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

function FilterButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button className={`filter ${active ? "active" : ""}`} type="button" onClick={onClick}>
      {label}
    </button>
  );
}

function statusClass(decision: GovernanceDecisionKind): string {
  return decision.toLowerCase();
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
  });
}
