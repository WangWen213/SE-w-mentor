import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const repo = resolve(root, "..");

function assert(condition, message) {
  if (!condition) {
    throw new Error(`test_T097_error_view_states_modified_backed_up_rolled_back_and_next_action: ${message}`);
  }
}

function read(path) {
  return readFileSync(resolve(repo, path), "utf-8");
}

for (const file of [
  "frontend/src/pages/TaskResultPage.tsx",
  "frontend/src/pages/RecoveryPage.tsx",
  "frontend/src/components/DiffViewer.tsx",
  "frontend/src/components/ValidationReport.tsx",
  "frontend/src/tests/result_recovery.test.tsx",
]) {
  assert(existsSync(resolve(repo, file)), `${file} missing`);
}

const api = read("frontend/src/api/mentorApi.ts");
const app = read("frontend/src/app/App.tsx");
const result = read("frontend/src/pages/TaskResultPage.tsx");
const recovery = read("frontend/src/pages/RecoveryPage.tsx");
const diff = read("frontend/src/components/DiffViewer.tsx");
const validation = read("frontend/src/components/ValidationReport.tsx");

assert(api.includes("getDiffTrace"), "real backend diff API integration missing");
assert(api.includes("`/api/diffs/${changeId}/trace`"), "diff must come from backend trace endpoint");
assert(api.includes("listRecovery"), "backend recovery state integration missing");
assert(api.includes("resolveRecovery"), "keep/rollback must call backend recovery endpoint");
assert(api.includes("ValidationResult"), "backend validation result type missing");
assert(api.includes("CompletionGate"), "backend CompletionGate type missing");
assert(app.includes("TaskResultPage"), "result page not wired into app");
assert(app.includes("RecoveryPage"), "recovery page not wired into app");
assert(result.includes("CompletionGate"), "result page must render backend completion gate");
assert(result.includes("ValidationReport"), "result page must render backend validation result");
assert(result.includes("DiffViewer"), "result page must render backend diff");
assert(diff.includes("outsideScope"), "diff must highlight out-of-scope backend changes");
assert(validation.includes("failureCategory"), "validation must show backend failure category");
assert(recovery.includes("force") === false, "recovery conflict must not offer force overwrite");
assert(recovery.includes("人工处理"), "recovery conflict must route to manual handling");
assert(recovery.includes("onRollback"), "rollback action must be present");
assert(recovery.includes("onKeep"), "keep action must be present");
assert(!api.includes("/knowledge"), "T097 must not add knowledge API");
assert(!api.includes("/credentials"), "T097 must not add credential API");
assert(!api.includes("/audit"), "T097 must not add audit API");

console.log("test_T097_error_view_states_modified_backed_up_rolled_back_and_next_action PASS");
