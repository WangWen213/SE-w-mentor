import { useRef, useState } from "react";

import type { DiffTrace, GovernanceReport, Proposal, Task } from "../api/mentorApi";
import type { TaskTab, WorkbenchMessage, WorkbenchTimelineItem } from "../app/fixtures";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { GovernanceDecision } from "../components/GovernanceDecision";
import { ChangesPanel } from "../components/workbench/ChangesPanel";
import { ChecksPanel } from "../components/workbench/ChecksPanel";
import { Conversation } from "../components/workbench/Conversation";
import { TaskTabs } from "../components/workbench/TaskTabs";
import type { NewTaskStage } from "./NewTaskPage";

const text = {
  adjustment: "\u65b9\u6848\u8c03\u6574",
  adjustmentPlaceholder: "\u544a\u8bc9 Mentor \u4f60\u5e0c\u671b\u5982\u4f55\u8c03\u6574\u65b9\u6848\u2026",
  analyzingPlaceholder: "Mentor \u6b63\u5728\u751f\u6210\u65b9\u6848\u2026",
  answerPlaceholder: "\u56de\u7b54 Mentor \u7684\u95ee\u9898\u2026",
  checksAcceptance: "\u5f85\u786e\u8ba4",
  confirm: "\u786e\u8ba4\u6b64\u8303\u56f4",
  confirming: "\u786e\u8ba4\u4e2d",
  confirmHint: "\u786e\u8ba4\u540e Mentor \u4f1a\u81ea\u52a8\u5206\u6790\u5f71\u54cd\u3001\u8fdb\u884c\u6cbb\u7406\u68c0\u67e5\u5e76\u5728\u5141\u8bb8\u65f6\u7ee7\u7eed\u6267\u884c\u3002",
  confirmUnavailable: "\u771f\u5b9e\u65b9\u6848\u751f\u6210\u540e\u624d\u80fd\u786e\u8ba4\u7ee7\u7eed\u3002",
  failed: "\u65b9\u6848\u751f\u6210\u5931\u8d25",
  failedFallback: "\u6a21\u578b\u6ca1\u6709\u8fd4\u56de\u53ef\u7528\u65b9\u6848\u3002",
  loadingBody: "Mentor \u6b63\u5728\u8bfb\u53d6\u4efb\u52a1\u548c\u65b9\u6848\u3002",
  loadingTitle: "\u6b63\u5728\u52a0\u8f7d\u4efb\u52a1",
  missing: "\u9700\u8981\u8865\u5145\u4fe1\u606f",
  noTaskBody: "\u8bf7\u9009\u62e9\u4e00\u4e2a\u4efb\u52a1\uff0c\u6216\u521b\u5efa\u65b0\u4efb\u52a1\u3002",
  noTaskTitle: "\u5c1a\u672a\u6253\u5f00\u4efb\u52a1",
  regenerate: "\u91cd\u65b0\u751f\u6210\u65b9\u6848",
  retryPlaceholder: "\u53ef\u7ee7\u7eed\u8f93\u5165\u8865\u5145\u8bf4\u660e\uff0c\u6216\u70b9\u51fb\u91cd\u65b0\u751f\u6210\u65b9\u6848\u3002",
  stop: "\u505c\u6b62\u4efb\u52a1",
  submitAnswer: "\u63d0\u4ea4\u56de\u7b54",
  taskCoverage: "\u9700\u6c42\u8986\u76d6",
  taskInfo: "\u8865\u5145\u4fe1\u606f",
  taskScope: "\u8303\u56f4\u63a7\u5236",
  taskTests: "\u76f8\u5173\u6d4b\u8bd5",
  toGovern: "\u5f85\u6cbb\u7406\u68c0\u67e5",
  toReview: "\u5f85\u590d\u6838",
  viewGovernance: "\u67e5\u770b\u6cbb\u7406\u8be6\u60c5",
  waiting: "\u7b49\u5f85\u65b9\u6848",
  workbench: "\u5de5\u4f5c\u53f0",
};

interface ProposalReviewPageProps {
  approvalAction?: string | null;
  approvalGranted?: boolean;
  changes?: DiffTrace[];
  changesError?: string | null;
  changesHasLoaded?: boolean;
  changesLoading?: boolean;
  conversationMessages?: WorkbenchMessage[];
  timelineItems?: WorkbenchTimelineItem[];
  error: string | null;
  governanceError?: string | null;
  governanceReport?: GovernanceReport | null;
  harnessProgress: string | null;
  loading: boolean;
  onAdjust?: (message: string) => Promise<void>;
  onSubmitTurn?: (message: string) => Promise<void>;
  onAllowGovernance?: () => Promise<void>;
  onCancel: () => Promise<void>;
  onConfirm: () => Promise<void>;
  onDenyGovernance?: () => Promise<void>;
  onOpenChanges?: () => void;
  onNeedAnswer?: (message: string) => Promise<void>;
  onOpenGovernance?: () => void;
  onRetryProposal?: () => Promise<void>;
  pendingAction: string | null;
  proposal: Proposal | null;
  proposalState?: "LOADING" | "NOT_CREATED" | "EXISTS";
  stage?: NewTaskStage;
  task: Task | null;
}

export function ProposalReviewPage({
  approvalAction,
  approvalGranted = false,
  changes = [],
  changesError = null,
  changesHasLoaded = false,
  changesLoading = false,
  conversationMessages = [],
  error,
  governanceError = null,
  governanceReport = null,
  harnessProgress = null,
  loading,
  onAdjust,
  onAllowGovernance,
  onCancel,
  onConfirm,
  onDenyGovernance,
  onOpenChanges,
  onSubmitTurn,
  onOpenGovernance,
  onRetryProposal,
  pendingAction,
  proposal,
  proposalState = "NOT_CREATED",
  stage = "IDLE",
  task,
  timelineItems = [],
}: ProposalReviewPageProps) {
  const [activeTab, setActiveTab] = useState<TaskTab>("conversation");
  const [composerText, setComposerText] = useState("");
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  if (loading) {
    return <EmptyWorkbench title={text.loadingTitle} body={text.loadingBody} />;
  }
  if (!task) {
    return <EmptyWorkbench title={text.noTaskTitle} body={text.noTaskBody} />;
  }

  const proposalFailed = stage === "PROPOSAL_FAILED" || Boolean(error && proposal === null);
  const hasProposal = proposal !== null && !proposalFailed;
  const proposalConfirmed = hasProposal && proposal.status === "CONFIRMED";
  const proposalCanConfirm = hasProposal && (proposal.completeness?.canConfirm ?? true);
  const proposalLoading = proposalState === "LOADING";
  const analyzing = !hasProposal && !proposalFailed && !proposalLoading;
  const busy = pendingAction !== null || Boolean(harnessProgress);
  const displayState = deriveProposalDisplayState({
    hasProposal,
    proposalConfirmed,
    proposalFailed,
    proposalState,
  });
  const displayStateLabel = stageLabel(displayState);

  const messages = conversationMessages;

  const openTab = (tab: TaskTab) => {
    setActiveTab(tab);
    if (tab === "changes") {
      onOpenChanges?.();
    }
  };

  const focusComposer = () => {
    setActiveTab("conversation");
    composerRef.current?.focus();
  };

  const taskForConversation = {
    title: task.request,
    status: displayStateLabel,
    messages,
    timeline: timelineItems,
    changes: [],
    checks: [
      { label: text.taskCoverage, state: hasProposal ? text.toReview : text.waiting, tone: "neutral" as const },
      { label: text.taskTests, state: hasProposal ? text.toReview : text.waiting, tone: "neutral" as const },
      { label: text.taskScope, state: hasProposal ? text.toGovern : text.waiting, tone: "neutral" as const },
      {
        label: text.taskInfo,
        state: proposal?.missingInformationQuestion ? text.missing : hasProposal ? text.checksAcceptance : text.waiting,
        tone: "warn" as const,
      },
    ],
  };

  const submitComposer = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = composerText.trim();
    if (pendingAction !== null) {
      return;
    }
    if (proposalFailed) {
      await onRetryProposal?.();
      setComposerText("");
      return;
    }
    if (!value || !hasProposal) {
      return;
    }
    const submitTurn = onSubmitTurn ?? onAdjust;
    if (!submitTurn) {
      return;
    }
    setComposerText("");
    void submitTurn(value);
  };

  return (
    <section className="view active workbench" aria-label={text.workbench}>
      <header className="task-head">
        <div className="task-name-wrap">
          <div className="task-state">{displayStateLabel}</div>
          <h1 className="task-name">{task.request}</h1>
        </div>
        <div className="task-head-actions">
          <Button variant="danger" disabled={pendingAction !== null || !hasProposal} onClick={onCancel}>
            {text.stop}
          </Button>
        </div>
      </header>
      {hasProposal && proposal.missingInformationQuestion ? (
        <div className="recovery-banner" role="status">
          <strong>{text.missing}</strong>
          <span>{proposal.missingInformationQuestion}</span>
        </div>
      ) : null}
      {proposalFailed ? (
        <div className="recovery-banner" role="alert">
          <strong>{text.failed}</strong>
          <span>{error ?? text.failedFallback}</span>
          <Button disabled={pendingAction !== null} onClick={() => void onRetryProposal?.()}>
            {text.regenerate}
          </Button>
        </div>
      ) : null}
      {harnessProgress ? (
        <div className="recovery-banner" role="status">
          <strong>{harnessProgress}</strong>
          <span>{"Mentor \u6b63\u5728\u6cbf\u5df2\u786e\u8ba4\u8303\u56f4\u7ee7\u7eed\u63a8\u8fdb\u3002"}</span>
        </div>
      ) : null}
      {governanceError ? (
        <div className="recovery-banner" role="alert">
          <strong>{"Harness \u6682\u505c"}</strong>
          <span>{governanceError}</span>
          <Button onClick={onOpenGovernance}>{text.viewGovernance}</Button>
        </div>
      ) : null}
      {governanceReport?.decision === "WARN" ? (
        <div className="workbench-governance-card">
          <GovernanceDecision
            approved={approvalGranted}
            pendingAction={approvalAction}
            report={governanceReport}
            onAllowOnce={onAllowGovernance}
            onDeny={onDenyGovernance}
          />
          <Button variant="link" onClick={onOpenGovernance}>
            {text.viewGovernance}
          </Button>
        </div>
      ) : null}
      {governanceReport?.decision === "BLOCK" ? (
        <div className="workbench-governance-card block">
          <GovernanceDecision report={governanceReport} />
          <Button variant="link" onClick={onOpenGovernance}>
            {text.viewGovernance}
          </Button>
        </div>
      ) : null}
      <TaskTabs active={activeTab} onChange={openTab} />
      {activeTab === "conversation" ? (
        <Conversation
          confirmDisabled={!proposalCanConfirm || pendingAction !== null}
          confirmLabel={pendingAction === "confirm" ? text.confirming : text.confirm}
          task={taskForConversation}
          onAdjustProposal={focusComposer}
          onConfirmProposal={() => void onConfirm()}
          onTimelineAction={(target) => {
            if (target === "governance") {
              onOpenGovernance?.();
              return;
            }
            openTab(target);
          }}
        />
      ) : null}
      <ChangesPanel
        active={activeTab === "changes"}
        changes={changes}
        error={changesError}
        hasLoaded={changesHasLoaded}
        loading={changesLoading}
        taskStatus={task.status}
      />
      <ChecksPanel active={activeTab === "checks"} task={taskForConversation} />
      <div className="composer-wrap show">
        <form className="composer" onSubmit={submitComposer}>
          <label className="sr-only" htmlFor="proposal-adjustment">
            {text.adjustment}
          </label>
          <textarea
            aria-label={text.adjustment}
            disabled={busy || analyzing}
            id="proposal-adjustment"
            ref={composerRef}
            placeholder={
              analyzing
                ? text.analyzingPlaceholder
                : proposalFailed
                  ? text.retryPlaceholder
              : hasProposal && proposal.missingInformationQuestion
                    ? text.answerPlaceholder
                    : text.adjustmentPlaceholder
            }
            value={composerText}
            onChange={(event) => setComposerText(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="composer-bottom">
            <span className="ghost">{hasProposal ? text.confirmHint : text.confirmUnavailable}</span>
            <div className="composer-actions">
              <Button disabled={busy || (!proposalFailed && (!composerText.trim() || !hasProposal))} type="submit">
                {proposalFailed ? text.regenerate : hasProposal && proposal.missingInformationQuestion ? text.submitAnswer : text.adjustment}
              </Button>
            </div>
          </div>
        </form>
      </div>
    </section>
  );
}

export type ProposalDisplayState = "AWAITING_CONFIRMATION" | "SCOPE_CONFIRMED" | "PROPOSAL_FAILED" | "ANALYZING" | "LOADING";

export function deriveProposalDisplayState({
  hasProposal,
  proposalConfirmed,
  proposalFailed,
  proposalState,
}: {
  hasProposal: boolean;
  proposalConfirmed: boolean;
  proposalFailed: boolean;
  proposalState: "LOADING" | "NOT_CREATED" | "EXISTS";
}): ProposalDisplayState {
  if (hasProposal) {
    return proposalConfirmed ? "SCOPE_CONFIRMED" : "AWAITING_CONFIRMATION";
  }
  if (proposalFailed) {
    return "PROPOSAL_FAILED";
  }
  if (proposalState === "LOADING") {
    return "LOADING";
  }
  return "ANALYZING";
}

function stageLabel(stage: ProposalDisplayState) {
  switch (stage) {
    case "AWAITING_CONFIRMATION":
      return "\u65b9\u6848\u5f85\u786e\u8ba4";
    case "SCOPE_CONFIRMED":
      return "\u8303\u56f4\u5df2\u786e\u8ba4";
    case "PROPOSAL_FAILED":
      return text.failed;
    case "LOADING":
      return text.loadingTitle;
    case "ANALYZING":
      return "\u6b63\u5728\u751f\u6210\u65b9\u6848";
  }
}

function EmptyWorkbench({
  alert = false,
  body,
  title,
}: {
  alert?: boolean;
  body: string;
  title: string;
}) {
  return (
    <section className="view active workbench" aria-label={text.workbench}>
      <div className="empty-workbench" role={alert ? "alert" : undefined}>
        <EmptyState title={title} body={body} />
      </div>
    </section>
  );
}
