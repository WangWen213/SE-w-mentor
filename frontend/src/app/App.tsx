import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  createMentorApi,
  type CompletionGate,
  type CredentialStatus,
  type DiffTrace,
  type GovernanceReport,
  type KnowledgeItem,
  type LockStatus,
  type Project,
  type Proposal,
  type RecoveryItem,
  type Task,
  type ValidationResult,
  type WorkbenchMessageRecord,
} from "../api/mentorApi";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { AnalysisPage } from "../pages/AnalysisPage";
import { ExecutionPage } from "../pages/ExecutionPage";
import { NewTaskPage, type NewTaskStage } from "../pages/NewTaskPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { ProposalReviewPage } from "../pages/ProposalReviewPage";
import { RecoveryPage } from "../pages/RecoveryPage";
import { TaskResultPage } from "../pages/TaskResultPage";
import { useTaskEvents } from "../hooks/useTaskEvents";
import { AppShell } from "./AppShell";
import type { NavKey, ProposalFixture, WorkbenchMessage } from "./fixtures";

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
  const [projectOpening, setProjectOpening] = useState(false);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [taskErrorTitle, setTaskErrorTitle] = useState<string | null>(null);
  const [persistedWorkbenchMessagesByTask, setPersistedWorkbenchMessagesByTask] = useState<Record<string, WorkbenchMessage[]>>({});
  const [optimisticWorkbenchMessagesByTask, setOptimisticWorkbenchMessagesByTask] = useState<Record<string, WorkbenchMessage[]>>({});
  const [newTaskPending, setNewTaskPending] = useState(false);
  const [newTaskStage, setNewTaskStage] = useState<NewTaskStage>("IDLE");
  const [proposalAction, setProposalAction] = useState<string | null>(null);
  const [governanceReport, setGovernanceReport] = useState<GovernanceReport | null>(null);
  const [governanceLoading, setGovernanceLoading] = useState(false);
  const [governanceError, setGovernanceError] = useState<string | null>(null);
  const [governanceState, setGovernanceState] = useState<"LOADING" | "READY" | "NOT_GENERATED" | "ERROR">("NOT_GENERATED");
  const [harnessProgress, setHarnessProgress] = useState<string | null>(null);
  const [approvalAction, setApprovalAction] = useState<string | null>(null);
  const [approvalGranted, setApprovalGranted] = useState(false);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [cancelPending, setCancelPending] = useState(false);
  const [diffTrace] = useState<DiffTrace | null>(null);
  const [validationResults] = useState<ValidationResult[]>([]);
  const [completionGate] = useState<CompletionGate[]>([]);
  const [taskEvaluation] = useState(null);
  const [evaluationError] = useState<string | null>(null);
  const [recoveryItems, setRecoveryItems] = useState<RecoveryItem[]>([]);
  const [recoveryPendingTaskId, setRecoveryPendingTaskId] = useState<string | null>(null);
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);
  const [knowledgeError, setKnowledgeError] = useState<string | null>(null);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [credentialStatus, setCredentialStatus] = useState<CredentialStatus | null>(null);
  const [credentialPending, setCredentialPending] = useState<string | null>(null);
  const [credentialError, setCredentialError] = useState<string | null>(null);
  const taskEvents = useTaskEvents(api, activeTask?.id ?? null);

  const loadWorkbenchMessages = useCallback(
    async (taskId: string) => {
      const timeline = await api.getWorkbenchMessages(taskId);
      const persistedMessages = timeline.items.map(workbenchMessageFromRecord);
      setPersistedWorkbenchMessagesByTask((current) => ({
        ...current,
        [taskId]: persistedMessages,
      }));
      setOptimisticWorkbenchMessagesByTask((current) => ({
        ...current,
        [taskId]: reconcileOptimisticMessages(current[taskId] ?? [], persistedMessages),
      }));
    },
    [api],
  );

  const appendWorkbenchMessage = useCallback((taskId: string, message: Omit<WorkbenchMessage, "createdAt" | "id" | "taskId">) => {
    const id = `${taskId}:${message.role}:${message.kind}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
    setOptimisticWorkbenchMessagesByTask((current) => ({
      ...current,
      [taskId]: [
        ...(current[taskId] ?? []),
        {
          ...message,
          createdAt: "now",
          id,
          taskId,
        },
      ],
    }));
    return id;
  }, []);

  const updateWorkbenchMessage = useCallback(
    (taskId: string, messageId: string, patch: Partial<Omit<WorkbenchMessage, "id" | "taskId">>) => {
      setOptimisticWorkbenchMessagesByTask((current) => ({
        ...current,
        [taskId]: (current[taskId] ?? []).map((message) =>
          message.id === messageId ? { ...message, ...patch } : message,
        ),
      }));
    },
    [],
  );

  const loadCredentialStatus = useCallback(async () => {
    setCredentialError(null);
    try {
      setCredentialStatus(await api.getCredentialStatus());
    } catch (error) {
      setCredentialError(userError(error));
    }
  }, [api]);

  useEffect(() => {
    void loadCredentialStatus();
  }, [loadCredentialStatus]);

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

  const openProject = useCallback(async () => {
    if (projectOpening) {
      return;
    }
    setProjectOpening(true);
    setProjectError(null);
    try {
      const opened = await api.chooseLocalProject();
      setProject(opened);
      await api.getProjectConfig(opened.id);
      await loadTaskList(opened.id);
      setActiveTask(null);
      setActiveProposal(null);
      setActiveView("workbench");
    } catch (error) {
      setProjectError(userError(error));
    } finally {
      setProjectOpening(false);
    }
  }, [api, loadTaskList, projectOpening]);

  const openTask = useCallback(
    async (taskId: string) => {
      setTaskDetailLoading(true);
      setTaskError(null);
      setTaskErrorTitle(null);
      setActiveView("workbench");
      try {
        const [task, proposal] = await Promise.all([
          api.getTask(taskId),
          api.getProposal(taskId).catch(() => null),
        ]);
        setActiveTask(task);
        setActiveProposal(proposal);
        await loadWorkbenchMessages(task.id);
        setApprovalGranted(false);
      } catch (error) {
        setTaskError(userError(error));
      } finally {
        setTaskDetailLoading(false);
      }
    },
    [api, loadWorkbenchMessages],
  );

  const createTask = useCallback(
    async (request: string) => {
      if (!project || newTaskPending) {
        return;
      }
      setNewTaskPending(true);
      setTaskError(null);
      setTaskErrorTitle(null);
      setNewTaskStage("TASK_CREATING");
      try {
        const task = await api.createTask(project.id, request);
        setNewTaskStage("PROPOSAL_GENERATING");
        setActiveTask(task);
        setActiveProposal(null);
        await loadWorkbenchMessages(task.id);
        setGovernanceReport(null);
        setGovernanceError(null);
        setHarnessProgress(null);
        void loadTaskList(project.id);
        const progressId = appendWorkbenchMessage(task.id, {
          kind: "PROGRESS",
          role: "MENTOR",
          status: "PENDING",
          text: "Mentor 正在生成方案",
        });
        const question = request.includes("?") || request.includes("？")
          ? "请补充你希望优先处理的目标。"
          : undefined;
        const proposal = await api.createProposal(task.id, request, question);
        setActiveTask(await api.getTask(task.id));
        setActiveProposal(proposal);
        updateWorkbenchMessage(task.id, progressId, {
          kind: "PROPOSAL",
          proposal: proposalToFixture(proposal, false),
          status: "DONE",
          text: `这是我的修改方案：Proposal v${proposal.version}`,
        });
        setNewTaskStage("PROPOSAL_READY");
        void loadWorkbenchMessages(task.id);
        void loadTaskList(project.id);
      } catch (error) {
        setTaskErrorTitle("任务已创建，但暂时无法生成修改方案");
        setTaskError(userError(error));
        setNewTaskStage("PROPOSAL_FAILED");
        throw error;
      } finally {
        setNewTaskPending(false);
      }
    },
    [api, appendWorkbenchMessage, loadTaskList, loadWorkbenchMessages, newTaskPending, project, updateWorkbenchMessage],
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
  }, [activeTask, api]);

  const confirmProposal = useCallback(async () => {
    if (!activeTask || !activeProposal || proposalAction !== null) {
      return;
    }
    setProposalAction("confirm");
    try {
      await api.confirmProposal(activeTask.id, activeProposal.id);
      await refreshActiveTask();
      setHarnessProgress("正在分析影响");
    } catch (error) {
      setTaskError(userError(error));
    } finally {
      setProposalAction(null);
    }
  }, [activeProposal, activeTask, api, proposalAction, refreshActiveTask]);

  const submitMentorTurn = useCallback(
    async (text: string) => {
      if (!activeTask || proposalAction !== null) {
        return;
      }
      appendWorkbenchMessage(activeTask.id, {
        kind: "TEXT",
        role: "USER",
        status: "DONE",
        text,
      });
      const progressId = appendWorkbenchMessage(activeTask.id, {
        kind: "PROGRESS",
        role: "MENTOR",
        status: "PENDING",
        text: "Mentor 正在分析",
      });
      try {
        const result = await api.createMentorTurn(activeTask.id, text);
        if (result.proposal) {
          setActiveProposal(result.proposal);
        }
        updateWorkbenchMessage(activeTask.id, progressId, result.message
          ? workbenchMessageFromRecord(result.message)
          : { kind: "TEXT", role: "MENTOR", status: "DONE", text: "已完成。" });
        void loadWorkbenchMessages(activeTask.id);
      } catch (error) {
        updateWorkbenchMessage(activeTask.id, progressId, {
          kind: "ERROR",
          role: "MENTOR",
          status: "ERROR",
          text: userError(error),
        });
      }
    },
    [activeTask, api, appendWorkbenchMessage, loadWorkbenchMessages, proposalAction, updateWorkbenchMessage],
  );

  const retryProposal = useCallback(async () => {
    if (!activeTask) {
      return;
    }
    setNewTaskPending(true);
    setNewTaskStage("PROPOSAL_GENERATING");
    const progressId = appendWorkbenchMessage(activeTask.id, {
      kind: "PROGRESS",
      role: "MENTOR",
      status: "PENDING",
      text: "Mentor 正在重新生成方案",
    });
    try {
      const proposal = await api.createProposal(activeTask.id, activeTask.request);
      setActiveProposal(proposal);
      updateWorkbenchMessage(activeTask.id, progressId, {
        kind: "PROPOSAL",
        proposal: proposalToFixture(proposal, false),
        status: "DONE",
        text: `这是我的修改方案：Proposal v${proposal.version}`,
      });
      setNewTaskStage("PROPOSAL_READY");
      void loadWorkbenchMessages(activeTask.id);
    } catch (error) {
      updateWorkbenchMessage(activeTask.id, progressId, {
        kind: "ERROR",
        role: "MENTOR",
        status: "ERROR",
        text: userError(error),
      });
      setNewTaskStage("PROPOSAL_FAILED");
    } finally {
      setNewTaskPending(false);
    }
  }, [activeTask, api, appendWorkbenchMessage, loadWorkbenchMessages, updateWorkbenchMessage]);

  const loadGovernance = useCallback(async () => {
    if (!activeProposal || activeProposal.status !== "CONFIRMED") {
      setGovernanceReport(null);
      setGovernanceState("NOT_GENERATED");
      return;
    }
    setGovernanceLoading(true);
    setGovernanceState("LOADING");
    setGovernanceError(null);
    try {
      const report = await api.runGovernance(activeProposal.id, activeProposal.items);
      setGovernanceReport(report);
      setGovernanceState("READY");
    } catch (error) {
      setGovernanceError(userError(error));
      setGovernanceState("ERROR");
    } finally {
      setGovernanceLoading(false);
    }
  }, [activeProposal, api]);

  useEffect(() => {
    if (activeView === "governance") {
      void loadGovernance();
    }
  }, [activeView, loadGovernance]);

  const approveGovernance = useCallback(async () => {
    if (!governanceReport?.approvalRequestId) {
      return;
    }
    setApprovalAction("allow");
    try {
      await api.approveRequest(governanceReport.approvalRequestId, governanceReport.impactScope.files);
      setApprovalGranted(true);
    } catch (error) {
      setExecutionError(userError(error));
    } finally {
      setApprovalAction(null);
    }
  }, [api, governanceReport]);

  const denyGovernance = useCallback(async () => {
    if (!governanceReport?.approvalRequestId) {
      return;
    }
    setApprovalAction("deny");
    try {
      await api.rejectApproval(governanceReport.approvalRequestId);
      setGovernanceError("本次授权没有通过");
    } catch (error) {
      setGovernanceError(userError(error));
    } finally {
      setApprovalAction(null);
    }
  }, [api, governanceReport]);

  const cancelExecution = useCallback(async () => {
    if (!activeTask || cancelPending) {
      return;
    }
    setCancelPending(true);
    try {
      await api.cancelTask(activeTask.id);
      await refreshActiveTask();
    } catch (error) {
      setExecutionError(userError(error));
    } finally {
      setCancelPending(false);
    }
  }, [activeTask, api, cancelPending, refreshActiveTask]);

  const resolveRecovery = useCallback(
    async (taskId: string, action: "keep" | "rollback") => {
      setRecoveryPendingTaskId(taskId);
      try {
        await api.resolveRecovery(taskId, action);
        const recovery = await api.listRecovery();
        setRecoveryItems(recovery.items);
      } catch (error) {
        setTaskError(userError(error));
      } finally {
        setRecoveryPendingTaskId(null);
      }
    },
    [api],
  );

  const loadKnowledge = useCallback(async () => {
    if (!project) {
      setKnowledgeItems([]);
      setKnowledgeError(null);
      return;
    }
    setKnowledgeLoading(true);
    setKnowledgeError(null);
    try {
      const knowledge = await api.listKnowledge(project.id);
      setKnowledgeItems(knowledge.items);
    } catch (error) {
      setKnowledgeError(userError(error));
    } finally {
      setKnowledgeLoading(false);
    }
  }, [api, project]);

  useEffect(() => {
    if (activeView === "memory") {
      void loadKnowledge();
    }
  }, [activeView, loadKnowledge]);

  const saveCredential = useCallback(
    async (key: string, baseUrl: string, model: string) => {
      setCredentialPending("save");
      setCredentialError(null);
      try {
        const status = credentialStatus?.configured
          ? await api.updateCredential("openai-compatible", key, baseUrl, model)
          : await api.setCredential("openai-compatible", key, baseUrl, model);
        setCredentialStatus(status);
      } catch (error) {
        setCredentialError(userError(error));
      } finally {
        setCredentialPending(null);
      }
    },
    [api, credentialStatus?.configured],
  );

  const clearCredential = useCallback(async () => {
    setCredentialPending("clear");
    setCredentialError(null);
    try {
      setCredentialStatus(await api.clearCredential());
    } catch (error) {
      setCredentialError(userError(error));
    } finally {
      setCredentialPending(null);
    }
  }, [api]);

  const conversationMessages = activeTask
    ? conversationMessagesForTask(
        activeTask.id,
        persistedWorkbenchMessagesByTask,
        optimisticWorkbenchMessagesByTask,
      )
    : [];
  const startNewTask = () => {
    setTaskError(null);
    setTaskErrorTitle(null);
    setActiveTask(null);
    setActiveProposal(null);
    setActiveView("workbench");
  };

  return (
    <AppShell
      activeView={activeView}
      project={project}
      projectBootstrap={project?.bootstrap ?? null}
      projectError={projectError}
      projectOpening={projectOpening}
      taskCount={tasks.length}
      onNewTask={startNewTask}
      onOpenProject={() => void openProject()}
      onViewChange={setActiveView}
    >
      {activeView === "workbench" ? (
        activeTask?.status === "EXECUTING" || activeTask?.status === "CANCEL_REQUESTED" ? (
          <ExecutionPage
            cancelPending={cancelPending}
            error={executionError}
            events={taskEvents.events}
            reconnecting={taskEvents.reconnecting}
            task={activeTask}
            onCancel={cancelExecution}
            onReconnect={taskEvents.reconnect}
          />
        ) : activeTask ? (
          <ProposalReviewPage
            approvalAction={approvalAction}
            approvalGranted={approvalGranted}
            conversationMessages={conversationMessages}
            error={taskError}
            governanceError={governanceError}
            governanceReport={governanceReport}
            harnessProgress={harnessProgress}
            loading={taskDetailLoading}
            pendingAction={proposalAction}
            proposal={activeProposal}
            stage={newTaskStage}
            task={activeTask}
            onAllowGovernance={approveGovernance}
            onCancel={async () => undefined}
            onConfirm={confirmProposal}
            onDenyGovernance={denyGovernance}
            onOpenGovernance={() => setActiveView("governance")}
            onRetryProposal={retryProposal}
            onSubmitTurn={submitMentorTurn}
          />
        ) : (
          <NewTaskPage
            disabled={!project}
            error={taskError}
            errorTitle={taskErrorTitle}
            pending={newTaskPending}
            stage={newTaskStage}
            onOpenSettings={() => setActiveView("settings")}
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
      {activeView === "memory" ? (
        <MemoryView error={knowledgeError} items={knowledgeItems} loading={knowledgeLoading} />
      ) : null}
      {activeView === "governance" ? (
        <AnalysisPage
          approved={approvalGranted}
          error={executionError ?? governanceError}
          loading={governanceLoading}
          pendingAction={approvalAction}
          report={governanceReport}
          state={governanceState}
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
            error={evaluationError}
            evaluation={taskEvaluation}
            task={activeTask}
            validationResults={validationResults}
          />
        )
      ) : null}
      {activeView === "settings" ? (
        <SettingsView
          credentialError={credentialError}
          credentialPending={credentialPending}
          credentialStatus={credentialStatus}
          project={project}
          onClearCredential={clearCredential}
          onSaveCredential={saveCredential}
        />
      ) : null}
    </AppShell>
  );
}

function MemoryView({
  error,
  items,
  loading,
}: {
  error: string | null;
  items: KnowledgeItem[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <Page title="记忆">
        <EmptyState title="正在读取真实记忆" body="正在从后端 knowledge repository 查询。" />
      </Page>
    );
  }
  return (
    <Page title="记忆">
      {error ? <EmptyState title="记忆读取失败" body={error} /> : null}
      {!error && items.length === 0 ? (
        <EmptyState
          title="还没有工程记忆"
          body="项目索引与项目认知会在打开仓库时建立；这里只显示后端 knowledge repository 中的真实记录。"
        />
      ) : null}
      {!error && items.length > 0 ? (
        <div className="memory-list">
          {items.map((item) =>
            item.presentation?.kind === "project-understanding" ? (
              <ProjectUnderstandingMemory item={item} key={item.id} />
            ) : (
              <article className="memory-item" key={item.id}>
                <div className="memory-status">{knowledgeStatusLabel(item.status)}</div>
                <h2>{item.key}</h2>
                <p>{item.summary}</p>
                <div className="memory-meta">
                  <span>{item.type}</span>
                  <span>{item.scope.join(", ") || "scope unavailable"}</span>
                </div>
              </article>
            ),
          )}
        </div>
      ) : null}
    </Page>
  );
}

function ProjectUnderstandingMemory({ item }: { item: KnowledgeItem }) {
  const presentation = item.presentation;
  if (!presentation) {
    return null;
  }
  return (
    <article className="memory-item project-understanding">
      <div className="memory-status">{presentation.statusLabel}</div>
      <h2>{presentation.title}</h2>
      <p>{presentation.summary}</p>
      <MemorySection title="Project type" values={presentation.projectType ? [presentation.projectType] : []} />
      <MemorySection title="技术栈" values={presentation.techStack} />
      <MemorySection title="项目规模" values={presentation.scale} />
      <MemorySection title="关键模块" values={presentation.modules} />
      <MemorySection title="关键路径" values={presentation.keyPaths} />
      <MemorySection title="约束 / 风险 / 未解析项" values={presentation.risks} />
      <details className="memory-details">
        <summary>技术详情 / 查看依据</summary>
        <pre>{JSON.stringify(presentation.details, null, 2)}</pre>
      </details>
    </article>
  );
}

function MemorySection({ title, values }: { title: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <section className="memory-section">
      <h3>{title}</h3>
      <div className="memory-chips">
        {values.map((value) => (
          <span key={value}>{value}</span>
        ))}
      </div>
    </section>
  );
}

function SettingsView({
  credentialError,
  credentialPending,
  credentialStatus,
  onClearCredential,
  onSaveCredential,
  project,
}: {
  credentialError: string | null;
  credentialPending: string | null;
  credentialStatus: CredentialStatus | null;
  onClearCredential: () => Promise<void>;
  onSaveCredential: (key: string, baseUrl: string, model: string) => Promise<void>;
  project: Project | null;
}) {
  const projectPath = project?.rootPath ?? "尚未打开本地项目";
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const configured = credentialStatus?.configured ?? false;
  useEffect(() => {
    setBaseUrl(credentialStatus?.baseUrl ?? "");
    setModel(credentialStatus?.model ?? "");
  }, [credentialStatus?.baseUrl, credentialStatus?.model]);
  const submitCredential = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const key = apiKey.trim();
    const trimmedBaseUrl = baseUrl.trim();
    const trimmedModel = model.trim();
    if (!key || !trimmedBaseUrl || !trimmedModel || credentialPending !== null) {
      return;
    }
    await onSaveCredential(key, trimmedBaseUrl, trimmedModel);
    setApiKey("");
  };

  return (
    <Page title="设置">
      <div className="settings-grid">
        <EmptyState title="本地项目" body={`当前目录：${projectPath}`} />
        <section className="setting-card">
          <div className="setting-head">
            <div className="setting-title">模型服务</div>
            <span className={`setting-status ${configured ? "" : "neutral"}`}>
              {configured ? "已配置" : "未配置"}
            </span>
          </div>
          <form className="setting-row credential-row" onSubmit={submitCredential}>
            <div className="setting-label">OpenAI 兼容接口</div>
            <div className="setting-value">
              {configured
                ? "LLM 已配置。页面不会显示已保存的 API Key。"
                : "尚未配置 LLM API Key。配置后 Mentor 才能生成结构化方案和分析。"}
              <span className="setting-sub">
                来源：{credentialStatus?.source ?? "未读取"}
              </span>
              <label className="setting-field" htmlFor="llm-base-url">
                API Base URL
                <input
                  autoComplete="off"
                  className="credential-input"
                  id="llm-base-url"
                  placeholder="https://api.example.com/v1"
                  type="url"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.currentTarget.value)}
                />
              </label>
              <label className="setting-field" htmlFor="llm-model">
                Model
                <input
                  autoComplete="off"
                  className="credential-input"
                  id="llm-model"
                  placeholder="服务商实际 model id"
                  type="text"
                  value={model}
                  onChange={(event) => setModel(event.currentTarget.value)}
                />
              </label>
              <label className="sr-only" htmlFor="llm-api-key">
                OpenAI API Key
              </label>
              <input
                autoComplete="off"
                className="credential-input"
                id="llm-api-key"
                placeholder={configured ? "粘贴新的 API Key 以更新" : "粘贴 API Key"}
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.currentTarget.value)}
              />
              {credentialError ? (
                <span className="setting-error" role="alert">
                  {credentialError}
                </span>
              ) : null}
            </div>
            <div className="page-actions">
              <Button
                disabled={!apiKey.trim() || !baseUrl.trim() || !model.trim() || credentialPending !== null}
                size="small"
                type="submit"
              >
                {credentialPending === "save" ? "保存中" : configured ? "更新模型服务" : "保存模型服务"}
              </Button>
              {configured ? (
                <Button
                  disabled={credentialPending !== null}
                  size="small"
                  variant="danger"
                  onClick={() => {
                    setApiKey("");
                    void onClearCredential();
                  }}
                >
                  {credentialPending === "clear" ? "清除中" : "清除 Key"}
                </Button>
              ) : null}
            </div>
          </form>
        </section>
      </div>
    </Page>
  );
}

function proposalToFixture(proposal: Proposal, superseded: boolean): ProposalFixture {
  return {
    acceptanceCriteria: proposal.acceptanceCriteria,
    changes: proposal.changes,
    completeness: proposal.completeness,
    display: proposal.display,
    executionBoundary: proposal.executionBoundary,
    expectedBehavior: proposal.expectedBehavior,
    files: proposal.impact,
    goal: proposal.goal,
    items: proposal.items,
    nonGoals: proposal.nonGoals,
    risk: proposal.risk,
    status: proposal.status,
    steps: proposal.steps,
    superseded,
    understanding: proposal.understanding,
    validation: proposal.validation,
    version: proposal.version,
  };
}

function workbenchMessageFromRecord(record: WorkbenchMessageRecord): WorkbenchMessage {
  return {
    createdAt: record.createdAt,
    id: record.id,
    kind: record.kind,
    proposal: record.proposal ? proposalToFixture(record.proposal, record.proposal.status === "SUPERSEDED") : undefined,
    role: record.role,
    status: record.status,
    taskId: record.taskId,
    text: record.text,
  };
}

function conversationMessagesForTask(
  taskId: string,
  persisted: Record<string, WorkbenchMessage[]>,
  optimistic: Record<string, WorkbenchMessage[]>,
): WorkbenchMessage[] {
  return [...(persisted[taskId] ?? []), ...(optimistic[taskId] ?? [])];
}

function reconcileOptimisticMessages(
  optimistic: WorkbenchMessage[],
  persisted: WorkbenchMessage[],
): WorkbenchMessage[] {
  return optimistic.filter((message) => !persisted.some((item) => sameWorkbenchMessage(item, message)));
}

function sameWorkbenchMessage(a: WorkbenchMessage, b: WorkbenchMessage): boolean {
  return a.role === b.role && a.kind === b.kind && a.status === b.status && a.text === b.text;
}

function knowledgeStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    CANDIDATE: "需复核",
    FAILED_EXPERIENCE: "失败经验",
    REVIEWED: "已复核",
    STALE: "已过期",
    VERIFIED: "已验证",
  };
  return labels[status] ?? status;
}

function userError(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "请求没有完成";
}

function Page({
  action,
  children,
  title,
}: {
  action?: string;
  children: ReactNode;
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
