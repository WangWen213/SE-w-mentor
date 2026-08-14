import type { Task, TaskStatus } from "../api/mentorApi";

const terminalStatuses = new Set<TaskStatus>([
  "BLOCKED",
  "CANCELLED",
  "COMPLETED",
  "FAILED",
  "PAUSED",
  "ROLLED_BACK",
]);

export function isTerminalTaskStatus(status: TaskStatus): boolean {
  return terminalStatuses.has(status);
}

export function shouldReconcileAfterReconnect(
  status: TaskStatus,
  reconnectCount: number,
): boolean {
  return reconnectCount > 0 && !isTerminalTaskStatus(status);
}

export function preserveTerminalTaskSnapshot(current: Task, incoming: Task): Task {
  if (
    current.id === incoming.id &&
    isTerminalTaskStatus(current.status) &&
    !isTerminalTaskStatus(incoming.status)
  ) {
    return current;
  }
  return incoming;
}
