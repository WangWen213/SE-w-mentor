export type TaskStatus =
  | "CREATED"
  | "WAITING_FOR_LOCK"
  | "INITIALIZING"
  | "CONTEXT_BUILDING"
  | "DECIDING"
  | "PROPOSAL_REVIEW"
  | "GOVERNING"
  | "APPROVAL_REQUIRED"
  | "ACTION_PENDING"
  | "NEEDS_INFORMATION"
  | "PROPOSAL_CONFIRMED"
  | "EXECUTING"
  | "RUNNING"
  | "VALIDATING"
  | "REPAIRING"
  | "STAGNATION_WARNING"
  | "PAUSED"
  | "KNOWLEDGE_UPDATING"
  | "ROLLING_BACK"
  | "COMPLETED"
  | "FAILED"
  | "BLOCKED"
  | "CANCELLED"
  | "CANCEL_REQUESTED"
  | "ROLLED_BACK";

export type ProposalStatus = "DRAFT" | "CONFIRMED" | "REJECTED" | "SUPERSEDED";
export type GovernanceDecisionKind = "ALLOW" | "WARN" | "BLOCK";
export type ApprovalStatus = "APPROVED" | "REJECTED";
export type ExecutionStatus = "COMPLETED" | "EXECUTING" | "CANCEL_REQUESTED" | "CANCELLED" | "FAILED";
export type TaskEventType =
  | "ACTION_COMPLETED"
  | "ACTION_STARTED"
  | "ACTION_GOVERNED"
  | "EXECUTION_COMPLETED"
  | "EXECUTION_FAILED"
  | "EXECUTION_STARTED"
  | "FILE_CHANGED"
  | "GOVERNANCE_DECIDED"
  | "TASK_COMPLETED"
  | "TASK_CANCELLED"
  | "TASK_FAILED"
  | "TOOL_COMPLETED"
  | "VALIDATION_COMPLETED"
  | "CANCEL_REQUESTED"
  | "status";
export type ValidationStatus = "PASS" | "FAIL" | "SKIPPED";
export type CompletionGateStatus = "PASS" | "FAIL" | "PENDING";

export interface ApiErrorInfo {
  code: string;
  actualKeys?: string[];
  expectedKeys?: string[];
  message: string;
  validationErrors?: ApiValidationError[];
}

export interface ApiValidationError {
  message?: string;
  path: string;
  type: string;
}

interface Envelope<T> {
  data: T | null;
  error: ApiErrorInfo | null;
  meta: Record<string, unknown>;
}

export interface Project {
  id: string;
  authorized: boolean;
  bootstrap?: ProjectBootstrap;
  rootPath?: string;
  branch?: string;
}

export interface ProjectBootstrap {
  error?: string;
  message?: string;
  readiness?: Record<string, unknown>;
  status: "REGISTERED" | "BOOTSTRAPPING" | "READY" | "BOOTSTRAP_FAILED";
}

export interface ProjectConfig {
  projectId: string;
  secrets: string;
}

export interface ProjectList {
  items: Project[];
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
  acceptanceCriteria?: string[];
  assumptions?: Record<string, unknown>;
  changes?: ProposalChange[];
  completeness?: ProposalCompletenessInfo;
  constraints?: string[];
  currentProblem?: string | null;
  display?: ProposalDisplay;
  executionBoundary?: string[];
  expectedBehavior?: string;
  id: string;
  goal: string;
  items: string[];
  impact: string;
  risk: string;
  missingInformationQuestion: string | null;
  nonGoals?: string[];
  risks?: Record<string, unknown>;
  scope?: string[];
  steps?: string[];
  status: ProposalStatus;
  supersedesId?: string | null;
  target?: string;
  taskId: string;
  understanding?: string;
  validation?: string[];
  version: number;
}

export interface ProposalCompletenessInfo {
  canConfirm: boolean;
  decision: "COMPLETE" | "NEEDS_MORE_TECHNICAL_ANALYSIS" | "NEEDS_USER_CLARIFICATION";
  technicalUnknowns: string[];
  userDecisions: string[];
}

export interface ProposalDisplay {
  expectedImpact: string[];
  goal: string;
  needsUserDecision: string[];
  nonGoals: string[];
  preparedChanges: ProposalDisplayChange[];
  risks: string[];
  scope: string[];
  steps: string[];
  technicalUnknowns: string[];
  title: string;
  understanding: string;
  validation: string[];
}

export interface ProposalDisplayChange {
  action: string;
  path: string;
  reason: string;
  symbol?: string | null;
}

export interface ProposalChange {
  action: string;
  path: string;
  reason: string;
  symbol?: string | null;
}

export interface ProposalHistory {
  items: Proposal[];
  taskId: string;
}

export type WorkbenchMessageRole = "MENTOR" | "SYSTEM" | "USER";
export type WorkbenchMessageKind = "ERROR" | "PROGRESS" | "PROPOSAL" | "TEXT";

export interface WorkbenchMessageRecord {
  createdAt: string;
  id: string;
  kind: WorkbenchMessageKind;
  proposal?: Proposal | null;
  role: WorkbenchMessageRole;
  sequence: number;
  status: "DONE" | "ERROR" | "PENDING";
  taskId: string;
  text: string;
}

export interface WorkbenchMessageList {
  items: WorkbenchMessageRecord[];
  taskId: string;
}

export type TaskTimelineKind =
  | "PROPOSAL_READY"
  | "PROPOSAL_CONFIRMED"
  | "IMPACT_READY"
  | "GOVERNANCE_ALLOW"
  | "GOVERNANCE_APPROVAL_REQUIRED"
  | "GOVERNANCE_BLOCK"
  | "LOCATING"
  | "TARGET_LOCATED"
  | "EXECUTION_STARTED"
  | "FILE_CHANGED"
  | "VALIDATION_STARTED"
  | "VALIDATION_COMPLETED"
  | "TASK_COMPLETED"
  | "TASK_CANCELLED"
  | "TASK_FAILED"
  | "TASK_STATUS";

export type TaskTimelineStatus = "SUCCESS" | "RUNNING" | "WAITING" | "FAILED";
export type TaskTimelineTarget = "changes" | "checks" | "governance";

export interface TaskTimelineAction {
  label: string;
  target: TaskTimelineTarget;
}

export interface TaskTimelineItem {
  action?: TaskTimelineAction;
  body: string;
  createdAt: string;
  id: string;
  kind: TaskTimelineKind;
  sequence: number;
  source: {
    id: string;
    type: string;
  };
  status: TaskTimelineStatus;
  title: string;
}

export interface TaskTimeline {
  count: number;
  items: TaskTimelineItem[];
  taskId: string;
}

export interface MentorTurnResult {
  message: WorkbenchMessageRecord | null;
  proposal: Proposal | null;
  type: "ANSWER" | "CHANGE_REQUEST" | "PROPOSAL_REVISION";
}

export interface CredentialStatus {
  baseUrl?: string | null;
  configured: boolean;
  model?: string | null;
  provider: string;
  source: string;
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
  governanceDecisionId?: string;
  taskId?: string;
  approvalRequestId?: string | null;
  approvalStatus?: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | null;
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

export interface ProjectGovernanceHistoryItem {
  affectedFileCount: number;
  blocked: boolean;
  createdAt: string;
  decision: GovernanceDecisionKind;
  displaySummary: string;
  governanceDecisionId: string;
  proposalId?: string | null;
  proposalVersion?: number | null;
  reasonCode: string;
  requiresApproval: boolean;
  summary: string;
  taskId: string;
  taskTitle: string;
}

export interface ProjectGovernanceHistory {
  hasMore: boolean;
  items: ProjectGovernanceHistoryItem[];
  limit: number;
  nextOffset?: number | null;
  offset: number;
  projectId: string;
}

export interface AnalysisIndexResult {
  evidenceRef: string;
  status: "INDEXED";
}

export interface KnowledgeItem {
  evidenceRefs: string[];
  id: string;
  key: string;
  presentation?: KnowledgePresentation | null;
  scope: string[];
  status: string;
  summary: string;
  type: string;
}

export interface KnowledgePresentation {
  decision?: string | null;
  details: Record<string, unknown>;
  gitBaseline?: string[];
  keyPaths: string[];
  kind: string;
  modules: string[];
  projectType?: string | null;
  risks: string[];
  scale: string[];
  statusLabel: string;
  structure?: string[];
  summary: string;
  techStack: string[];
  tests?: string[];
  title: string;
}

export interface KnowledgeList {
  items: KnowledgeItem[];
  projectId: string;
}

export interface ProjectEvaluationList {
  items: TaskEvaluation[];
  projectId: string;
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
  task?: Task;
  taskId: string;
}

export interface DiffLine {
  content: string;
  lineNumber: number;
  outsideScope: boolean;
  type: "added" | "removed" | "context";
}

export type FileChangeOperation = "CREATE" | "MODIFY" | "DELETE";

export interface DiffTrace {
  actionId?: string | null;
  afterHash?: string | null;
  backedUp: boolean;
  beforeHash?: string | null;
  changeId: string;
  diff: string;
  evidence?: Record<string, unknown>;
  filePath: string;
  lines: DiffLine[];
  modified: boolean;
  operation?: FileChangeOperation;
  projectId?: string;
  relativePath?: string;
  rolledBack: boolean;
  taskId?: string;
  toolExecutionId?: string | null;
  transactionId?: string | null;
}

export interface TaskFileChanges {
  count: number;
  items: DiffTrace[];
  taskId: string;
}

export interface ValidationResult {
  failureCategory: string | null;
  message: string;
  name: string;
  status: ValidationStatus;
}

export interface CompletionGate {
  label: string;
  status: CompletionGateStatus;
}

export interface RecoveryItem {
  conflict: boolean;
  sideEffects: string;
  status: string;
  taskId: string;
}

export interface RecoveryList {
  items: RecoveryItem[];
}

export interface RecoveryResolution {
  action: "keep" | "rollback";
  status: string;
  taskId: string;
}

export interface TaskEvaluation {
  changeQuality: EvaluationChangeQuality;
  createdAt?: string;
  evidence: EvaluationEvidence;
  evaluationId?: string;
  execution?: Record<string, unknown>;
  governance: EvaluationGovernance;
  hasEvaluation: boolean;
  memoryCandidates?: Array<Record<string, unknown>>;
  overall: EvaluationOverall;
  projectId?: string;
  requirementCoverage: EvaluationRequirementCoverage;
  taskTitle?: string;
  taskId: string;
  validation: EvaluationValidation;
}

export interface EvaluationOverall {
  status: string;
  summary: string;
  title: string;
}

export interface EvaluationRequirementCoverage {
  covered: EvaluationValue[];
  summary: string;
  uncovered: EvaluationValue[];
}

export interface EvaluationChangeQuality {
  risks: EvaluationValue[];
  scope: EvaluationValue[];
  summary: string;
}

export interface EvaluationGovernance {
  decision: string;
  reason: string;
  requiresApproval: boolean;
}

export interface EvaluationValidation {
  executed: EvaluationValue[];
  failed: EvaluationValue[];
  notRun: EvaluationValue[];
  planned: EvaluationValue[];
}

export interface EvaluationEvidence {
  summary: string[];
  technical: Record<string, unknown>;
}

export type EvaluationValue = string | Record<string, unknown>;

export interface TaskEvent {
  eventId: number;
  eventType: TaskEventType;
  payload: {
    changeId?: string;
    completionGate?: CompletionGate[];
    message?: string;
    projectId?: string;
    state?: string;
    taskId?: string;
    validation?: ValidationResult[];
  };
  taskId: string;
}

export class MentorApiError extends Error {
  readonly actualKeys?: string[];
  readonly code: string;
  readonly expectedKeys?: string[];
  readonly status: number;
  readonly validationErrors?: ApiValidationError[];

  constructor(status: number, error: ApiErrorInfo) {
    super(error.message);
    this.name = "MentorApiError";
    this.actualKeys = error.actualKeys;
    this.code = error.code;
    this.expectedKeys = error.expectedKeys;
    this.status = status;
    this.validationErrors = error.validationErrors;
  }
}

export interface MentorApi {
  adjustProposal(taskId: string, proposalId: string, instruction: string): Promise<Proposal>;
  cancelProposal(taskId: string, proposalId: string): Promise<Proposal>;
  chooseLocalProject(): Promise<Project>;
  clearCredential(): Promise<CredentialStatus>;
  confirmProposal(taskId: string, proposalId: string): Promise<Proposal>;
  createProject(rootPath: string): Promise<Project>;
  createWorkbenchMessage(
    taskId: string,
    message: Pick<WorkbenchMessageRecord, "kind" | "role" | "status" | "text"> & { proposalId?: string | null },
  ): Promise<WorkbenchMessageRecord>;
  createProposal(taskId: string, goal: string, question?: string): Promise<Proposal>;
  createTask(projectId: string, request: string): Promise<Task>;
  exportProjectPatch(projectId: string): Promise<Blob>;
  exportProjectZip(projectId: string): Promise<Blob>;
  getDiffTrace(changeId: string): Promise<DiffTrace>;
  getTaskFileChanges(taskId: string): Promise<TaskFileChanges>;
  getProjectBootstrap(projectId: string): Promise<ProjectBootstrap>;
  getProjectConfig(projectId: string): Promise<ProjectConfig>;
  getProjectLocks(projectId: string): Promise<LockStatus>;
  getProjects(): Promise<ProjectList>;
  getProposal(taskId: string): Promise<Proposal>;
  getProposalHistory(taskId: string): Promise<ProposalHistory>;
  getWorkbenchMessages(taskId: string): Promise<WorkbenchMessageList>;
  getGovernance(proposalId: string): Promise<GovernanceReport>;
  getGovernanceDecision(projectId: string, decisionId: string): Promise<GovernanceReport>;
  getProjectGovernanceHistory(
    projectId: string,
    options?: { limit?: number; offset?: number; taskId?: string | null },
  ): Promise<ProjectGovernanceHistory>;
  getProjectEvaluations(projectId: string): Promise<ProjectEvaluationList>;
  getTask(taskId: string): Promise<Task>;
  getTaskEvaluation(taskId: string): Promise<TaskEvaluation>;
  getTaskEvents(taskId: string, lastEventId: number | null): Promise<TaskEvent[]>;
  getTaskTimeline(taskId: string): Promise<TaskTimeline>;
  getTaskList(projectId: string): Promise<TaskList>;
  getCredentialStatus(): Promise<CredentialStatus>;
  indexAnalysis(): Promise<AnalysisIndexResult>;
  importProjectZip(file: File): Promise<Project>;
  approveRequest(approvalId: string, approvedScope: string[]): Promise<ApprovalResult>;
  rejectApproval(approvalId: string): Promise<ApprovalResult>;
  executeTask(taskId: string, command: string): Promise<ExecutionResult>;
  cancelTask(taskId: string): Promise<ExecutionResult>;
  createMentorTurn(taskId: string, text: string): Promise<MentorTurnResult>;
  listRecovery(): Promise<RecoveryList>;
  listKnowledge(projectId: string): Promise<KnowledgeList>;
  resolveRecovery(taskId: string, action: "keep" | "rollback"): Promise<RecoveryResolution>;
  runGovernance(proposalId: string, changedPaths: string[]): Promise<GovernanceReport>;
  setCredential(provider: string, key: string, baseUrl: string, model: string): Promise<CredentialStatus>;
  updateCredential(provider: string, key: string | null, baseUrl: string, model: string): Promise<CredentialStatus>;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export function createMentorApi(fetcher: FetchLike = fetch): MentorApi {
  const request = async <T>(input: string, init?: RequestInit): Promise<T> => {
    const response = await fetcher(input, {
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
    const body = await response.text();
    let payload: Envelope<T>;
    try {
      payload = JSON.parse(body) as Envelope<T>;
    } catch {
      throw new MentorApiError(response.status, {
        code: `HTTP_${response.status}`,
        message: body || response.statusText || "Server returned a non-JSON response",
      });
    }
    if (!response.ok || payload.error) {
      throw new MentorApiError(response.status, payload.error ?? {
        code: "API_ERROR",
        message: "Request did not complete",
      });
    }
    if (payload.data === null) {
      throw new MentorApiError(response.status, {
        code: "EMPTY_RESPONSE",
        message: "Server returned no data",
      });
    }
    return payload.data;
  };
  const requestBlob = async (input: string): Promise<Blob> => {
    const response = await fetcher(input);
    if (!response.ok) {
      const body = await response.text();
      try {
        const payload = JSON.parse(body) as Envelope<unknown>;
        throw new MentorApiError(response.status, payload.error ?? {
          code: "API_ERROR",
          message: "Request did not complete",
        });
      } catch (error) {
        if (error instanceof MentorApiError) {
          throw error;
        }
        throw new MentorApiError(response.status, {
          code: `HTTP_${response.status}`,
          message: body || response.statusText || "Download failed",
        });
      }
    }
    return response.blob();
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
    cancelProposal: (taskId, proposalId) =>
      request<Proposal>(`/api/tasks/${taskId}/proposals/${proposalId}/reject`, {
        method: "POST",
      }),
    cancelTask: (taskId) =>
      request<ExecutionResult>(`/api/tasks/${taskId}/cancel`, { method: "POST" }),
    chooseLocalProject: () =>
      request<Project>("/api/projects/choose-local", {
        method: "POST",
      }),
    clearCredential: () =>
      request<CredentialStatus>("/api/credentials/llm", {
        method: "DELETE",
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
    createWorkbenchMessage: (taskId, message) =>
      request<WorkbenchMessageRecord>(`/api/tasks/${taskId}/messages`, {
        body: JSON.stringify(message),
        method: "POST",
      }),
    createMentorTurn: (taskId, text) =>
      request<MentorTurnResult>(`/api/tasks/${taskId}/turns`, {
        body: JSON.stringify({ text }),
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
    exportProjectPatch: (projectId) =>
      requestBlob(`/api/projects/${projectId}/changes.patch`),
    exportProjectZip: (projectId) =>
      requestBlob(`/api/projects/${projectId}/export.zip`),
    executeTask: (taskId, command) =>
      request<ExecutionResult>(`/api/tasks/${taskId}/execute`, {
        body: JSON.stringify({ command }),
        method: "POST",
      }),
    getDiffTrace: (changeId) => request<DiffTrace>(`/api/diffs/${changeId}/trace`),
    getTaskFileChanges: (taskId) => request<TaskFileChanges>(`/api/diffs/tasks/${taskId}/changes`),
    getProjectBootstrap: (projectId) =>
      request<ProjectBootstrap>(`/api/projects/${projectId}/bootstrap`),
    getProjectConfig: (projectId) =>
      request<ProjectConfig>(`/api/projects/${projectId}/config`),
    getProjectLocks: (projectId) =>
      request<LockStatus>(`/api/projects/${projectId}/locks`),
    getProjects: () => request<ProjectList>("/api/projects"),
    getProposal: (taskId) => request<Proposal>(`/api/tasks/${taskId}/proposals`),
    getProposalHistory: (taskId) => request<ProposalHistory>(`/api/tasks/${taskId}/proposals/history`),
    getWorkbenchMessages: (taskId) => request<WorkbenchMessageList>(`/api/tasks/${taskId}/messages`),
    getGovernance: (proposalId) => request<GovernanceReport>(`/api/proposals/${proposalId}/governance`),
    getGovernanceDecision: (projectId, decisionId) =>
      request<GovernanceReport>(`/api/projects/${projectId}/governance-history/${decisionId}`),
    getProjectGovernanceHistory: (projectId, options = {}) => {
      const params = new URLSearchParams();
      if (options.limit !== undefined) {
        params.set("limit", String(options.limit));
      }
      if (options.offset !== undefined) {
        params.set("offset", String(options.offset));
      }
      if (options.taskId) {
        params.set("taskId", options.taskId);
      }
      const query = params.toString();
      return request<ProjectGovernanceHistory>(
        `/api/projects/${projectId}/governance-history${query ? `?${query}` : ""}`,
      );
    },
    getProjectEvaluations: (projectId) =>
      request<ProjectEvaluationList>(`/api/projects/${projectId}/evaluations`),
    getTask: (taskId) => request<Task>(`/api/tasks/${taskId}`),
    getTaskEvaluation: (taskId) => request<TaskEvaluation>(`/api/tasks/${taskId}/evaluation`),
    getTaskEvents: async (taskId, lastEventId) => {
      const response = await fetcher(`/api/tasks/${taskId}/events`, {
        headers: lastEventId === null ? {} : { "Last-Event-ID": String(lastEventId) },
      });
      if (!response.ok) {
        throw new MentorApiError(response.status, {
          code: "EVENT_STREAM_ERROR",
          message: "Task event stream was interrupted",
        });
      }
      return parseTaskEvents(taskId, await response.text());
    },
    getTaskTimeline: (taskId) => request<TaskTimeline>(`/api/tasks/${taskId}/timeline`),
    getTaskList: (projectId) => request<TaskList>(`/api/projects/${projectId}/tasks`),
    getCredentialStatus: () => request<CredentialStatus>("/api/credentials/llm/status"),
    importProjectZip: (file) =>
      request<Project>("/api/projects/import-zip", {
        body: file,
        headers: {
          "content-type": "application/zip",
          "x-se-mentor-filename": file.name,
        },
        method: "POST",
      }),
    indexAnalysis: () => request<AnalysisIndexResult>("/api/analysis/index", { method: "POST" }),
    listRecovery: () => request<RecoveryList>("/api/recovery"),
    listKnowledge: (projectId) => request<KnowledgeList>(`/api/projects/${projectId}/knowledge`),
    rejectApproval: (approvalId) =>
      request<ApprovalResult>(`/api/approvals/${approvalId}/reject`, { method: "POST" }),
    resolveRecovery: (taskId, action) =>
      request<RecoveryResolution>(`/api/recovery/${taskId}/resolve`, {
        body: JSON.stringify({ action }),
        method: "POST",
      }),
    runGovernance: (proposalId, changedPaths) =>
      request<GovernanceReport>(`/api/proposals/${proposalId}/governance`, {
        body: JSON.stringify({ changedPaths }),
        method: "POST",
      }),
    setCredential: (provider, key, baseUrl, model) =>
      request<CredentialStatus>("/api/credentials/llm", {
        body: JSON.stringify({ provider, key, baseUrl, model }),
        method: "POST",
      }),
    updateCredential: (provider, key, baseUrl, model) =>
      request<CredentialStatus>("/api/credentials/llm", {
        body: JSON.stringify({ provider, key, baseUrl, model }),
        method: "PUT",
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
    ALLOW: "\u81ea\u52a8\u5141\u8bb8",
    BLOCK: "\u59cb\u7ec8\u963b\u6b62",
    WARN: "\u9700\u8981\u4f60\u7684\u786e\u8ba4",
  };
  return labels[decision];
}

export function taskStateLabel(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    CANCELLED: "\u5df2\u53d6\u6d88",
    CANCEL_REQUESTED: "\u6b63\u5728\u505c\u6b62",
    COMPLETED: "\u5df2\u5b8c\u6210",
    ACTION_PENDING: "\u5f85\u6267\u884c",
    APPROVAL_REQUIRED: "\u9700\u8981\u786e\u8ba4",
    CONTEXT_BUILDING: "\u6b63\u5728\u6784\u5efa\u4e0a\u4e0b\u6587",
    CREATED: "\u5f85\u786e\u8ba4",
    DECIDING: "\u6b63\u5728\u5206\u6790",
    EXECUTING: "\u6b63\u5728\u6267\u884c",
    FAILED: "\u5df2\u5931\u8d25",
    BLOCKED: "\u5df2\u963b\u6b62",
    GOVERNING: "\u6cbb\u7406\u68c0\u67e5\u4e2d",
    INITIALIZING: "\u6b63\u5728\u521d\u59cb\u5316",
    KNOWLEDGE_UPDATING: "\u6b63\u5728\u66f4\u65b0\u8bb0\u5fc6",
    NEEDS_INFORMATION: "\u9700\u8865\u5145",
    PAUSED: "\u5df2\u6682\u505c",
    PROPOSAL_CONFIRMED: "\u65b9\u6848\u5df2\u786e\u8ba4",
    PROPOSAL_REVIEW: "\u65b9\u6848\u590d\u6838",
    REPAIRING: "\u6b63\u5728\u4fee\u590d",
    ROLLED_BACK: "\u5df2\u56de\u6eda",
    ROLLING_BACK: "\u6b63\u5728\u56de\u6eda",
    RUNNING: "\u6b63\u5728\u8fd0\u884c",
    STAGNATION_WARNING: "\u8fdb\u5c55\u505c\u6ede\u9884\u8b66",
    VALIDATING: "\u6b63\u5728\u9a8c\u8bc1",
    WAITING_FOR_LOCK: "\u7b49\u5f85\u9501",
  };
  return labels[status];
}

export function taskEventLabel(eventType: TaskEventType): string {
  const labels: Record<TaskEventType, string> = {
    ACTION_COMPLETED: "动作已完成",
    ACTION_GOVERNED: "动作已通过治理",
    ACTION_STARTED: "动作已开始",
    CANCEL_REQUESTED: "正在停止",
    TASK_CANCELLED: "任务已取消",
    EXECUTION_COMPLETED: "执行已完成",
    EXECUTION_FAILED: "执行失败",
    EXECUTION_STARTED: "正在修改",
    FILE_CHANGED: "文件已变更",
    GOVERNANCE_DECIDED: "治理已完成",
    TASK_COMPLETED: "任务已完成",
    TASK_FAILED: "任务失败",
    TOOL_COMPLETED: "工具已完成",
    VALIDATION_COMPLETED: "验证已完成",
    status: "状态已更新",
  };
  return labels[eventType];
}
