import { describe, expect, it } from "vitest";

import type { Task, TaskStatus } from "../api/mentorApi";
import {
  preserveTerminalTaskSnapshot,
  shouldReconcileAfterReconnect,
} from "../app/taskRefreshPolicy";

function task(status: TaskStatus): Task {
  return {
    id: "task-1",
    projectId: "project-1",
    request: "change one file",
    status,
  } as Task;
}

describe("task refresh policy", () => {
  it.each(["FAILED", "PAUSED", "BLOCKED", "COMPLETED"] as const)(
    "stops automatic reconnect recovery after %s",
    (status) => {
      expect(shouldReconcileAfterReconnect(status, 1)).toBe(false);
    },
  );

  it("allows one reconnect reconciliation while execution is active", () => {
    expect(shouldReconcileAfterReconnect("EXECUTING", 1)).toBe(true);
    expect(shouldReconcileAfterReconnect("EXECUTING", 0)).toBe(false);
  });

  it.each(["FAILED", "PAUSED", "BLOCKED"] as const)(
    "does not let a stale EXECUTING response replace %s",
    (status) => {
      const terminal = task(status);
      expect(preserveTerminalTaskSnapshot(terminal, task("EXECUTING"))).toBe(terminal);
    },
  );

  it("accepts a newer terminal snapshot", () => {
    const failed = task("FAILED");
    expect(preserveTerminalTaskSnapshot(task("EXECUTING"), failed)).toBe(failed);
  });
});
