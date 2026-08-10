export type TaskStatus =
  | "CREATED"
  | "NEEDS_INFORMATION"
  | "PROPOSAL_CONFIRMED"
  | "EXECUTING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "CANCEL_REQUESTED"
  | "ROLLED_BACK";

export type ProposalStatus = "DRAFT" | "CONFIRMED" | "REJECTED" | "SUPERSEDED";
export type GovernanceDecisionKind = "ALLOW" | "WARN" | "BLOCK";
export type ApprovalStatus = "APPROVED" | "REJECTED";
export type ExecutionStatus = "EXECUTING" | "CANCEL_REQUESTED";
export type TaskEventType = "EXECUTION_STARTED" | "CANCEL_REQUESTED" | "status";

export interface ApiErrorInfo {
  code: string;
  message: string;
}

interface Envelope<T> {
  data: T | null;
  error: ApiErrorInfo | null;
  meta: Record<string, unknown>;
}

export interface Project {
  id: string;
  authorized: boolean;
  rootPath?: string;
  branch?: string;
}

export interface ProjectConfig {
  projectId: string;
  secrets: string;
}

export interface LockStatus {
  projectId: string;
  status: string;
}

export interface Task {
  id: string;
  projectId: string;
  request: string;
  status: TaskStatus;
}

export interface TaskList {
  projectId: string;
  items: Task[];
}

export interface Proposal {
  id: string;
  taskId: string;
  version: number;
  goal: string;
  items: string[];
  impact: string;
  risk: string;
  missingInformationQuestion: string | null;
  status: ProposalStatus;
}

export interface GovernanceEvidence {
  detail: string;
  file: string;
  label: string;
  line: number;
}

export interface GovernanceFact {
  file: string;
  line: number;
  summary: string;
}

export interface ImpactScope {
  files: string[];
  summary: string;
}

export interface RuleHit {
  label: string;
  level: GovernanceDecisionKind;
  reason: string;
}

export interface GovernanceReport {
  changedPaths: string[];
  decision: GovernanceDecisionKind;
  evidence: GovernanceEvidence[];
  evidenceRef: string;
  facts: GovernanceFact[];
  impactScope: ImpactScope;
  inferences: string[];
  nonApprovable: boolean;
  proposalId: string;
  ruleHits: RuleHit[];
  unknowns: string[];
}

export interface AnalysisIndexResult {
  evidenceRef: string;
  status: "INDEXED";
}

export interface TemporaryGrant {
  approvalId: string;
  id: string;
  scope: string[];
  status: "ACTIVE";
}

export interface ExecutionPolicy {
  approvalId: string;
  commands: string[];
  writeAllowed: boolean;
}

export interface ApprovalResult {
  approvedScope?: string[];
  executionPolicy?: ExecutionPolicy;
  id: string;
  status: ApprovalStatus;
  temporaryGrant?: TemporaryGrant;
}

export interface ExecutionResult {
  command?: string;
  eventId: number;
  status: ExecutionStatus;
  taskId: string;
}

export interface TaskEvent {
  eventId: number;
  eventType: TaskEventType;
  payload: {
    message?: string;
    projectId?: string;
    state?: string;
    taskId?: string;
  };
  taskId: string;
}

export class MentorApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, error: ApiErrorInfo) {
    super(error.message);
    this.name = "MentorApiError";
    this.code = error.code;
    this.status = status;
  }
}

export interface MentorApi {
  adjustProposal(taskId: string, proposalId: string, instruction: string): Promise<Proposal>;
  cancelProposal(taskId: string, proposalId: string): Promise<Proposal>;
  confirmProposal(taskId: string, proposalId: string): Promise<Proposal>;
  createProject(rootPath: string): Promise<Project>;
  createProposal(taskId: string, goal: string, question?: string): Promise<Proposal>;
  createTask(projectId: string, request: string): Promise<Task>;
  getProjectConfig(projectId: string): Promise<ProjectConfig>;
  getProposal(taskId: string): Promise<Proposal>;
  getTask(taskId: string): Promise<Task>;
  getTaskList(projectId: string): Promise<TaskList>;
  getProjectLocks(projectId: string): Promise<LockStatus>;
  indexAnalysis(): Promise<AnalysisIndexResult>;
  approveRequest(approvalId: string, approvedScope: string[]): Promise<ApprovalResult>;
  rejectApproval(approvalId: string): Promise<ApprovalResult>;
  executeTask(taskId: string, command: string): Promise<ExecutionResult>;
  cancelTask(taskId: string): Promise<ExecutionResult>;
  getTaskEvents(taskId: string, lastEventId: number | null): Promise<TaskEvent[]>;
  runGovernance(proposalId: string, changedPaths: string[]): Promise<GovernanceReport>;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export function createMentorApi(fetcher: FetchLike = fetch): MentorApi {
  const request = async <T>(input: string, init?: RequestInit): Promise<T> => {
    const response = await fetcher(input, {
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
    const payload = (await response.json()) as Envelope<T>;
    if (!response.ok || payload.error) {
      throw new MentorApiError(response.status, payload.error ?? {
        code: "API_ERROR",
        message: "请求没有完成",
      });
    }
    if (payload.data === null) {
      throw new MentorApiError(response.status, {
        code: "EMPTY_RESPONSE",
        message: "服务端没有返回数据",
      });
    }
    return payload.data;
  };

  return {
    adjustProposal: (taskId, proposalId, instruction) =>
      request<Proposal>(`/api/tasks/${taskId}/proposals/${proposalId}/adjust`, {
        body: JSON.stringify({ instruction }),
        method: "POST",
      }),
    approveRequest: (approvalId, approvedScope) =>
      request<ApprovalResult>(`/api/approvals/${approvalId}/approve`, {
        body: JSON.stringify({ approvedScope }),
        method: "POST",
      }),
    cancelTask: (taskId) =>
      request<ExecutionResult>(`/api/tasks/${taskId}/cancel`, { method: "POST" }),
    cancelProposal: (taskId, proposalId) =>
      request<Proposal>(`/api/tasks/${taskId}/proposals/${proposalId}/reject`, {
        method: "POST",
      }),
    confirmProposal: (taskId, proposalId) =>
      request<Proposal>(`/api/tasks/${taskId}/proposals/${proposalId}/confirm`, {
        method: "POST",
      }),
    createProject: (rootPath) =>
      request<Project>("/api/projects", {
        body: JSON.stringify({ rootPath }),
        method: "POST",
      }),
    createProposal: (taskId, goal, question) =>
      request<Proposal>(`/api/tasks/${taskId}/proposals`, {
        body: JSON.stringify({ goal, missingInformationQuestion: question ?? null }),
        method: "POST",
      }),
    createTask: (projectId, requestText) =>
      request<Task>("/api/tasks", {
        body: JSON.stringify({ projectId, request: requestText }),
        method: "POST",
      }),
    executeTask: (taskId, command) =>
      request<ExecutionResult>(`/api/tasks/${taskId}/execute`, {
        body: JSON.stringify({ command }),
        method: "POST",
      }),
    getProjectConfig: (projectId) =>
      request<ProjectConfig>(`/api/projects/${projectId}/config`),
    getProposal: (taskId) => request<Proposal>(`/api/tasks/${taskId}/proposals`),
    getProjectLocks: (projectId) =>
      request<LockStatus>(`/api/projects/${projectId}/locks`),
    getTask: (taskId) => request<Task>(`/api/tasks/${taskId}`),
    getTaskEvents: async (taskId, lastEventId) => {
      const response = await fetcher(`/api/tasks/${taskId}/events`, {
        headers: lastEventId === null ? {} : { "Last-Event-ID": String(lastEventId) },
      });
      if (!response.ok) {
        throw new MentorApiError(response.status, {
          code: "EVENT_STREAM_ERROR",
          message: "执行状态暂时中断",
        });
      }
      return parseTaskEvents(taskId, await response.text());
    },
    getTaskList: (projectId) => request<TaskList>(`/api/projects/${projectId}/tasks`),
    indexAnalysis: () => request<AnalysisIndexResult>("/api/analysis/index", { method: "POST" }),
    rejectApproval: (approvalId) =>
      request<ApprovalResult>(`/api/approvals/${approvalId}/reject`, { method: "POST" }),
    runGovernance: (proposalId, changedPaths) =>
      request<GovernanceReport>(`/api/proposals/${proposalId}/governance`, {
        body: JSON.stringify({ changedPaths }),
        method: "POST",
      }),
  };
}

export function parseTaskEvents(taskId: string, text: string): TaskEvent[] {
  return text
    .split("\n\n")
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const lines = block.split("\n");
      const idLine = lines.find((line) => line.startsWith("id: "));
      const eventLine = lines.find((line) => line.startsWith("event: "));
      const dataLine = lines.find((line) => line.startsWith("data: "));
      const eventId = Number(idLine?.slice(4) ?? 0);
      const eventType = (eventLine?.slice(7) ?? "status") as TaskEventType;
      const payload = JSON.parse(dataLine?.slice(6) ?? "{}") as TaskEvent["payload"];
      return { eventId, eventType, payload, taskId };
    });
}

export function governanceDecisionLabel(decision: GovernanceDecisionKind): string {
  const labels: Record<GovernanceDecisionKind, string> = {
    ALLOW: "自动允许",
    BLOCK: "始终阻止",
    WARN: "需要你的确认",
  };
  return labels[decision];
}

export function taskStateLabel(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    CANCELLED: "已取消",
    CANCEL_REQUESTED: "正在停止",
    COMPLETED: "已完成",
    CREATED: "待确认",
    EXECUTING: "进行中",
    FAILED: "失败",
    NEEDS_INFORMATION: "需补充",
    PROPOSAL_CONFIRMED: "已确认",
    ROLLED_BACK: "已回滚",
    RUNNING: "进行中",
  };
  return labels[status];
}

export function taskEventLabel(eventType: TaskEventType): string {
  const labels: Record<TaskEventType, string> = {
    CANCEL_REQUESTED: "正在停止",
    EXECUTION_STARTED: "正在修改",
    status: "状态已更新",
  };
  return labels[eventType];
}
