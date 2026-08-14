import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  createMentorApi,
  type CompletionGate,
  type CredentialStatus,
  type DiffTrace,
  type ProjectGovernanceHistoryItem,
  type GovernanceReport,
  type KnowledgeItem,
  type LockStatus,
  type MentorApi,
  MentorApiError,
  type Project,
  type ProjectEvaluationList,
  type Proposal,
  type RecoveryItem,
  type Task,
  type TaskFileChanges,
  type TaskTimeline,
  type TaskTimelineItem,
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
import type { NavKey, ProposalFixture, WorkbenchMessage, WorkbenchTimelineItem } from "./fixtures";

interface AppProps {
  api?: MentorApi;
}

type ProposalQueryState = "LOADING" | "NOT_CREATED" | "EXISTS";
export type ProjectHydrationState = "BOOTING" | "READY" | "EMPTY" | "ERROR";
export type ResourceInitialStatus = "UNINITIALIZED" | "LOADING" | "READY" | "ERROR";
const BACKGROUND_REFETCH_DELAY_MS = 180;
const LAST_ACTIVE_VIEW_KEY = "se-mentor:lastActiveView";
const LAST_SELECTED_PROJECT_ID_KEY = "se-mentor:lastSelectedProjectId";

interface GovernanceReadState {
  error: string | null;
  initialStatus: ResourceInitialStatus;
  refreshing: boolean;
  report: GovernanceReport | null;
}

interface ProjectGovernanceHistoryReadState {
  detail: GovernanceReport | null;
  detailError: string | null;
  detailLoading: boolean;
  error: string | null;
  hasMore: boolean;
  initialStatus: ResourceInitialStatus;
  items: ProjectGovernanceHistoryItem[];
  loadingMore: boolean;
  nextOffset: number | null;
  refreshing: boolean;
  selectedDecisionId: string | null;
}

function startFrontendTiming(label: string): () => void {
  const started = typeof performance === "undefined" ? Date.now() : performance.now();
  return () => {
    const now = typeof performance === "undefined" ? Date.now() : performance.now();
    const totalMs = Math.round(now - started);
    console.info(`[perf] frontend.${label} total_ms=${totalMs}`);
  };
}

function readLastSelectedProjectId(): string | null {
  try {
    return window.localStorage.getItem(LAST_SELECTED_PROJECT_ID_KEY);
  } catch {
    return null;
  }
}

function rememberLastSelectedProjectId(projectId: string): void {
  try {
    window.localStorage.setItem(LAST_SELECTED_PROJECT_ID_KEY, projectId);
  } catch {
    // localStorage is a UI preference only; backend remains the project authority.
  }
}

function forgetLastSelectedProjectId(): void {
  try {
    window.localStorage.removeItem(LAST_SELECTED_PROJECT_ID_KEY);
  } catch {
    // localStorage is a UI preference only; backend remains the project authority.
  }
}

export function readLastActiveView(): NavKey {
  try {
    const stored = window.localStorage.getItem(LAST_ACTIVE_VIEW_KEY);
    return isNavKey(stored) ? stored : "workbench";
  } catch {
    return "workbench";
  }
}

export function rememberLastActiveView(view: NavKey): void {
  try {
    window.localStorage.setItem(LAST_ACTIVE_VIEW_KEY, view);
  } catch {
    // localStorage only preserves the user's route preference.
  }
}

function isNavKey(value: string | null): value is NavKey {
  return (
    value === "workbench" ||
    value === "tasks" ||
    value === "memory" ||
    value === "governance" ||
    value === "evaluation" ||
    value === "settings"
  );
}

export function isOnlineSafeCredentialStatus(status: CredentialStatus | null): boolean {
  return status?.source === "ONLINE_SAFE" || status?.source === "ONLINE_SAFE_SESSION";
}

export function isCloudDemoCredentialStatus(status: CredentialStatus | null): boolean {
  return status?.source === "CLOUD_DEMO";
}

function selectProjectZipFile(): Promise<File | null> {
  if (typeof document === "undefined") {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".zip,application/zip";
    input.onchange = () => resolve(input.files?.[0] ?? null);
    input.click();
  });
}

function downloadBlob(blob: Blob, filename: string): void {
  if (typeof document === "undefined") {
    return;
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function canConfirmHydratedProposal({
  pendingAction,
  proposalId,
  taskId,
}: {
  pendingAction: string | null;
  proposalId: string | null;
  taskId: string | null;
}): boolean {
  return pendingAction === null && Boolean(taskId) && Boolean(proposalId);
}

export function App({ api: providedApi }: AppProps = {}) {
  const defaultApi = useMemo(() => createMentorApi(), []);
  const api = providedApi ?? defaultApi;
  const [activeView, setActiveView] = useState<NavKey>(() => readLastActiveView());
  const [project, setProject] = useState<Project | null>(null);
  const [lockStatus, setLockStatus] = useState<LockStatus | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [activeProposal, setActiveProposal] = useState<Proposal | null>(null);
  const [proposalQueryState, setProposalQueryState] = useState<ProposalQueryState>("NOT_CREATED");
  const [taskListLoading, setTaskListLoading] = useState(false);
  const [taskDetailLoading, setTaskDetailLoading] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [projectOpening, setProjectOpening] = useState(false);
  const [projectHydrationState, setProjectHydrationState] = useState<ProjectHydrationState>("BOOTING");
  const [taskError, setTaskError] = useState<string | null>(null);
  const [taskErrorTitle, setTaskErrorTitle] = useState<string | null>(null);
  const [persistedWorkbenchMessagesByTask, setPersistedWorkbenchMessagesByTask] = useState<Record<string, WorkbenchMessage[]>>({});
  const [optimisticWorkbenchMessagesByTask, setOptimisticWorkbenchMessagesByTask] = useState<Record<string, WorkbenchMessage[]>>({});
  const [newTaskPending, setNewTaskPending] = useState(false);
  const [newTaskStage, setNewTaskStage] = useState<NewTaskStage>("IDLE");
  const [proposalAction, setProposalAction] = useState<string | null>(null);
  const [governanceByTask, setGovernanceByTask] = useState<Record<string, GovernanceReadState>>({});
  const [governanceHistoryByProject, setGovernanceHistoryByProject] = useState<Record<string, ProjectGovernanceHistoryReadState>>({});
  const [harnessProgress, setHarnessProgress] = useState<string | null>(null);
  const [approvalAction, setApprovalAction] = useState<string | null>(null);
  const [approvalGranted, setApprovalGranted] = useState(false);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [cancelPending, setCancelPending] = useState(false);
  const [diffTrace] = useState<DiffTrace | null>(null);
  const [fileChangesByTask, setFileChangesByTask] = useState<Record<string, DiffTrace[]>>({});
  const [fileChangesLoadingByTask, setFileChangesLoadingByTask] = useState<Record<string, boolean>>({});
  const [fileChangesErrorByTask, setFileChangesErrorByTask] = useState<Record<string, string | null>>({});
  const [timelineByTask, setTimelineByTask] = useState<Record<string, WorkbenchTimelineItem[]>>({});
  const [timelineErrorByTask, setTimelineErrorByTask] = useState<Record<string, string | null>>({});
  const [validationResults] = useState<ValidationResult[]>([]);
  const [completionGate] = useState<CompletionGate[]>([]);
  const [projectEvaluations, setProjectEvaluations] = useState<ProjectEvaluationList | null>(null);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);
  const [evaluationLoading, setEvaluationLoading] = useState(false);
  const [recoveryItems, setRecoveryItems] = useState<RecoveryItem[]>([]);
  const [recoveryPendingTaskId, setRecoveryPendingTaskId] = useState<string | null>(null);
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);
  const [knowledgeError, setKnowledgeError] = useState<string | null>(null);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [credentialStatus, setCredentialStatus] = useState<CredentialStatus | null>(null);
  const [credentialPending, setCredentialPending] = useState<string | null>(null);
  const [credentialError, setCredentialError] = useState<string | null>(null);
  const taskEvents = useTaskEvents(api, activeTask?.id ?? null);
  const hydrationRunRef = useRef(0);
  const executionDispatchRef = useRef<string | null>(null);
  const processedEventIdsRef = useRef<Set<number>>(new Set());
  const activeTaskIdRef = useRef<string | null>(null);
  const taskListRunRef = useRef(0);
  const governanceRequestRunRef = useRef<Record<string, number>>({});
  const governanceHistoryRequestRunRef = useRef<Record<string, number>>({});
  const governanceDetailRequestRunRef = useRef<Record<string, number>>({});
  const fileChangeRequestRunRef = useRef<Record<string, number>>({});
  const timelineRequestRunRef = useRef<Record<string, number>>({});
  const governanceRefreshTimersRef = useRef<Record<string, number>>({});
  const governanceHistoryRefreshTimersRef = useRef<Record<string, number>>({});
  const fileChangeRefreshTimersRef = useRef<Record<string, number>>({});
  const timelineRefreshTimersRef = useRef<Record<string, number>>({});

  const applyTaskSnapshot = useCallback((task: Task) => {
    setActiveTask((current) => (current?.id === task.id ? task : current));
    setTasks((current) => upsertTasks(current, [task]));
  }, []);

  useEffect(() => {
    activeTaskIdRef.current = activeTask?.id ?? null;
  }, [activeTask?.id]);

  const loadWorkbenchMessages = useCallback(
    async (taskId: string) => {
      const finishTiming = startFrontendTiming("task_messages");
      try {
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
      } finally {
        finishTiming();
      }
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

  const loadTaskFileChanges = useCallback(
    async (taskId: string) => {
      const finishTiming = startFrontendTiming("task_file_changes");
      const requestId = (fileChangeRequestRunRef.current[taskId] ?? 0) + 1;
      fileChangeRequestRunRef.current[taskId] = requestId;
      setFileChangesLoadingByTask((current) => ({ ...current, [taskId]: true }));
      setFileChangesErrorByTask((current) => ({ ...current, [taskId]: null }));
      try {
        const result: TaskFileChanges = await api.getTaskFileChanges(taskId);
        if (fileChangeRequestRunRef.current[taskId] !== requestId) {
          return;
        }
        setFileChangesByTask((current) => ({ ...current, [taskId]: result.items }));
      } catch (error) {
        if (fileChangeRequestRunRef.current[taskId] === requestId) {
          setFileChangesErrorByTask((current) => ({ ...current, [taskId]: userError(error) }));
        }
      } finally {
        if (fileChangeRequestRunRef.current[taskId] === requestId) {
          setFileChangesLoadingByTask((current) => ({ ...current, [taskId]: false }));
        }
        finishTiming();
      }
    },
    [api],
  );

  const loadTaskTimeline = useCallback(
    async (taskId: string) => {
      const finishTiming = startFrontendTiming("task_timeline");
      const requestId = (timelineRequestRunRef.current[taskId] ?? 0) + 1;
      timelineRequestRunRef.current[taskId] = requestId;
      setTimelineErrorByTask((current) => ({ ...current, [taskId]: null }));
      try {
        const result: TaskTimeline = await api.getTaskTimeline(taskId);
        if (timelineRequestRunRef.current[taskId] !== requestId) {
          return;
        }
        setTimelineByTask((current) => ({
          ...current,
          [taskId]: dedupeTimelineItems(result.items.map((item) => timelineItemFromRecord(taskId, item))),
        }));
      } catch (error) {
        if (timelineRequestRunRef.current[taskId] === requestId) {
          setTimelineErrorByTask((current) => ({ ...current, [taskId]: userError(error) }));
        }
      } finally {
        finishTiming();
      }
    },
    [api],
  );

  const ensureTaskFileChanges = useCallback(
    (taskId: string) => {
      if (fileChangesByTask[taskId] || fileChangesLoadingByTask[taskId]) {
        return;
      }
      void loadTaskFileChanges(taskId);
    },
    [fileChangesByTask, fileChangesLoadingByTask, loadTaskFileChanges],
  );

  useEffect(() => {
    void loadCredentialStatus();
  }, [loadCredentialStatus]);

  const loadTaskList = useCallback(
    async (projectId: string) => {
      const runId = taskListRunRef.current + 1;
      taskListRunRef.current = runId;
      setTaskListLoading(true);
      setProjectError(null);
      try {
        const [list, locks] = await Promise.all([
          api.getTaskList(projectId),
          api.getProjectLocks(projectId),
        ]);
        if (taskListRunRef.current !== runId) {
          return;
        }
        setTasks((current) => replaceTasksForProject(current, projectId, list.items));
        setLockStatus(locks);
      } catch (error) {
        if (taskListRunRef.current === runId) {
          setProjectError(userError(error));
        }
      } finally {
        if (taskListRunRef.current === runId) {
          setTaskListLoading(false);
        }
      }
    },
    [api],
  );

  const fetchProposalForTask = useCallback(
    async (taskId: string): Promise<Proposal | null> => {
      try {
        return await api.getProposal(taskId);
      } catch (error) {
        if (isApiErrorCode(error, "PROPOSAL_NOT_FOUND")) {
          return null;
        }
        throw error;
      }
    },
    [api],
  );

  const hydrateFromRegisteredProjects = useCallback(async () => {
    const finishTiming = startFrontendTiming("project_hydration");
    const runId = hydrationRunRef.current + 1;
    hydrationRunRef.current = runId;
    const isCurrentRun = () => hydrationRunRef.current === runId;
    setTaskListLoading(true);
    setTaskDetailLoading(false);
    setProjectHydrationState("BOOTING");
    setProjectError(null);
    setTaskError(null);
    try {
      const registered = await api.getProjects();
      if (!isCurrentRun()) {
        return;
      }
      const currentProject = registered.items[0] ?? null;
      if (!currentProject) {
        forgetLastSelectedProjectId();
        setProject(null);
        setTasks([]);
        setLockStatus(null);
        setActiveTask(null);
        setActiveProposal(null);
        setProposalQueryState("NOT_CREATED");
        setProjectHydrationState("EMPTY");
        return;
      }
      const selectedProjectId = readLastSelectedProjectId();
      const selectedProject =
        registered.items.find((item) => item.id === selectedProjectId) ?? currentProject;
      if (selectedProjectId && selectedProject.id !== selectedProjectId) {
        forgetLastSelectedProjectId();
      }
      setProject(selectedProject);
      rememberLastSelectedProjectId(selectedProject.id);
      const [list, locks] = await Promise.all([
        api.getTaskList(selectedProject.id),
        api.getProjectLocks(selectedProject.id),
      ]);
      if (!isCurrentRun()) {
        return;
      }
      setTasks((current) => replaceTasksForProject(current, selectedProject.id, list.items));
      setLockStatus(locks);
      const currentTask = list.items[0] ?? null;
      if (!currentTask) {
        setActiveTask(null);
        setActiveProposal(null);
        setProposalQueryState("NOT_CREATED");
        setProjectHydrationState("READY");
        return;
      }
      setActiveTask((current) => current ?? currentTask);
      setTaskDetailLoading(false);
      setProposalQueryState("LOADING");
      setApprovalGranted(false);
      setProjectHydrationState("READY");
      void Promise.allSettled([
        api.getProjectConfig(selectedProject.id),
        api.getTask(currentTask.id).then((task) => {
          if (isCurrentRun()) {
            applyTaskSnapshot(task);
          }
        }),
        fetchProposalForTask(currentTask.id).then((proposal) => {
          if (!isCurrentRun()) {
            return;
          }
          setActiveProposal(proposal);
          setProposalQueryState(proposal ? "EXISTS" : "NOT_CREATED");
          setNewTaskStage(proposal ? "PROPOSAL_READY" : "IDLE");
        }),
        loadWorkbenchMessages(currentTask.id),
        loadTaskTimeline(currentTask.id),
      ]);
    } catch (error) {
      if (isCurrentRun()) {
        setProjectError(userError(error));
        setProposalQueryState("NOT_CREATED");
        setProjectHydrationState("ERROR");
      }
    } finally {
      if (isCurrentRun()) {
        setTaskDetailLoading(false);
        setTaskListLoading(false);
        finishTiming();
      }
    }
  }, [api, applyTaskSnapshot, fetchProposalForTask, loadTaskTimeline, loadWorkbenchMessages]);

  useEffect(() => {
    void hydrateFromRegisteredProjects();
  }, [hydrateFromRegisteredProjects]);

  useEffect(() => {
    rememberLastActiveView(activeView);
  }, [activeView]);

  const onlineSafeProfile = isOnlineSafeCredentialStatus(credentialStatus);

  const openProject = useCallback(async () => {
    if (projectOpening) {
      return;
    }
    if (onlineSafeProfile && project) {
      setProjectError(
        "当前在线会话已经有上传项目。为了避免清除任务、治理和执行状态，本版本不会覆盖项目；请使用新的浏览器会话上传另一个 ZIP。",
      );
      return;
    }
    const finishTiming = startFrontendTiming("project_open");
    const runId = hydrationRunRef.current + 1;
    hydrationRunRef.current = runId;
    const isCurrentRun = () => hydrationRunRef.current === runId;
    setProjectOpening(true);
    setProjectError(null);
    try {
      const zipFile = onlineSafeProfile ? await selectProjectZipFile() : null;
      if (onlineSafeProfile && !zipFile) {
        return;
      }
      const opened = zipFile ? await api.importProjectZip(zipFile) : await api.chooseLocalProject();
      if (!isCurrentRun()) {
        return;
      }
      setProject(opened);
      rememberLastSelectedProjectId(opened.id);
      setActiveTask(null);
      setActiveProposal(null);
      setProposalQueryState("NOT_CREATED");
      setActiveView("workbench");
      setTaskListLoading(true);
      const [list, locks] = await Promise.all([
        api.getTaskList(opened.id),
        api.getProjectLocks(opened.id),
        api.getProjectConfig(opened.id),
      ]);
      if (!isCurrentRun()) {
        return;
      }
      setTasks((current) => replaceTasksForProject(current, opened.id, list.items));
      setLockStatus(locks);
      setActiveTask(null);
      setActiveProposal(null);
      setProposalQueryState("NOT_CREATED");
    } catch (error) {
      if (isCurrentRun()) {
        setProjectError(userError(error));
      }
    } finally {
      if (isCurrentRun()) {
        setTaskListLoading(false);
        setProjectOpening(false);
      }
      finishTiming();
    }
  }, [api, onlineSafeProfile, project, projectOpening]);

  const openTask = useCallback(
    async (taskId: string) => {
      const finishTiming = startFrontendTiming("task_open");
      const runId = hydrationRunRef.current + 1;
      hydrationRunRef.current = runId;
      const isCurrentRun = () => hydrationRunRef.current === runId;
      const cachedTask = tasks.find((item) => item.id === taskId) ?? null;
      if (cachedTask) {
        setActiveTask(cachedTask);
        setTaskDetailLoading(false);
      } else {
        setTaskDetailLoading(true);
      }
      setTaskError(null);
      setTaskErrorTitle(null);
      setActiveView("workbench");
      setActiveProposal(null);
      setProposalQueryState("LOADING");
      try {
        void Promise.allSettled([loadWorkbenchMessages(taskId), loadTaskTimeline(taskId)]);
        const [taskResult, proposalResult] = await Promise.allSettled([
          api.getTask(taskId),
          fetchProposalForTask(taskId),
        ]);
        if (!isCurrentRun()) {
          return;
        }
        if (taskResult.status === "fulfilled") {
          applyTaskSnapshot(taskResult.value);
        } else {
          throw taskResult.reason;
        }
        if (proposalResult.status === "fulfilled") {
          if (activeTaskIdRef.current === taskId) {
            setActiveProposal(proposalResult.value);
            setProposalQueryState(proposalResult.value ? "EXISTS" : "NOT_CREATED");
          }
        } else {
          if (activeTaskIdRef.current === taskId) {
            setProposalQueryState("NOT_CREATED");
          }
          throw proposalResult.reason;
        }
        setApprovalGranted(false);
      } catch (error) {
        if (isCurrentRun()) {
          setTaskError(userError(error));
        }
      } finally {
        if (isCurrentRun()) {
          setTaskDetailLoading(false);
        }
        finishTiming();
      }
    },
    [api, applyTaskSnapshot, fetchProposalForTask, loadTaskTimeline, loadWorkbenchMessages, tasks],
  );

  const createTask = useCallback(
    async (request: string) => {
      if (!project || newTaskPending) {
        return;
      }
      hydrationRunRef.current += 1;
      setNewTaskPending(true);
      setTaskError(null);
      setTaskErrorTitle(null);
      setNewTaskStage("TASK_CREATING");
      try {
        const task = await api.createTask(project.id, request);
        setNewTaskStage("PROPOSAL_GENERATING");
        setActiveTask(task);
        setTasks((current) => [task, ...current.filter((item) => item.id !== task.id)]);
        setActiveProposal(null);
        setProposalQueryState("LOADING");
        void loadTaskTimeline(task.id);
        await loadWorkbenchMessages(task.id);
        setGovernanceByTask((current) => {
          const next = { ...current };
          delete next[task.id];
          return next;
        });
        setHarnessProgress(null);
        void loadTaskList(project.id);
        const progressId = appendWorkbenchMessage(task.id, {
          kind: "PROGRESS",
          role: "MENTOR",
          status: "PENDING",
          text: "Mentor 正在生成方案",
        });
        const question = request.includes("?")
          ? "请补充你最希望优先达成的目标。"
          : undefined;
        const proposal = await api.createProposal(task.id, request, question);
        applyTaskSnapshot(await api.getTask(task.id));
        setActiveProposal(proposal);
        setProposalQueryState("EXISTS");
        updateWorkbenchMessage(task.id, progressId, {
          kind: "PROPOSAL",
          proposal: proposalToFixture(proposal, false),
          status: "DONE",
          text: `方案已生成：Proposal v${proposal.version}`,
        });
        setNewTaskStage("PROPOSAL_READY");
        void loadWorkbenchMessages(task.id);
        void loadTaskTimeline(task.id);
        void loadTaskList(project.id);
      } catch (error) {
        setTaskErrorTitle("任务已创建，但方案生成失败。");
        setTaskError(userError(error));
        setNewTaskStage("PROPOSAL_FAILED");
        setProposalQueryState("NOT_CREATED");
        throw error;
      } finally {
        setNewTaskPending(false);
      }
    },
    [
      api,
      appendWorkbenchMessage,
      applyTaskSnapshot,
      loadTaskTimeline,
      loadTaskList,
      loadWorkbenchMessages,
      newTaskPending,
      project,
      updateWorkbenchMessage,
    ],
  );

  const reconcileTaskProjection = useCallback(async (taskId: string) => {
    const [task, proposal, timeline] = await Promise.all([
      api.getTask(taskId),
      fetchProposalForTask(taskId),
      api.getTaskTimeline(taskId),
    ]);
    applyTaskSnapshot(task);
    if (activeTaskIdRef.current === taskId) {
      setActiveProposal(proposal);
      setProposalQueryState(proposal ? "EXISTS" : "NOT_CREATED");
    }
    setTimelineByTask((current) => ({
      ...current,
      [taskId]: dedupeTimelineItems(timeline.items.map((item) => timelineItemFromRecord(taskId, item))),
    }));
    return { proposal, task, timeline };
  }, [api, applyTaskSnapshot, fetchProposalForTask]);

  const refreshActiveTask = useCallback(async () => {
    if (!activeTask) {
      return;
    }
    await reconcileTaskProjection(activeTask.id);
  }, [activeTask, reconcileTaskProjection]);

  const scheduleFileChangesRefresh = useCallback(
    (taskId: string) => {
      const currentTimer = fileChangeRefreshTimersRef.current[taskId];
      if (currentTimer) {
        window.clearTimeout(currentTimer);
      }
      fileChangeRefreshTimersRef.current[taskId] = window.setTimeout(() => {
        delete fileChangeRefreshTimersRef.current[taskId];
        void loadTaskFileChanges(taskId);
      }, BACKGROUND_REFETCH_DELAY_MS);
    },
    [loadTaskFileChanges],
  );

  const scheduleTimelineRefresh = useCallback(
    (taskId: string) => {
      const currentTimer = timelineRefreshTimersRef.current[taskId];
      if (currentTimer) {
        window.clearTimeout(currentTimer);
      }
      timelineRefreshTimersRef.current[taskId] = window.setTimeout(() => {
        delete timelineRefreshTimersRef.current[taskId];
        void loadTaskTimeline(taskId);
      }, BACKGROUND_REFETCH_DELAY_MS);
    },
    [loadTaskTimeline],
  );

  const loadProjectGovernanceHistory = useCallback(async () => {
    if (!project) {
      return;
    }
    const projectId = project.id;
    const requestId = (governanceHistoryRequestRunRef.current[projectId] ?? 0) + 1;
    governanceHistoryRequestRunRef.current[projectId] = requestId;
    setGovernanceHistoryByProject((current) => {
      const previous = current[projectId] ?? emptyProjectGovernanceHistoryReadState();
      return {
        ...current,
        [projectId]: {
          ...previous,
          error: null,
          initialStatus: previous.items.length > 0 ? previous.initialStatus : "LOADING",
          refreshing: previous.items.length > 0,
        },
      };
    });
    const finishTiming = startFrontendTiming("governance_history");
    try {
      const history = await api.getProjectGovernanceHistory(projectId, { limit: 20, offset: 0 });
      if (governanceHistoryRequestRunRef.current[projectId] !== requestId) {
        return;
      }
      setGovernanceHistoryByProject((current) => {
        const previous = current[projectId] ?? emptyProjectGovernanceHistoryReadState();
        const selectedDecisionId = history.items.some(
          (item) => item.governanceDecisionId === previous.selectedDecisionId,
        )
          ? previous.selectedDecisionId
          : null;
        return {
          ...current,
          [projectId]: {
            ...previous,
            error: null,
            hasMore: history.hasMore,
            initialStatus: "READY",
            items: history.items,
            loadingMore: false,
            nextOffset: history.nextOffset ?? null,
            refreshing: false,
            selectedDecisionId,
          },
        };
      });
    } catch (error) {
      if (governanceHistoryRequestRunRef.current[projectId] === requestId) {
        setGovernanceHistoryByProject((current) => {
          const previous = current[projectId] ?? emptyProjectGovernanceHistoryReadState();
          return {
            ...current,
            [projectId]: {
              ...previous,
              error: userError(error),
              initialStatus: previous.items.length > 0 ? previous.initialStatus : "ERROR",
              refreshing: false,
            },
          };
        });
      }
    } finally {
      if (governanceHistoryRequestRunRef.current[projectId] === requestId) {
        setGovernanceHistoryByProject((current) => {
          const previous = current[projectId];
          if (!previous) {
            return current;
          }
          return {
            ...current,
            [projectId]: {
              ...previous,
              refreshing: false,
            },
          };
        });
      }
      finishTiming();
    }
  }, [api, project]);

  const loadMoreProjectGovernanceHistory = useCallback(async () => {
    if (!project) {
      return;
    }
    const projectId = project.id;
    const previous = governanceHistoryByProject[projectId] ?? emptyProjectGovernanceHistoryReadState();
    if (previous.loadingMore || !previous.hasMore || previous.nextOffset === null) {
      return;
    }
    setGovernanceHistoryByProject((current) => ({
      ...current,
      [projectId]: {
        ...(current[projectId] ?? emptyProjectGovernanceHistoryReadState()),
        loadingMore: true,
      },
    }));
    try {
      const history = await api.getProjectGovernanceHistory(projectId, {
        limit: 20,
        offset: previous.nextOffset,
      });
      setGovernanceHistoryByProject((current) => {
        const currentHistory = current[projectId] ?? emptyProjectGovernanceHistoryReadState();
        return {
          ...current,
          [projectId]: {
            ...currentHistory,
            error: null,
            hasMore: history.hasMore,
            initialStatus: "READY",
            items: dedupeGovernanceHistory([...currentHistory.items, ...history.items]),
            loadingMore: false,
            nextOffset: history.nextOffset ?? null,
          },
        };
      });
    } catch (error) {
      setGovernanceHistoryByProject((current) => {
        const currentHistory = current[projectId] ?? emptyProjectGovernanceHistoryReadState();
        return {
          ...current,
          [projectId]: {
            ...currentHistory,
            error: userError(error),
            loadingMore: false,
          },
        };
      });
    }
  }, [api, governanceHistoryByProject, project]);

  const loadGovernanceDecisionDetail = useCallback(async (decision: ProjectGovernanceHistoryItem) => {
    if (!project) {
      return;
    }
    const projectId = project.id;
    const requestId = (governanceDetailRequestRunRef.current[projectId] ?? 0) + 1;
    governanceDetailRequestRunRef.current[projectId] = requestId;
    setGovernanceHistoryByProject((current) => {
      const previous = current[projectId] ?? emptyProjectGovernanceHistoryReadState();
      return {
        ...current,
        [projectId]: {
          ...previous,
          detailError: null,
          detailLoading: true,
          selectedDecisionId: decision.governanceDecisionId,
        },
      };
    });
    const finishTiming = startFrontendTiming("governance_detail");
    try {
      const detail = await api.getGovernanceDecision(projectId, decision.governanceDecisionId);
      if (governanceDetailRequestRunRef.current[projectId] !== requestId) {
        return;
      }
      setGovernanceHistoryByProject((current) => {
        const previous = current[projectId] ?? emptyProjectGovernanceHistoryReadState();
        return {
          ...current,
          [projectId]: {
            ...previous,
            detail,
            detailError: null,
            detailLoading: false,
          },
        };
      });
    } catch (error) {
      if (governanceDetailRequestRunRef.current[projectId] === requestId) {
        setGovernanceHistoryByProject((current) => {
          const previous = current[projectId] ?? emptyProjectGovernanceHistoryReadState();
          return {
            ...current,
            [projectId]: {
              ...previous,
              detailError: userError(error),
              detailLoading: false,
            },
          };
        });
      }
    } finally {
      finishTiming();
    }
  }, [api, project]);

  const loadGovernance = useCallback(async (proposalOverride?: Proposal) => {
    const proposal = proposalOverride ?? activeProposal;
    if (!proposal || proposal.status !== "CONFIRMED") {
      return;
    }
    const taskId = proposal.taskId;
    const requestId = (governanceRequestRunRef.current[taskId] ?? 0) + 1;
    governanceRequestRunRef.current[taskId] = requestId;
    setGovernanceByTask((current) => {
      const previous = current[taskId] ?? emptyGovernanceReadState();
      return {
        ...current,
        [taskId]: {
          ...previous,
          error: null,
          initialStatus: previous.report ? previous.initialStatus : "LOADING",
          refreshing: Boolean(previous.report),
        },
      };
    });
    const finishTiming = startFrontendTiming("governance_load");
    try {
      const report = await api.getGovernance(proposal.id);
      if (governanceRequestRunRef.current[taskId] !== requestId) {
        return;
      }
      setGovernanceByTask((current) => ({
        ...current,
        [taskId]: {
          error: null,
          initialStatus: "READY",
          refreshing: false,
          report,
        },
      }));
      void loadTaskTimeline(proposal.taskId);
    } catch (error) {
      if (governanceRequestRunRef.current[taskId] === requestId) {
        setGovernanceByTask((current) => {
          const previous = current[taskId] ?? emptyGovernanceReadState();
          return {
            ...current,
            [taskId]: {
              ...previous,
              error: userError(error),
              initialStatus: previous.report ? previous.initialStatus : "ERROR",
              refreshing: false,
            },
          };
        });
      }
    } finally {
      if (governanceRequestRunRef.current[taskId] === requestId) {
        setGovernanceByTask((current) => {
          const previous = current[taskId];
          if (!previous) {
            return current;
          }
          return {
            ...current,
            [taskId]: {
              ...previous,
              refreshing: false,
            },
          };
        });
      }
      finishTiming();
    }
  }, [activeProposal, api, loadTaskTimeline]);

  const runGovernance = useCallback(async (proposal: Proposal) => {
    const taskId = proposal.taskId;
    const requestId = (governanceRequestRunRef.current[taskId] ?? 0) + 1;
    governanceRequestRunRef.current[taskId] = requestId;
    setGovernanceByTask((current) => {
      const previous = current[taskId] ?? emptyGovernanceReadState();
      return {
        ...current,
        [taskId]: {
          ...previous,
          error: null,
          initialStatus: previous.report ? previous.initialStatus : "LOADING",
          refreshing: Boolean(previous.report),
        },
      };
    });
    const finishTiming = startFrontendTiming("governance_run");
    try {
      const report = await api.runGovernance(proposal.id, proposal.items);
      const task = await api.getTask(proposal.taskId);
      if (governanceRequestRunRef.current[taskId] !== requestId) {
        return;
      }
      setGovernanceByTask((current) => ({
        ...current,
        [taskId]: {
          error: null,
          initialStatus: "READY",
          refreshing: false,
          report,
        },
      }));
      applyTaskSnapshot(task);
      void loadTaskTimeline(proposal.taskId);
    } catch (error) {
      if (governanceRequestRunRef.current[taskId] === requestId) {
        setGovernanceByTask((current) => {
          const previous = current[taskId] ?? emptyGovernanceReadState();
          return {
            ...current,
            [taskId]: {
              ...previous,
              error: userError(error),
              initialStatus: previous.report ? previous.initialStatus : "ERROR",
              refreshing: false,
            },
          };
        });
      }
    } finally {
      if (governanceRequestRunRef.current[taskId] === requestId) {
        setGovernanceByTask((current) => {
          const previous = current[taskId];
          if (!previous) {
            return current;
          }
          return {
            ...current,
            [taskId]: {
              ...previous,
              refreshing: false,
            },
          };
        });
      }
      finishTiming();
    }
  }, [api, applyTaskSnapshot, loadTaskTimeline]);

  const scheduleGovernanceRefresh = useCallback(
    (proposal: Proposal) => {
      const currentTimer = governanceRefreshTimersRef.current[proposal.taskId];
      if (currentTimer) {
        window.clearTimeout(currentTimer);
      }
      governanceRefreshTimersRef.current[proposal.taskId] = window.setTimeout(() => {
        delete governanceRefreshTimersRef.current[proposal.taskId];
        void loadGovernance(proposal);
      }, BACKGROUND_REFETCH_DELAY_MS);
    },
    [loadGovernance],
  );

  const scheduleProjectGovernanceHistoryRefresh = useCallback(
    (projectId: string) => {
      const currentTimer = governanceHistoryRefreshTimersRef.current[projectId];
      if (currentTimer) {
        window.clearTimeout(currentTimer);
      }
      governanceHistoryRefreshTimersRef.current[projectId] = window.setTimeout(() => {
        delete governanceHistoryRefreshTimersRef.current[projectId];
        void loadProjectGovernanceHistory();
      }, BACKGROUND_REFETCH_DELAY_MS);
    },
    [loadProjectGovernanceHistory],
  );

  const confirmProposal = useCallback(async () => {
    if (proposalAction !== null) {
      return;
    }
    const taskId = activeTask?.id ?? null;
    const proposalId = activeProposal?.id ?? null;
    if (!taskId || !proposalId) {
      setTaskError(
        !taskId
          ? "Cannot confirm before the task has been restored."
          : proposalQueryState === "LOADING"
            ? "Cannot confirm while the proposal is still loading."
            : "Cannot confirm because no persisted proposal is available.",
      );
      return;
    }
    if (!canConfirmHydratedProposal({ pendingAction: proposalAction, proposalId, taskId })) {
      return;
    }
    setProposalAction("confirm");
    try {
      const confirmed = await api.confirmProposal(taskId, proposalId);
      setActiveProposal(confirmed);
      await reconcileTaskProjection(taskId);
      void loadGovernance(confirmed);
      setHarnessProgress("正在分析影响范围");
    } catch (error) {
      setTaskError(userError(error));
    } finally {
      setProposalAction(null);
    }
  }, [activeProposal, activeTask, api, loadGovernance, proposalAction, proposalQueryState, reconcileTaskProjection]);

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
        text: "Mentor is analyzing",
      });
      try {
        const result = await api.createMentorTurn(activeTask.id, text);
        if (result.proposal) {
          setActiveProposal(result.proposal);
        }
        updateWorkbenchMessage(activeTask.id, progressId, result.message
          ? workbenchMessageFromRecord(result.message)
          : { kind: "TEXT", role: "MENTOR", status: "DONE", text: "Done." });
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
      text: "Mentor is regenerating a proposal",
    });
    try {
      const proposal = await api.createProposal(activeTask.id, activeTask.request);
      setActiveProposal(proposal);
      setProposalQueryState("EXISTS");
      updateWorkbenchMessage(activeTask.id, progressId, {
        kind: "PROPOSAL",
        proposal: proposalToFixture(proposal, false),
        status: "DONE",
        text: `闁哄鏅滈悷锕€危閹间礁绠ｉ柟瀵稿У閻ｅ崬菐閸ヨ泛鏋熼柡浣搞偢瀵剛鎲撮崟鍨暤闂佹寧绋掗悺宄硂posal v${proposal.version}`,
      });
      setNewTaskStage("PROPOSAL_READY");
      void loadWorkbenchMessages(activeTask.id);
      void loadTaskTimeline(activeTask.id);
    } catch (error) {
      updateWorkbenchMessage(activeTask.id, progressId, {
        kind: "ERROR",
        role: "MENTOR",
        status: "ERROR",
        text: userError(error),
      });
      setNewTaskStage("PROPOSAL_FAILED");
      setProposalQueryState("NOT_CREATED");
    } finally {
      setNewTaskPending(false);
    }
  }, [
    activeTask,
    api,
    appendWorkbenchMessage,
    loadTaskTimeline,
    loadWorkbenchMessages,
    updateWorkbenchMessage,
  ]);

  useEffect(() => {
    if (activeView === "governance") {
      void loadProjectGovernanceHistory();
    }
  }, [activeView, loadProjectGovernanceHistory]);

  useEffect(() => {
    if (!activeTask) {
      return;
    }
    const newEvents = taskEvents.events.filter((event) => {
      if (processedEventIdsRef.current.has(event.eventId)) {
        return false;
      }
      processedEventIdsRef.current.add(event.eventId);
      return true;
    });
    if (newEvents.length === 0) {
      return;
    }
    const fileChangeRefresh = newEvents.some((event) =>
      ["FILE_CHANGED", "TOOL_COMPLETED", "TASK_COMPLETED"].includes(event.eventType),
    );
    const timelineRefresh = newEvents.some((event) =>
      [
        "ACTION_GOVERNED",
        "GOVERNANCE_DECIDED",
        "TOOL_COMPLETED",
        "FILE_CHANGED",
        "VALIDATION_COMPLETED",
        "TASK_COMPLETED",
        "TASK_FAILED",
        "EXECUTION_COMPLETED",
        "EXECUTION_FAILED",
      ].includes(event.eventType),
    );
    const governanceRefresh = newEvents.some((event) =>
      ["ACTION_GOVERNED", "GOVERNANCE_DECIDED"].includes(event.eventType),
    );
    const cancelRequested = newEvents.some((event) => event.eventType === "CANCEL_REQUESTED");
    const taskRefresh = newEvents.some((event) =>
      [
        "TASK_CANCELLED",
        "TASK_COMPLETED",
        "TASK_FAILED",
        "EXECUTION_COMPLETED",
        "EXECUTION_FAILED",
      ].includes(event.eventType),
    );
    if (fileChangeRefresh) {
      scheduleFileChangesRefresh(activeTask.id);
    }
    if (timelineRefresh) {
      scheduleTimelineRefresh(activeTask.id);
    }
    if (governanceRefresh && activeProposal?.status === "CONFIRMED") {
      scheduleGovernanceRefresh(activeProposal);
    }
    if (governanceRefresh && project) {
      scheduleProjectGovernanceHistoryRefresh(project.id);
    }
    if (cancelRequested) {
      applyTaskSnapshot({ ...activeTask, status: "CANCEL_REQUESTED" });
    }
    if (taskRefresh) {
      void reconcileTaskProjection(activeTask.id);
    }
  }, [
    activeTask,
    activeProposal,
    applyTaskSnapshot,
    project,
    reconcileTaskProjection,
    scheduleFileChangesRefresh,
    scheduleGovernanceRefresh,
    scheduleProjectGovernanceHistoryRefresh,
    scheduleTimelineRefresh,
    taskEvents.events,
  ]);

  useEffect(() => {
    if (activeTask && taskEvents.reconnectCount > 0) {
      void reconcileTaskProjection(activeTask.id);
      scheduleFileChangesRefresh(activeTask.id);
    }
  }, [activeTask, reconcileTaskProjection, scheduleFileChangesRefresh, taskEvents.reconnectCount]);

  useEffect(() => {
    processedEventIdsRef.current = new Set();
  }, [activeTask?.id]);

  const activeGovernance = activeTask ? governanceByTask[activeTask.id] ?? emptyGovernanceReadState() : emptyGovernanceReadState();
  const activeGovernanceReport = activeGovernance.report;
  const activeGovernanceError = activeGovernance.error;
  const activeProjectGovernanceHistory = project
    ? governanceHistoryByProject[project.id] ?? emptyProjectGovernanceHistoryReadState()
    : emptyProjectGovernanceHistoryReadState();

  useEffect(() => {
    if (
      !activeTask ||
      !activeGovernanceReport ||
      activeGovernanceReport.decision !== "ALLOW" ||
      activeTask.status !== "ACTION_PENDING" ||
      executionDispatchRef.current === activeTask.id
    ) {
      return;
    }
    executionDispatchRef.current = activeTask.id;
    setHarnessProgress("正在执行改动");
    void api.executeTask(activeTask.id, onlineSafeProfile ? "APPLY_APPROVED_CHANGES" : "RUN_COMMAND")
      .then(async (result) => {
        if (result.task) {
          applyTaskSnapshot(result.task);
        }
        await reconcileTaskProjection(activeTask.id);
        scheduleFileChangesRefresh(activeTask.id);
        setHarnessProgress(null);
      })
      .catch((error) => {
        setExecutionError(userError(error));
        setHarnessProgress(null);
        void reconcileTaskProjection(activeTask.id);
      });
  }, [activeGovernanceReport, activeTask, api, applyTaskSnapshot, onlineSafeProfile, reconcileTaskProjection, scheduleFileChangesRefresh]);

  const approveGovernance = useCallback(async () => {
    if (!activeGovernanceReport?.approvalRequestId) {
      return;
    }
    setApprovalAction("allow");
    try {
      await api.approveRequest(activeGovernanceReport.approvalRequestId, activeGovernanceReport.impactScope.files);
      setApprovalGranted(true);
    } catch (error) {
      setExecutionError(userError(error));
    } finally {
      setApprovalAction(null);
    }
  }, [activeGovernanceReport, api]);

  const denyGovernance = useCallback(async () => {
    if (!activeGovernanceReport?.approvalRequestId) {
      return;
    }
    const taskId = activeTask?.id ?? null;
    const setActiveGovernanceError = (message: string) => {
      if (!taskId) {
        return;
      }
      setGovernanceByTask((current) => ({
        ...current,
        [taskId]: {
          ...(current[taskId] ?? emptyGovernanceReadState()),
          error: message,
        },
      }));
    };
    setApprovalAction("deny");
    try {
      await api.rejectApproval(activeGovernanceReport.approvalRequestId);
      setActiveGovernanceError("本次授权没有通过");
    } catch (error) {
      setActiveGovernanceError(userError(error));
    } finally {
      setApprovalAction(null);
    }
  }, [activeGovernanceReport, activeTask?.id, api]);
  const cancelExecution = useCallback(async () => {
    if (!activeTask || cancelPending) {
      return;
    }
    setCancelPending(true);
    const taskId = activeTask.id;
    try {
      const result = await api.cancelTask(taskId);
      if (result.task) {
        applyTaskSnapshot(result.task);
      } else {
        applyTaskSnapshot({ ...activeTask, status: result.status === "CANCEL_REQUESTED" ? "CANCEL_REQUESTED" : activeTask.status });
      }
      void reconcileTaskProjection(taskId);
    } catch (error) {
      setExecutionError(userError(error));
    } finally {
      setCancelPending(false);
    }
  }, [activeTask, api, applyTaskSnapshot, cancelPending, reconcileTaskProjection]);

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

  const loadProjectEvaluations = useCallback(async () => {
    if (!project) {
      setProjectEvaluations(null);
      setEvaluationError(null);
      return;
    }
    setEvaluationLoading(true);
    setEvaluationError(null);
    try {
      setProjectEvaluations(await api.getProjectEvaluations(project.id));
    } catch (error) {
      setEvaluationError(userError(error));
    } finally {
      setEvaluationLoading(false);
    }
  }, [api, project]);

  useEffect(() => {
    if (activeView === "evaluation") {
      void loadProjectEvaluations();
    }
  }, [activeView, loadProjectEvaluations]);

  const saveCredential = useCallback(
    async (key: string | null, baseUrl: string, model: string) => {
      setCredentialPending("save");
      setCredentialError(null);
      try {
        const status = credentialStatus?.configured
          ? await api.updateCredential("openai-compatible", key, baseUrl, model)
          : key
            ? await api.setCredential("openai-compatible", key, baseUrl, model)
            : credentialStatus;
        if (!status) {
          setCredentialError("API Key is required before saving a new model service.");
          return;
        }
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

  const downloadProjectZip = useCallback(async () => {
    if (!project) {
      return;
    }
    setProjectError(null);
    try {
      downloadBlob(await api.exportProjectZip(project.id), "se-mentor-project.zip");
    } catch (error) {
      setProjectError(userError(error));
    }
  }, [api, project]);

  const downloadProjectPatch = useCallback(async () => {
    if (!project) {
      return;
    }
    setProjectError(null);
    try {
      downloadBlob(await api.exportProjectPatch(project.id), "se-mentor-changes.patch");
    } catch (error) {
      setProjectError(
        isApiErrorCode(error, "ONLINE_SAFE_PATCH_EXPORT_UNTRACKED_UNSUPPORTED")
          ? "当前变更包含新建文件，Patch 下载暂不支持未跟踪文件；请下载完整项目 ZIP。"
          : userError(error),
      );
    }
  }, [api, project]);

  const conversationMessages = activeTask
    ? conversationMessagesForTask(
        activeTask.id,
        persistedWorkbenchMessagesByTask,
        optimisticWorkbenchMessagesByTask,
      )
    : [];
  const activeTimelineItems = activeTask
    ? timelineItemsForTask(activeTask.id, timelineByTask, timelineErrorByTask)
    : [];
  const startNewTask = () => {
    hydrationRunRef.current += 1;
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
      projectHydrationState={projectHydrationState}
      projectOpening={projectOpening}
      taskCount={tasks.length}
      onlineSafe={onlineSafeProfile}
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
            changes={fileChangesByTask[activeTask.id] ?? []}
            changesError={fileChangesErrorByTask[activeTask.id] ?? null}
            changesHasLoaded={Object.prototype.hasOwnProperty.call(fileChangesByTask, activeTask.id)}
            changesLoading={fileChangesLoadingByTask[activeTask.id] ?? false}
            conversationMessages={conversationMessages}
            error={taskError}
            governanceError={activeGovernanceError}
            governanceReport={activeGovernanceReport}
            harnessProgress={harnessProgress}
            loading={taskDetailLoading}
            pendingAction={proposalAction}
            proposal={activeProposal}
            proposalState={proposalQueryState}
            stage={newTaskStage}
            task={activeTask}
            timelineItems={activeTimelineItems}
            onAllowGovernance={approveGovernance}
            onCancel={async () => undefined}
            onConfirm={confirmProposal}
            onDenyGovernance={denyGovernance}
            onOpenChanges={() => ensureTaskFileChanges(activeTask.id)}
            onOpenGovernance={() => setActiveView("governance")}
            onRetryProposal={retryProposal}
            onSubmitTurn={submitMentorTurn}
          />
        ) : (
          <NewTaskPage
            booting={projectHydrationState === "BOOTING"}
            disabled={!project || projectHydrationState === "BOOTING"}
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
          onlineSafe={onlineSafeProfile}
          project={project}
          tasks={tasks}
          onDownloadPatch={downloadProjectPatch}
          onDownloadZip={downloadProjectZip}
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
          detail={activeProjectGovernanceHistory.detail}
          detailError={activeProjectGovernanceHistory.detailError}
          detailLoading={activeProjectGovernanceHistory.detailLoading}
          error={activeProjectGovernanceHistory.error}
          hasMore={activeProjectGovernanceHistory.hasMore}
          history={activeProjectGovernanceHistory.items}
          loading={activeProjectGovernanceHistory.initialStatus === "LOADING" && activeProjectGovernanceHistory.items.length === 0}
          loadingMore={activeProjectGovernanceHistory.loadingMore}
          pendingAction={approvalAction}
          refreshing={activeProjectGovernanceHistory.refreshing}
          selectedDecisionId={activeProjectGovernanceHistory.selectedDecisionId}
          state={activeProjectGovernanceHistory.initialStatus}
          onAllowOnce={approveGovernance}
          onDeny={denyGovernance}
          onLoadMore={() => void loadMoreProjectGovernanceHistory()}
          onReload={() => void loadProjectGovernanceHistory()}
          onSelectDecision={(decision) => void loadGovernanceDecisionDetail(decision)}
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
            evaluations={projectEvaluations?.items ?? []}
            loading={evaluationLoading}
            task={activeTask}
            validationResults={validationResults}
          />
        )
      ) : null}
      {activeView === "settings" ? (
        <SettingsViewV2
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
        <EmptyState title="正在读取记忆" body="Mentor 正在读取后端知识库。" />
      </Page>
    );
  }
  return (
    <Page title="记忆">
      {error ? <EmptyState title="记忆读取失败" body={error} /> : null}
      {!error && items.length === 0 ? (
        <EmptyState title="还没有已复核的记忆" body="Mentor 捕获并复核项目知识后，会显示在这里。" />
      ) : null}
      {!error && items.length > 0 ? (
        <div className="memory-list">
          {items.map((item) =>
            item.presentation ? (
              <PresentedMemory item={item} key={item.id} />
            ) : (
              <article className="memory-item" key={item.id}>
                <div className="memory-status">{knowledgeStatusLabel(item.status)}</div>
                <h2>{item.key}</h2>
                <p>{item.summary}</p>
                <div className="memory-meta">
                  <span>{item.type}</span>
                  <span>{item.scope.join(", ") || "范围暂不可用"}</span>
                </div>
              </article>
            ),
          )}
        </div>
      ) : null}
    </Page>
  );
}

function PresentedMemory({ item }: { item: KnowledgeItem }) {
  const presentation = item.presentation;
  if (!presentation) {
    return null;
  }
  return (
    <article className="memory-item project-understanding">
      <div className="memory-status">{presentation.statusLabel}</div>
      <h2>{presentation.title}</h2>
      <p>{presentation.summary}</p>
      <MemorySection title="项目类型" values={presentation.projectType ? [presentation.projectType] : []} />
      <MemorySection title="技术栈" values={presentation.techStack} />
      <MemorySection title="项目规模" values={presentation.scale} />
      <MemorySection title="关键模块" values={presentation.modules} />
      <MemorySection title="关键路径" values={presentation.keyPaths} />
      <MemorySection title="治理决策" values={presentation.decision ? [presentation.decision] : []} />
      <MemorySection title="风险与约束" values={presentation.risks} />
      <details className="memory-details">
        <summary>技术详情</summary>
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

export function SettingsViewV2({
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
  onSaveCredential: (key: string | null, baseUrl: string, model: string) => Promise<void>;
  project: Project | null;
}) {
  const projectPath = project?.rootPath ?? "\u5c1a\u672a\u9009\u62e9\u9879\u76ee";
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const configured = credentialStatus?.configured ?? false;
  const cloudDemo = isCloudDemoCredentialStatus(credentialStatus);
  const onlineSafe = isOnlineSafeCredentialStatus(credentialStatus);
  useEffect(() => {
    setBaseUrl(credentialStatus?.baseUrl ?? "");
    setModel(credentialStatus?.model ?? "");
  }, [credentialStatus?.baseUrl, credentialStatus?.model]);
  const submitCredential = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const key = apiKey.trim();
    const trimmedBaseUrl = baseUrl.trim();
    const trimmedModel = model.trim();
    if ((!configured && !key) || !trimmedBaseUrl || !trimmedModel || credentialPending !== null) {
      return;
    }
    await onSaveCredential(key || null, trimmedBaseUrl, trimmedModel);
    setApiKey("");
  };

  return (
    <Page title="设置">
      <div className="settings-grid">
        <EmptyState title="项目" body={`\u5f53\u524d\u9879\u76ee\uff1a${projectPath}`} />
        <section className="setting-card">
          <div className="setting-head">
            <div className="setting-title">
              {cloudDemo ? "\u6f14\u793a\u6a21\u5f0f" : "\u6a21\u578b\u670d\u52a1"}
            </div>
            <span className={`setting-status ${configured ? "" : "neutral"}`}>
              {cloudDemo ? "Mock" : configured ? "\u5df2\u914d\u7f6e" : "\u672a\u914d\u7f6e"}
            </span>
          </div>
          {cloudDemo ? (
            <div className="setting-row credential-row">
              <div className="setting-label">CLOUD_DEMO</div>
              <div className="setting-value">
                {"\u5f53\u524d\u4f7f\u7528\u5185\u7f6e Mock \u6a21\u578b\uff0c\u65e0\u9700 API Key\u3002"}
                <span className="setting-sub">
                  {"\u6765\u6e90\uff1a"}{credentialStatus?.source ?? "CLOUD_DEMO"}
                </span>
              </div>
            </div>
          ) : null}
          {!cloudDemo ? (
            <form className="setting-row credential-row" onSubmit={submitCredential}>
              <div className="setting-label">OpenAI {"\u517c\u5bb9\u63a5\u53e3"}</div>
              <div className="setting-value">
                {onlineSafe
                  ? "\u51ed\u636e\u4ec5\u4fdd\u5b58\u5728\u5f53\u524d\u5728\u7ebf\u4f1a\u8bdd\u4e2d\uff0c\u8fde\u7eed 12 \u5c0f\u65f6\u65e0\u6d3b\u52a8\u540e\u81ea\u52a8\u6e05\u9664\u3002"
                  : configured
                    ? "LLM \u5df2\u914d\u7f6e\u3002\u7559\u7a7a API Key \u4f1a\u7ee7\u7eed\u4f7f\u7528\u5df2\u4fdd\u5b58\u7684\u5bc6\u94a5\u3002"
                    : "\u914d\u7f6e LLM API Key \u540e\uff0cMentor \u624d\u80fd\u751f\u6210\u65b9\u6848\u548c\u5206\u6790\u6539\u52a8\u3002"}
                <span className="setting-sub">
                  {"\u6765\u6e90\uff1a"}{credentialStatus?.source ?? "\u672a\u914d\u7f6e"}
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
                    placeholder={"\u670d\u52a1\u5546\u5b9e\u9645 model id"}
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
                  placeholder={
                    configured
                      ? "\u4fdd\u7559\u5f53\u524d\u4f1a\u8bdd\u4e2d\u7684 API Key"
                      : "\u8f93\u5165 API Key"
                  }
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
                  disabled={
                    (!configured && !apiKey.trim()) ||
                    !baseUrl.trim() ||
                    !model.trim() ||
                    credentialPending !== null
                  }
                  size="small"
                  type="submit"
                >
                  {credentialPending === "save"
                    ? "\u4fdd\u5b58\u4e2d"
                    : configured
                      ? "\u66f4\u65b0\u6a21\u578b\u670d\u52a1"
                      : "\u4fdd\u5b58\u6a21\u578b\u670d\u52a1"}
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
                    {credentialPending === "clear" ? "\u6e05\u9664\u4e2d" : "\u6e05\u9664 Key"}
                  </Button>
                ) : null}
              </div>
            </form>
          ) : null}
        </section>
      </div>
    </Page>
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
  onSaveCredential: (key: string | null, baseUrl: string, model: string) => Promise<void>;
  project: Project | null;
}) {
  const projectPath = project?.rootPath ?? "尚未选择项目";
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
    if ((!configured && !key) || !trimmedBaseUrl || !trimmedModel || credentialPending !== null) {
      return;
    }
    await onSaveCredential(key || null, trimmedBaseUrl, trimmedModel);
    setApiKey("");
  };

  return (
    <Page title="设置">
      <div className="settings-grid">
        <EmptyState title="项目" body={`当前项目：${projectPath}`} />
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
                ? "LLM 已配置。留空 API Key 会继续使用已保存的密钥。"
                : "配置 LLM API Key 后，Mentor 才能生成方案和分析改动。"}
              <span className="setting-sub">
                来源：{credentialStatus?.source ?? "未配置"}
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
                placeholder={configured ? "保留已保存的 API Key" : "输入 API Key"}
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
                disabled={(!configured && !apiKey.trim()) || !baseUrl.trim() || !model.trim() || credentialPending !== null}
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
    id: proposal.id,
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

function timelineItemFromRecord(taskId: string, record: TaskTimelineItem): WorkbenchTimelineItem {
  return {
    action: record.action,
    body: record.body,
    createdAt: record.createdAt,
    id: record.id,
    status: record.status,
    taskId,
    title: record.title,
  };
}

function timelineItemsForTask(
  taskId: string,
  persisted: Record<string, WorkbenchTimelineItem[]>,
  errors: Record<string, string | null>,
): WorkbenchTimelineItem[] {
  const items = persisted[taskId] ?? [];
  const error = errors[taskId];
  if (!error) {
    return items;
  }
  return [
    ...items,
    {
      body: error,
      createdAt: "now",
      id: `${taskId}:timeline-error`,
      status: "FAILED",
      taskId,
      title: "\u8fc7\u7a0b\u8bb0\u5f55\u8bfb\u53d6\u5931\u8d25",
    },
  ];
}

export function shouldRenderProjectEmpty(state: ProjectHydrationState, projectsLoaded: boolean): boolean {
  return state === "EMPTY" && projectsLoaded;
}

export function upsertTasks(current: Task[], updates: Task[]): Task[] {
  const byId = new Map(current.map((task) => [task.id, task]));
  for (const task of updates) {
    byId.set(task.id, task);
  }
  return Array.from(byId.values());
}

export function replaceTasksForProject(current: Task[], projectId: string, next: Task[]): Task[] {
  const retained = current.filter((task) => task.projectId !== projectId);
  return [...retained, ...dedupeBy(next, (task) => task.id)];
}

export function dedupeTimelineItems(items: WorkbenchTimelineItem[]): WorkbenchTimelineItem[] {
  return dedupeBy(items, (item) => item.id);
}

export function dedupeGovernanceHistory(items: ProjectGovernanceHistoryItem[]): ProjectGovernanceHistoryItem[] {
  return dedupeBy(items, (item) => item.governanceDecisionId);
}

function emptyGovernanceReadState(): GovernanceReadState {
  return {
    error: null,
    initialStatus: "UNINITIALIZED",
    refreshing: false,
    report: null,
  };
}

function emptyProjectGovernanceHistoryReadState(): ProjectGovernanceHistoryReadState {
  return {
    detail: null,
    detailError: null,
    detailLoading: false,
    error: null,
    hasMore: false,
    initialStatus: "UNINITIALIZED",
    items: [],
    loadingMore: false,
    nextOffset: null,
    refreshing: false,
    selectedDecisionId: null,
  };
}

export function shouldRenderGovernanceInitialLoading(
  governance: Pick<GovernanceReadState, "initialStatus" | "report" | "refreshing">,
): boolean {
  return !governance.report && governance.initialStatus === "LOADING";
}

export function shouldRenderChangesInitialLoading({
  hasLoaded,
  itemCount,
  loading,
}: {
  hasLoaded: boolean;
  itemCount: number;
  loading: boolean;
}): boolean {
  return loading && !hasLoaded && itemCount === 0;
}

export function shouldRenderChangesEmpty({
  hasLoaded,
  itemCount,
  loading,
}: {
  hasLoaded: boolean;
  itemCount: number;
  loading: boolean;
}): boolean {
  return hasLoaded && itemCount === 0 && !loading;
}

function conversationMessagesForTask(
  taskId: string,
  persisted: Record<string, WorkbenchMessage[]>,
  optimistic: Record<string, WorkbenchMessage[]>,
): WorkbenchMessage[] {
  return dedupeWorkbenchMessages([...(persisted[taskId] ?? []), ...(optimistic[taskId] ?? [])]);
}

function reconcileOptimisticMessages(
  optimistic: WorkbenchMessage[],
  persisted: WorkbenchMessage[],
): WorkbenchMessage[] {
  return optimistic.filter((message) => !persisted.some((item) => sameWorkbenchMessage(item, message)));
}

function sameWorkbenchMessage(a: WorkbenchMessage, b: WorkbenchMessage): boolean {
  const aProposalKey = proposalMessageKey(a);
  const bProposalKey = proposalMessageKey(b);
  if (aProposalKey && bProposalKey) {
    return aProposalKey === bProposalKey;
  }
  return a.role === b.role && a.kind === b.kind && a.status === b.status && a.text === b.text;
}

export function dedupeWorkbenchMessages(messages: WorkbenchMessage[]): WorkbenchMessage[] {
  const seen = new Set<string>();
  const result: WorkbenchMessage[] = [];
  for (const message of messages) {
    const key = proposalMessageKey(message) ?? `message:${message.id}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(message);
  }
  return result;
}

function proposalMessageKey(message: WorkbenchMessage): string | null {
  if (!message.proposal) {
    return null;
  }
  return `proposal:${message.taskId}:${message.proposal.id ?? "unknown"}:${message.proposal.version ?? "unknown"}`;
}

function dedupeBy<T>(items: T[], keyOf: (item: T) => string): T[] {
  const seen = new Set<string>();
  const result: T[] = [];
  for (const item of items) {
    const key = keyOf(item);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(item);
  }
  return result;
}

function knowledgeStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    CANDIDATE: "待复核",
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
  return "请求未完成。";
}
function isApiErrorCode(error: unknown, code: string): boolean {
  return error instanceof MentorApiError && error.code === code;
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
