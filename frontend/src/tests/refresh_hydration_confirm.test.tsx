import { describe, expect, it } from "vitest";

import {
  canConfirmHydratedProposal,
  dedupeTimelineItems,
  dedupeWorkbenchMessages,
  readLastActiveView,
  replaceTasksForProject,
  rememberLastActiveView,
  shouldRenderChangesEmpty,
  shouldRenderChangesInitialLoading,
  shouldRenderGovernanceInitialLoading,
  shouldRenderProjectEmpty,
  upsertTasks,
} from "../app/App";
import { deriveProposalDisplayState } from "../pages/ProposalReviewPage";

describe("refresh hydration and confirm recovery", () => {
  it("keeps proposal loading distinct from proposal analysis", () => {
    expect(
      deriveProposalDisplayState({
        hasProposal: false,
        proposalConfirmed: false,
        proposalFailed: false,
        proposalState: "LOADING",
      }),
    ).toBe("LOADING");

    expect(
      deriveProposalDisplayState({
        hasProposal: false,
        proposalConfirmed: false,
        proposalFailed: false,
        proposalState: "NOT_CREATED",
      }),
    ).toBe("ANALYZING");
  });

  it("restores the active route from persisted app hydration state", () => {
    const store = new Map<string, string>();
    const storage = {
      clear: () => store.clear(),
      getItem: (key: string) => store.get(key) ?? null,
      removeItem: (key: string) => store.delete(key),
      setItem: (key: string, value: string) => store.set(key, value),
    };
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: storage,
    });
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { localStorage: storage },
    });
    globalThis.localStorage.clear();
    rememberLastActiveView("evaluation");

    expect(readLastActiveView()).toBe("evaluation");
  });

  it("requires restored task and proposal identities before confirm", () => {
    expect(canConfirmHydratedProposal({ pendingAction: null, proposalId: "proposal-1", taskId: "task-1" })).toBe(true);
    expect(canConfirmHydratedProposal({ pendingAction: null, proposalId: null, taskId: "task-1" })).toBe(false);
    expect(canConfirmHydratedProposal({ pendingAction: null, proposalId: "proposal-1", taskId: null })).toBe(false);
    expect(canConfirmHydratedProposal({ pendingAction: "confirm", proposalId: "proposal-1", taskId: "task-1" })).toBe(false);
  });

  it("does not expose project hydration as a recovery conversation state", () => {
    expect(canConfirmHydratedProposal({ pendingAction: null, proposalId: "proposal-1", taskId: "task-1" })).toBe(true);
  });

  it("does not render empty project state while boot hydration is still running", () => {
    expect(shouldRenderProjectEmpty("BOOTING", false)).toBe(false);
    expect(shouldRenderProjectEmpty("READY", true)).toBe(false);
    expect(shouldRenderProjectEmpty("EMPTY", true)).toBe(true);
  });

  it("upserts task command responses into active task list identity", () => {
    expect(
      upsertTasks(
        [{ id: "task-1", projectId: "project-1", request: "change", status: "ACTION_PENDING" }],
        [{ id: "task-1", projectId: "project-1", request: "change", status: "CANCEL_REQUESTED" }],
      ),
    ).toEqual([{ id: "task-1", projectId: "project-1", request: "change", status: "CANCEL_REQUESTED" }]);
  });

  it("replaces only the requested project's task list to block stale cross-project writes", () => {
    expect(
      replaceTasksForProject(
        [
          { id: "task-a", projectId: "project-a", request: "a", status: "CREATED" },
          { id: "task-b", projectId: "project-b", request: "b", status: "CREATED" },
        ],
        "project-a",
        [{ id: "task-a2", projectId: "project-a", request: "a2", status: "CREATED" }],
      ).map((task) => task.id),
    ).toEqual(["task-b", "task-a2"]);
  });

  it("dedupes the same proposal entity but preserves legitimate proposal versions", () => {
    const base = {
      createdAt: "2026-08-13T00:00:00Z",
      kind: "PROPOSAL" as const,
      role: "MENTOR" as const,
      status: "DONE" as const,
      taskId: "task-1",
      text: "proposal",
    };
    const deduped = dedupeWorkbenchMessages([
      { ...base, id: "local-v1", proposal: proposalFixture(1) },
      { ...base, id: "rest-v1", proposal: proposalFixture(1) },
      { ...base, id: "rest-v2", proposal: proposalFixture(2) },
    ]);

    expect(deduped.map((message) => message.id)).toEqual(["local-v1", "rest-v2"]);
  });

  it("dedupes timeline by stable source identity without dropping distinct file changes", () => {
    const items = [
      timelineItem("FileChange:change-1:FILE_CHANGED"),
      timelineItem("FileChange:change-1:FILE_CHANGED"),
      timelineItem("FileChange:change-2:FILE_CHANGED"),
    ];

    expect(dedupeTimelineItems(items).map((item) => item.id)).toEqual([
      "FileChange:change-1:FILE_CHANGED",
      "FileChange:change-2:FILE_CHANGED",
    ]);
  });

  it("keeps governance detail visible during background refresh", () => {
    expect(
      shouldRenderGovernanceInitialLoading({
        initialStatus: "LOADING",
        refreshing: false,
        report: null,
      }),
    ).toBe(true);
    expect(
      shouldRenderGovernanceInitialLoading({
        initialStatus: "READY",
        refreshing: true,
        report: governanceReport(),
      }),
    ).toBe(false);
  });

  it("keeps real file changes visible during background refresh", () => {
    expect(shouldRenderChangesInitialLoading({ hasLoaded: false, itemCount: 0, loading: true })).toBe(true);
    expect(shouldRenderChangesInitialLoading({ hasLoaded: true, itemCount: 1, loading: true })).toBe(false);
    expect(shouldRenderChangesEmpty({ hasLoaded: false, itemCount: 0, loading: false })).toBe(false);
    expect(shouldRenderChangesEmpty({ hasLoaded: true, itemCount: 0, loading: false })).toBe(true);
  });
});

function proposalFixture(version: number) {
  return {
    files: "frontend/src/app/App.tsx",
    goal: "change",
    id: `proposal-${version}`,
    impact: "frontend",
    items: ["frontend/src/app/App.tsx"],
    risk: "low",
    status: "DRAFT" as const,
    version,
  };
}

function timelineItem(id: string) {
  return {
    body: "frontend/src/app/fixtures.ts",
    createdAt: "2026-08-13T00:00:00Z",
    id,
    status: "SUCCESS" as const,
    taskId: "task-1",
    title: "文件修改成功",
  };
}

function governanceReport() {
  return {
    changedPaths: ["frontend/src/app/App.tsx"],
    decision: "ALLOW" as const,
    evidence: [],
    evidenceRef: "evidence-1",
    facts: [],
    impactScope: { files: ["frontend/src/app/App.tsx"], summary: "frontend-only" },
    inferences: [],
    nonApprovable: false,
    proposalId: "proposal-1",
    ruleHits: [],
    unknowns: [],
  };
}
