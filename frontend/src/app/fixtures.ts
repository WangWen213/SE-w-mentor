import type { ProposalChange, ProposalCompletenessInfo, ProposalDisplay, ProposalStatus } from "../api/mentorApi";

export type NavKey =
  | "workbench"
  | "tasks"
  | "memory"
  | "governance"
  | "evaluation"
  | "settings";

export type TaskTab = "conversation" | "changes" | "checks";

export type BadgeTone = "allow" | "warn" | "block" | "neutral" | "info";

export type WorkbenchMessageRole = "MENTOR" | "SYSTEM" | "USER";
export type WorkbenchMessageKind = "ERROR" | "PROGRESS" | "PROPOSAL" | "TEXT";

export interface WorkbenchMessage {
  createdAt: string;
  id: string;
  kind: WorkbenchMessageKind;
  proposal?: ProposalFixture;
  role: WorkbenchMessageRole;
  status?: "DONE" | "ERROR" | "PENDING";
  taskId: string;
  text: string;
}

export type WorkbenchTimelineTarget = "changes" | "checks" | "governance";

export interface WorkbenchTimelineItem {
  action?: {
    label: string;
    target: WorkbenchTimelineTarget;
  };
  body: string;
  createdAt: string;
  id: string;
  status: "SUCCESS" | "RUNNING" | "WAITING" | "FAILED";
  taskId: string;
  title: string;
}

export interface ProposalFixture {
  acceptanceCriteria?: string[];
  changes?: ProposalChange[];
  completeness?: ProposalCompletenessInfo;
  display?: ProposalDisplay;
  executionBoundary?: string[];
  expectedBehavior?: string;
  id?: string;
  goal: string;
  items: string[];
  files: string;
  nonGoals?: string[];
  risk: string;
  status?: ProposalStatus;
  steps?: string[];
  superseded?: boolean;
  understanding?: string;
  validation?: string[];
  version?: number;
}

export interface TaskFixture {
  title: string;
  status: string;
  messages: WorkbenchMessage[];
  timeline?: WorkbenchTimelineItem[];
  changes: Array<{
    file: string;
    state: string;
    added: number;
    removed: number;
  }>;
  checks: Array<{
    label: string;
    state: string;
    tone: BadgeTone;
  }>;
}

export const navItems: Array<{
  key: NavKey;
  label: string;
  marker: string;
}> = [
  { key: "workbench", label: "\u5de5\u4f5c\u53f0", marker: "W" },
  { key: "tasks", label: "\u4efb\u52a1", marker: "T" },
  { key: "memory", label: "\u8bb0\u5fc6", marker: "M" },
  { key: "governance", label: "\u6cbb\u7406", marker: "G" },
  { key: "evaluation", label: "\u8bc4\u4f30", marker: "E" },
  { key: "settings", label: "\u8bbe\u7f6e", marker: "S" },
];
