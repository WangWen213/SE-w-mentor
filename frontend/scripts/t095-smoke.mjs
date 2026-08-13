import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const repo = resolve(root, "..");

function assert(condition, message) {
  if (!condition) {
    throw new Error(`test_T095_block_has_no_execute_button_and_unknowns_are_explicit: ${message}`);
  }
}

function read(path) {
  return readFileSync(resolve(repo, path), "utf-8");
}

assert(existsSync(resolve(root, "src", "pages", "AnalysisPage.tsx")), "AnalysisPage missing");
assert(existsSync(resolve(root, "src", "components", "ImpactReport.tsx")), "ImpactReport missing");
assert(existsSync(resolve(root, "src", "components", "GovernanceDecision.tsx")), "GovernanceDecision missing");
assert(existsSync(resolve(root, "src", "tests", "analysis_page.test.tsx")), "T095 frontend contract test missing");

const api = read("frontend/src/api/mentorApi.ts");
const app = read("frontend/src/app/App.tsx");
const analysisPage = read("frontend/src/pages/AnalysisPage.tsx");
const impact = read("frontend/src/components/ImpactReport.tsx");
const decision = read("frontend/src/components/GovernanceDecision.tsx");
const backendGovernance = read("backend/src/se_mentor/api/governance.py");

for (const endpoint of [
  '"/api/analysis/index"',
  '`/api/proposals/${proposalId}/governance`',
]) {
  assert(api.includes(endpoint), `API client missing ${endpoint}`);
}

for (const field of [
  "facts",
  "inferences",
  "unknowns",
  "evidence",
  "impactScope",
  "ruleHits",
]) {
  assert(api.includes(field), `typed governance field missing ${field}`);
  assert(backendGovernance.includes(`"${field}"`), `backend governance field missing ${field}`);
}

assert(app.includes("loadGovernance"), "Governance page should load from API");
assert(app.includes("governanceRequestRef"), "stale governance responses should be guarded");
assert(analysisPage.includes("无法加载治理结果"), "actionable governance error missing");
assert(impact.includes("主要依据"), "facts section missing");
assert(impact.includes("推断"), "inference section missing");
assert(impact.includes("还不能确认"), "unknowns section missing");
assert(impact.includes("查看依据"), "evidence toggle missing");
assert(decision.includes("自动允许"), "ALLOW mapping missing");
assert(decision.includes("需要你的确认"), "WARN mapping missing");
assert(decision.includes("始终阻止"), "BLOCK mapping missing");
assert(decision.includes("执行授权将在下一阶段接入"), "T096 boundary copy missing");
assert(!decision.includes("开始执行"), "BLOCK/governance UI must not expose execution entry");
assert(!api.includes("/execute"), "T095 must not add execution API");
assert(!api.includes("/events"), "T095 must not add SSE API");
assert(!api.includes("/approvals"), "T095 must not add approval API");

console.log("test_T095_block_has_no_execute_button_and_unknowns_are_explicit PASS");
