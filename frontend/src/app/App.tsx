import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createMentorApi,
  type CompletionGate,
  type DiffTrace,
  type GovernanceReport,
  type LockStatus,
  type Project,
  type Proposal,
  type RecoveryItem,
  type Task,
  type TaskEvent,
  type ValidationResult,
} from "../api/mentorApi";
import { cards, type NavKey } from "./fixtures";
import { AppShell } from "./AppShell";
import { Button } from "../components/Button";
import { Drawer } from "../components/Drawer";
import { EmptyState } from "../components/EmptyState";
import { Modal } from "../components/Modal";
import { StatusBadge } from "../components/StatusBadge";
import { NewTaskPage } from "../pages/NewTaskPage";
import { AnalysisPage } from "../pages/AnalysisPage";
import { ExecutionPage } from "../pages/ExecutionPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { ProposalReviewPage } from "../pages/ProposalReviewPage";
import { RecoveryPage } from "../pages/RecoveryPage";
import { TaskResultPage } from "../pages/TaskResultPage";
import { useTaskEvents } from "../hooks/useTaskEvents";

interface AppProps {
  api?: ReturnType<typeof createMentorApi>;
}

export function App({ api: providedApi }: AppProps = {}) {
  const defaultApi = useMemo(() => createMentorApi(), []);
  const api = providedApi ?? defaultApi;
  const [activeView, setActiveView] = useState<NavKey>("workbench");
  const [project, setProject] = useState<Project | null>(null);
  const [lockStatus, setLockStatus] = useState<LockStatus | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [activeProposal, setActiveProposal] = useState<Proposal | null>(null);
  const [taskListLoading, setTaskListLoading] = useState(false);
  const [taskDetailLoading, setTaskDetailLoading] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [newTaskPending, setNewTaskPending] = useState(false);
  const [proposalAction, setProposalAction] = useState<string | null>(null);
  const [governanceReport, setGovernanceReport] = useState<GovernanceReport | null>(null);
  const [governanceLoading, setGovernanceLoading] = useState(false);
  const [governanceError, setGovernanceError] = useState<string | null>(null);
  const [approvalAction, setApprovalAction] = useState<string | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [cancelPending, setCancelPending] = useState(false);
  const [activeExecutions, setActiveExecutions] = useState<Record<string, TaskEvent[]>>({});
  const [diffTrace, setDiffTrace] = useState<DiffTrace | null>(null);
  const [validationResults, setValidationResults] = useState<ValidationResult[]>([]);
  const [completionGate, setCompletionGate] = useState<CompletionGate[]>([]);
  const [recoveryItems, setRecoveryItems] = useState<RecoveryItem[]>([]);
  const [recoveryPendingTaskId, setRecoveryPendingTaskId] = useState<string | null>(null);
  const governanceRequestRef = useRef(0);
  const taskEvents = useTaskEvents(api, activeTask?.id ?? null);
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const loadTaskList = useCallback(
    async (projectId: string) => {
      setTaskListLoading(true);
      setProjectError(null);
      try {
        const [list, locks] = await Promise.all([
          api.getTaskList(projectId),
          api.getProjectLocks(projectId),
        ]);
        setTasks(list.items);
        setLockStatus(locks);
      } catch (error) {
        setProjectError(userError(error));
      } finally {
        setTaskListLoading(false);
      }
    },
    [api],
  );

  const openProject = useCallback(async (rootPath: string) => {
    if (!rootPath.trim()) {
      setProjectError("project rootPath is required");
      return;
    }
    setProjectError(null);
    try {
      const opened = await api.createProject(rootPath);
      setProject(opened);
      await api.getProjectConfig(opened.id);
      await loadTaskList(opened.id);
    } catch (error) {
      setProjectError(userError(error));
    }
  }, [api, loadTaskList]);

  const openTask = useCallback(
    async (taskId: string) => {
      setTaskDetailLoading(true);
      setTaskError(null);
      setActiveView("workbench");
      try {
        const [task, proposal] = await Promise.all([
          api.getTask(taskId),
          api.getProposal(taskId).catch(() => null),
        ]);
        setActiveTask(task);
        setActiveProposal(proposal);
      } catch (error) {
        setTaskError(userError(error));
      } finally {
        setTaskDetailLoading(false);
      }
    },
    [api],
  );

  const createTask = useCallback(
    async (request: string) => {
      if (!project || newTaskPending) {
        return;
      }
      setNewTaskPending(true);
      setTaskError(null);
      try {
        const task = await api.createTask(project.id, request);
        const question = request.includes("?") || request.includes("？")
          ? "请补充你希望优先处理的目标。"
          : undefined;
        const proposal = await api.createProposal(task.id, request, question);
        setActiveTask(await api.getTask(task.id));
        setActiveProposal(proposal);
        await loadTaskList(project.id);
        setActiveView("workbench");
      } catch (error) {
        setTaskError(userError(error));
      } finally {
        setNewTaskPending(false);
      }
    },
    [api, loadTaskList, newTaskPending, project],
  );

  const refreshActiveTask = useCallback(async () => {
    if (!activeTask) {
      return;
    }
    const [task, proposal] = await Promise.all([
      api.getTask(activeTask.id),
      api.getProposal(activeTask.id).catch(() => null),
    ]);
    setActiveTask(task);
    setActiveProposal(proposal);
    if (project) {
      await loadTaskList(project.id);
    }
  }, [activeTask, api, loadTaskList, project]);

  const confirmProposal = useCallback(async () => {
    if (!activeTask || !activeProposal || proposalAction !== null) {
      return;
    }
    setProposalAction("confirm");
    try {
      await api.confirmProposal(activeTask.id, activeProposal.id);
      await refreshActiveTask();
    } catch (error) {
      setTaskError(userError(error));
    } finally {
      setProposalAction(null);
    }
  }, [activeProposal, activeTask, api, proposalAction, refreshActiveTask]);

  const adjustProposal = useCallback(
    async (instruction: string) => {
      if (!activeTask || !activeProposal || proposalAction !== null) {
        return;
      }
      setProposalAction("adjust");
      try {
        const proposal = await api.adjustProposal(activeTask.id, activeProposal.id, instruction);
        setActiveProposal(proposal);
        await refreshActiveTask();
      } catch (error) {
        setTaskError(userError(error));
      } finally {
        setProposalAction(null);
      }
    },
    [activeProposal, activeTask, api, proposalAction, refreshActiveTask],
  );

  const cancelProposal = useCallback(async () => {
    if (!activeTask || !activeProposal || proposalAction !== null) {
      return;
    }
    setProposalAction("cancel");
    try {
      await api.cancelProposal(activeTask.id, activeProposal.id);
      await refreshActiveTask();
      setModalOpen(true);
    } catch (error) {
      setTaskError(userError(error));
    } finally {
      setProposalAction(null);
    }
  }, [activeProposal, activeTask, api, proposalAction, refreshActiveTask]);

  const startNewTask = () => {
    setTaskError(null);
    setActiveTask(null);
    setActiveProposal(null);
    setActiveView("workbench");
  };

  const loadGovernance = useCallback(async () => {
    if (!activeProposal || activeProposal.status !== "CONFIRMED") {
      setGovernanceReport(null);
      setGovernanceError(null);
      return;
    }
    const requestId = governanceRequestRef.current + 1;
    governanceRequestRef.current = requestId;
    setGovernanceLoading(true);
    setGovernanceError(null);
    try {
      await api.indexAnalysis();
      const report = await api.runGovernance(activeProposal.id, activeProposal.items);
      if (governanceRequestRef.current === requestId) {
        setGovernanceReport(report);
      }
    } catch (error) {
      if (governanceRequestRef.current === requestId) {
        setGovernanceError(userError(error));
        setGovernanceReport(null);
      }
    } finally {
      if (governanceRequestRef.current === requestId) {
        setGovernanceLoading(false);
      }
    }
  }, [activeProposal, api]);

  useEffect(() => {
    if (activeView === "governance") {
      void loadGovernance();
    }
  }, [activeView, loadGovernance]);

  useEffect(() => {
    if (!activeTask) {
      return;
    }
    setActiveExecutions((current) => ({
      ...current,
      [activeTask.id]: taskEvents.events,
    }));
  }, [activeTask, taskEvents.events]);

  const executeTask = useCallback(async () => {
    if (!activeTask) {
      return;
    }
    await api.executeTask(activeTask.id, "RUN_COMMAND");
    await refreshActiveTask();
    await taskEvents.reconnect();
    setActiveView("workbench");
  }, [activeTask, api, refreshActiveTask, taskEvents]);

  const approveGovernance = useCallback(async () => {
    if (!activeTask || !activeProposal || !governanceReport || approvalAction !== null) {
      return;
    }
    setApprovalAction("allow");
    setExecutionError(null);
    try {
      const approval = await api.approveRequest(activeProposal.id, governanceReport.impactScope.files);
      if (!approval.temporaryGrant || !approval.executionPolicy) {
        throw new Error("授权没有完成");
      }
      await executeTask();
    } catch (error) {
      setExecutionError(userError(error));
    } finally {
      setApprovalAction(null);
    }
  }, [activeProposal, activeTask, api, approvalAction, executeTask, governanceReport]);

  const denyGovernance = useCallback(async () => {
    if (!activeProposal || approvalAction !== null) {
      return;
    }
    setApprovalAction("deny");
    try {
      await api.rejectApproval(activeProposal.id);
      setGovernanceError("本次授权没有通过");
    } catch (error) {
      setGovernanceError(userError(error));
    } finally {
      setApprovalAction(null);
    }
  }, [activeProposal, api, approvalAction]);

  const cancelExecution = useCallback(async () => {
    if (!activeTask || cancelPending) {
      return;
    }
    setCancelPending(true);
    setExecutionError(null);
    try {
      await api.cancelTask(activeTask.id);
      await refreshActiveTask();
      await taskEvents.reconnect();
    } catch (error) {
      setExecutionError(userError(error));
    } finally {
      setCancelPending(false);
    }
  }, [activeTask, api, cancelPending, refreshActiveTask, taskEvents]);

  const loadResultState = useCallback(async () => {
    if (!activeTask) {
      setDiffTrace(null);
      setValidationResults([]);
      setCompletionGate([]);
      setRecoveryItems([]);
      return;
    }
    const latestDiffChangeId = latestEventValue(
      activeExecutions[activeTask.id] ?? taskEvents.events,
      "changeId",
    );
    const [recovery, trace] = await Promise.all([
      api.listRecovery(),
      latestDiffChangeId ? api.getDiffTrace(latestDiffChangeId).catch(() => null) : null,
    ]);
    const events = activeExecutions[activeTask.id] ?? taskEvents.events;
    setDiffTrace(trace);
    setRecoveryItems(recovery.items);
    setValidationResults(validationResultsFromEvents(events));
    setCompletionGate(completionGateFromEvents(events));
  }, [activeExecutions, activeTask, api, taskEvents.events]);

  useEffect(() => {
    if (activeView === "evaluation") {
      void loadResultState();
    }
  }, [activeView, loadResultState]);

  const resolveRecovery = useCallback(
    async (taskId: string, action: "keep" | "rollback") => {
      setRecoveryPendingTaskId(taskId);
      try {
        await api.resolveRecovery(taskId, action);
        await loadResultState();
      } catch (error) {
        setTaskError(userError(error));
      } finally {
        setRecoveryPendingTaskId(null);
      }
    },
    [api, loadResultState],
  );

  return (
    <AppShell
      activeView={activeView}
      project={project}
      onNewTask={startNewTask}
      onOpenProject={(rootPath) => void openProject(rootPath)}
      onViewChange={setActiveView}
    >
      {activeView === "workbench" ? (
        activeTask?.status === "EXECUTING" || activeTask?.status === "CANCEL_REQUESTED" ? (
          <ExecutionPage
            cancelPending={cancelPending}
            error={executionError}
            events={activeExecutions[activeTask.id] ?? []}
            reconnecting={taskEvents.reconnecting}
            task={activeTask}
            onCancel={cancelExecution}
            onReconnect={taskEvents.reconnect}
          />
        ) : activeTask ? (
          <ProposalReviewPage
            error={taskError}
            loading={taskDetailLoading}
            pendingAction={proposalAction}
            proposal={activeProposal}
            task={activeTask}
            onAdjust={adjustProposal}
            onCancel={cancelProposal}
            onConfirm={confirmProposal}
            onNeedAnswer={adjustProposal}
          />
        ) : (
          <NewTaskPage
            disabled={!project}
            error={taskError}
            pending={newTaskPending}
            onSubmit={createTask}
          />
        )
      ) : null}
      {activeView === "tasks" ? (
        <ProjectsPage
          error={projectError}
          loading={taskListLoading}
          lockStatus={lockStatus}
          project={project}
          tasks={tasks}
          onOpenTask={(taskId) => void openTask(taskId)}
          onStartNewTask={startNewTask}
        />
      ) : null}
      {activeView === "memory" ? <MemoryView onOpenDrawer={() => setDrawerOpen(true)} /> : null}
      {activeView === "governance" ? (
        <AnalysisPage
          error={governanceError}
          loading={governanceLoading}
          pendingAction={approvalAction}
          report={governanceReport}
          onAllowOnce={approveGovernance}
          onDeny={denyGovernance}
          onReload={() => void loadGovernance()}
        />
      ) : null}
      {activeView === "evaluation" ? (
        recoveryItems.length > 0 ? (
          <RecoveryPage
            items={recoveryItems}
            pendingTaskId={recoveryPendingTaskId}
            onKeep={(taskId) => resolveRecovery(taskId, "keep")}
            onRollback={(taskId) => resolveRecovery(taskId, "rollback")}
          />
        ) : (
          <TaskResultPage
            completionGate={completionGate}
            diffTrace={diffTrace}
            task={activeTask}
            validationResults={validationResults}
          />
        )
      ) : null}
      {activeView === "settings" ? <SettingsView project={project} /> : null}
      <Modal open={modalOpen} title="任务已停止" onClose={() => setModalOpen(false)}>
        提案已停止。后续执行、安全点和回滚流程将在后续任务接入。
      </Modal>
      <Drawer open={drawerOpen} title="项目经验" onClose={() => setDrawerOpen(false)}>
        <div className="detail-section">
          <div className="detail-label">内容</div>
          <div className="detail-text">用户模块字段变化需要同步 schema、service 与相关测试。</div>
        </div>
      </Drawer>
      <div className="toast" role="status" aria-live="polite">
        当前为本地演示数据
      </div>
    </AppShell>
  );
}

function MemoryView({ onOpenDrawer }: { onOpenDrawer: () => void }) {
  return (
    <Page title="记忆">
      <div className="memory-tools">
        <button className="filter active" type="button">
          全部
        </button>
        <button className="filter" type="button">
          已验证
        </button>
        <button className="filter" type="button">
          待复核
        </button>
      </div>
      <div className="memory-list">
        {cards.memory.map(([title, text, state]) => (
          <button className="memory-card" key={title} type="button" onClick={onOpenDrawer}>
            <span className="memory-icon" aria-hidden="true">
              M
            </span>
            <span>
              <span className="memory-title">{title}</span>
              <span className="memory-text">{text}</span>
              <span className="memory-meta">
                <span className="memory-tag ok">{state}</span>
                <span>来源：最近任务</span>
              </span>
            </span>
            <span className="memory-date">今天</span>
          </button>
        ))}
      </div>
    </Page>
  );
}

function userError(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "请求没有完成";
}

function SettingsView({ project }: { project: Project | null }) {
  const projectPath = project?.rootPath ?? "No local project opened";
  return (
    <Page title="设置">
      <div className="settings-grid">
        <section className="setting-card">
          <div className="setting-head">
            <div className="setting-title">模型与凭据</div>
            <StatusBadge tone="allow">已配置</StatusBadge>
          </div>
          <div className="setting-row">
            <div className="setting-label">OpenAI</div>
            <div className="setting-value">
              凭据已配置
              <span className="setting-sub">Windows 凭据管理器</span>
            </div>
            <div className="page-actions">
              <Button size="small">更新</Button>
              <Button size="small" variant="danger">
                删除
              </Button>
            </div>
          </div>
        </section>
        <EmptyState title="本地项目" body={`当前目录：${projectPath}`} />
      </div>
    </Page>
  );
}

function latestEventValue(events: TaskEvent[], key: string): string | null {
  for (const event of [...events].reverse()) {
    const value = event.payload[key as keyof TaskEvent["payload"]];
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
  }
  return null;
}

function validationResultsFromEvents(events: TaskEvent[]): ValidationResult[] {
  return events.flatMap((event) => {
    const value = event.payload.validation;
    return Array.isArray(value) ? (value as ValidationResult[]) : [];
  });
}

function completionGateFromEvents(events: TaskEvent[]): CompletionGate[] {
  const latest = [...events].reverse().find((event) => Array.isArray(event.payload.completionGate));
  if (!latest || !Array.isArray(latest.payload.completionGate)) {
    return [];
  }
  return latest.payload.completionGate as CompletionGate[];
}

function Page({
  action,
  children,
  title,
}: {
  action?: string;
  children: React.ReactNode;
  title: string;
}) {
  return (
    <section className="view active">
      <div className="page">
        <div className="page-head">
          <h1 className="page-title">{title}</h1>
          {action ? (
            <div className="page-actions">
              <Button>{action}</Button>
            </div>
          ) : null}
        </div>
        {children}
      </div>
    </section>
  );
}
