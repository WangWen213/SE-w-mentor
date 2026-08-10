import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const repo = resolve(root, "..");

function assert(condition, message) {
  if (!condition) {
    throw new Error(`test_T096_warn_cannot_start_before_explicit_approval: ${message}`);
  }
}

function read(path) {
  return readFileSync(resolve(repo, path), "utf-8");
}

assert(existsSync(resolve(root, "src", "pages", "ExecutionPage.tsx")), "ExecutionPage missing");
assert(existsSync(resolve(root, "src", "hooks", "useTaskEvents.ts")), "useTaskEvents hook missing");
assert(existsSync(resolve(root, "src", "components", "ExecutionTimeline.tsx")), "ExecutionTimeline missing");
assert(existsSync(resolve(root, "src", "tests", "execution_page.test.tsx")), "T096 frontend contract test missing");

const api = read("frontend/src/api/mentorApi.ts");
const app = read("frontend/src/app/App.tsx");
const decision = read("frontend/src/components/GovernanceDecision.tsx");
const execution = read("frontend/src/pages/ExecutionPage.tsx");
const timeline = read("frontend/src/components/ExecutionTimeline.tsx");
const eventsHook = read("frontend/src/hooks/useTaskEvents.ts");
const backendApprovals = read("backend/src/se_mentor/api/approvals.py");
const backendExecution = read("backend/src/se_mentor/api/execution.py");
const backendEvents = read("backend/src/se_mentor/api/events.py");

for (const endpoint of [
  "`/api/approvals/${approvalId}/approve`",
  "`/api/approvals/${approvalId}/reject`",
  "`/api/tasks/${taskId}/execute`",
  "`/api/tasks/${taskId}/cancel`",
  "`/api/tasks/${taskId}/events`",
]) {
  assert(api.includes(endpoint), `API client missing ${endpoint}`);
}

assert(api.includes("TemporaryGrant"), "TemporaryGrant type missing");
assert(api.includes("ExecutionPolicy"), "ExecutionPolicy type missing");
assert(api.includes("TaskEvent"), "TaskEvent type missing");
assert(decision.includes("onAllowOnce"), "WARN allow button should call real approval flow");
assert(decision.includes("onDeny"), "WARN deny button should call real approval flow");
assert(decision.includes("disabled={pendingAction !== null}"), "WARN mutations need pending protection");
assert(app.includes("approveGovernance"), "App should coordinate Approval API");
assert(app.includes("executeTask"), "App should coordinate Execution API");
assert(app.includes("cancelExecution"), "App should coordinate Cancel API");
assert(app.includes("activeExecutions"), "background task state should be keyed, not only current view");
assert(timeline.includes("正在重新连接任务进度"), "SSE reconnecting UI missing");
assert(execution.includes("正在停止"), "cancel pending UI missing");
assert(eventsHook.includes("Last-Event-ID"), "SSE reconnect should use Last-Event-ID");
assert(eventsHook.includes("lastEventId"), "event id tracking missing");
assert(eventsHook.includes("seenEventIds"), "duplicate event avoidance missing");
assert(eventsHook.includes("taskId"), "per-task event isolation missing");
assert(backendApprovals.includes("temporaryGrant"), "Approval response should expose TemporaryGrant");
assert(backendExecution.includes('@router.post("/{task_id}/cancel")'), "Cancel endpoint missing");
assert(backendExecution.includes("BUS.publish"), "Execution/cancel should publish task events");
assert(backendEvents.includes("json.dumps"), "SSE event data should be typed JSON");
assert(!api.includes("/diffs"), "T096 must not add diff API");
assert(!api.includes("/validation"), "T096 must not add validation API");
assert(!api.includes("/rollback"), "T096 must not add rollback API");
assert(!api.includes("/recovery"), "T096 must not add recovery API");

console.log("test_T096_warn_cannot_start_before_explicit_approval PASS");
