import { useState } from "react";

import type { Proposal, Task } from "../api/mentorApi";
import { taskStateLabel } from "../api/mentorApi";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { ChangesPanel } from "../components/workbench/ChangesPanel";
import { ChecksPanel } from "../components/workbench/ChecksPanel";
import { Conversation } from "../components/workbench/Conversation";
import { TaskTabs } from "../components/workbench/TaskTabs";
import type { MessageFixture, TaskTab } from "../app/fixtures";

interface ProposalReviewPageProps {
  error: string | null;
  loading: boolean;
  onAdjust: (instruction: string) => Promise<void>;
  onCancel: () => Promise<void>;
  onConfirm: () => Promise<void>;
  onNeedAnswer: (answer: string) => Promise<void>;
  pendingAction: string | null;
  proposal: Proposal | null;
  task: Task | null;
}

export function ProposalReviewPage({
  error,
  loading,
  onAdjust,
  onCancel,
  onConfirm,
  onNeedAnswer,
  pendingAction,
  proposal,
  task,
}: ProposalReviewPageProps) {
  const [activeTab, setActiveTab] = useState<TaskTab>("conversation");
  const [composerText, setComposerText] = useState("");

  if (loading) {
    return <EmptyWorkbench title="正在读取任务" body="Mentor 正在从后端获取任务和方案。" />;
  }
  if (error) {
    return <EmptyWorkbench title="任务没有更新" body={`${error}。请重新加载最新方案。`} alert />;
  }
  if (!task) {
    return <EmptyWorkbench title="还没有打开任务" body="从任务列表选择一个任务，或新建任务。" />;
  }

  const messages: MessageFixture[] = [
    { id: "user-request", author: "user", body: task.request, time: "刚刚" },
    {
      id: "mentor-proposal",
      author: "mentor",
      body: proposal?.missingInformationQuestion ? "我还需要你补充一个问题。" : "我先把这次修改范围整理给你确认。",
      time: "刚刚",
    },
  ];

  const taskForConversation = {
    title: task.request,
    status: taskStateLabel(task.status),
    messages,
    proposal: {
      files: proposal?.impact ?? "待分析",
      goal: proposal?.goal ?? "等待方案",
      items: proposal?.items ?? ["等待 Mentor 生成方案"],
      risk: proposal?.risk ?? "需先分析治理，不会立即修改",
    },
    changes: [],
    checks: [
      { label: "需求是否满足", state: "等待", tone: "neutral" as const },
      { label: "相关测试", state: "T096/T097 接入", tone: "neutral" as const },
      { label: "修改是否超出范围", state: "待治理", tone: "neutral" as const },
      { label: "是否还有待处理确认", state: proposal?.missingInformationQuestion ? "需要补充" : "需要确认", tone: "warn" as const },
    ],
  };

  const submitComposer = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = composerText.trim();
    if (!text || pendingAction !== null) {
      return;
    }
    if (proposal?.missingInformationQuestion) {
      await onNeedAnswer(text);
    } else {
      await onAdjust(text);
    }
    setComposerText("");
  };

  return (
    <section className="view active workbench" aria-label="工作台">
      <header className="task-head">
        <div className="task-name-wrap">
          <div className="task-state">{taskStateLabel(task.status)}</div>
          <h1 className="task-name">{task.request}</h1>
        </div>
        <div className="task-head-actions">
          <Button variant="danger" disabled={pendingAction !== null || !proposal} onClick={onCancel}>
            停止任务
          </Button>
        </div>
      </header>
      {proposal?.missingInformationQuestion ? (
        <div className="recovery-banner" role="status">
          <strong>需要你补充</strong>
          <span>{proposal.missingInformationQuestion}</span>
        </div>
      ) : null}
      <TaskTabs active={activeTab} onChange={setActiveTab} />
      {activeTab === "conversation" ? <Conversation task={taskForConversation} /> : null}
      <ChangesPanel active={activeTab === "changes"} task={taskForConversation} />
      <ChecksPanel active={activeTab === "checks"} task={taskForConversation} />
      <ProposalActions
        hasProposal={proposal !== null}
        pendingAction={pendingAction}
        onConfirm={onConfirm}
      />
      <div className="composer-wrap show">
        <form className="composer" onSubmit={submitComposer}>
          <label className="sr-only" htmlFor="proposal-adjustment">
            {proposal?.missingInformationQuestion ? "补充信息" : "调整方案"}
          </label>
          <textarea
            aria-label={proposal?.missingInformationQuestion ? "补充信息" : "调整方案"}
            disabled={pendingAction !== null || !proposal}
            id="proposal-adjustment"
            placeholder={proposal?.missingInformationQuestion ? "回答 Mentor 的问题..." : "告诉 Mentor 你想怎么调整方案..."}
            value={composerText}
            onChange={(event) => setComposerText(event.currentTarget.value)}
          />
          <div className="composer-bottom">
            <span className="ghost">确认后 Mentor 才会开始修改</span>
            <Button variant="dark" disabled={!composerText.trim() || pendingAction !== null || !proposal} type="submit">
              {proposal?.missingInformationQuestion ? "提交补充" : "调整方案"}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}

function ProposalActions({
  hasProposal,
  onConfirm,
  pendingAction,
}: {
  hasProposal: boolean;
  onConfirm: () => Promise<void>;
  pendingAction: string | null;
}) {
  return (
    <div className="proposal-floating-actions">
      <Button variant="dark" disabled={!hasProposal || pendingAction !== null} onClick={onConfirm}>
        {pendingAction === "confirm" ? "确认中" : "确认并继续"}
      </Button>
    </div>
  );
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
    <section className="view active workbench" aria-label="工作台">
      <div className="empty-workbench" role={alert ? "alert" : undefined}>
        <EmptyState title={title} body={body} />
      </div>
    </section>
  );
}
