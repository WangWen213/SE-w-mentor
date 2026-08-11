import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const repo = resolve(root, "..");

function assert(condition, message) {
  if (!condition) {
    throw new Error(`test_T094_incomplete_proposal_shows_missing_information_and_no_execute: ${message}`);
  }
}

function read(path) {
  return readFileSync(resolve(repo, path), "utf-8");
}

assert(existsSync(resolve(root, "src", "api", "mentorApi.ts")), "T094 typed API client missing");
assert(existsSync(resolve(root, "src", "pages", "ProjectsPage.tsx")), "ProjectsPage missing");
assert(existsSync(resolve(root, "src", "pages", "NewTaskPage.tsx")), "NewTaskPage missing");
assert(existsSync(resolve(root, "src", "pages", "ProposalReviewPage.tsx")), "ProposalReviewPage missing");
assert(existsSync(resolve(root, "src", "tests", "proposal_flow.test.tsx")), "T094 frontend contract test missing");

const api = read("frontend/src/api/mentorApi.ts");
const app = read("frontend/src/app/App.tsx");
const proposal = read("frontend/src/pages/ProposalReviewPage.tsx");
const tasksPage = read("frontend/src/pages/ProjectsPage.tsx");
const backendProjects = read("backend/src/se_mentor/api/projects.py");
const backendProposals = read("backend/src/se_mentor/api/proposals.py");

for (const endpoint of [
  '"/api/projects"',
  '`/api/projects/${projectId}/tasks`',
  '"/api/tasks"',
  '`/api/tasks/${taskId}`',
  '`/api/tasks/${taskId}/proposals`',
  '`/api/tasks/${taskId}/proposals/${proposalId}/confirm`',
  '`/api/tasks/${taskId}/proposals/${proposalId}/reject`',
  '`/api/tasks/${taskId}/proposals/${proposalId}/adjust`',
]) {
  assert(api.includes(endpoint), `API client missing endpoint ${endpoint}`);
}

assert(backendProjects.includes('@router.get("/{project_id}/tasks")'), "backend task list endpoint missing");
assert(backendProposals.includes('@router.get("")'), "backend proposal read endpoint missing");
assert(backendProposals.includes('@router.post("/{proposal_id}/adjust")'), "backend proposal adjust endpoint missing");
assert(app.includes("loadTaskList"), "task list should refresh from API");
assert(app.includes("createTask"), "create task should call API");
assert(app.includes("cancelProposal"), "stop proposal should call reject/cancel API");
assert(!app.includes("void openProject();"), "fresh page load must not register a project");
assert(!app.includes("C:/Users/ww/Desktop/SE-w-mentor"), "frontend must not register a hardcoded demo project");
assert(!app.includes("C:\\Users\\ww\\Desktop\\SE-w-mentor"), "frontend must not render a hardcoded local project path");
assert(app.includes("openProject = useCallback(async (rootPath: string)"), "project registration must use user-provided rootPath");
assert(proposal.includes("需要你补充"), "incomplete proposal state should be visible");
assert(proposal.includes("确认后 Mentor 才会开始修改"), "frozen proposal hint missing");
assert(proposal.includes("pendingAction !== null"), "proposal actions must avoid duplicate submit");
assert(tasksPage.includes("无法加载任务"), "task list API error should be actionable");
assert(!app.includes("setTimeout("), "frontend must not copy prototype async task state machine");
assert(!app.includes("executionToken"), "frontend must not copy prototype execution token state");
assert(!app.includes("writerOwned"), "frontend must not copy prototype write ownership state");

console.log("test_T094_incomplete_proposal_shows_missing_information_and_no_execute PASS");
