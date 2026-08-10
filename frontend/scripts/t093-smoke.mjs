import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const appPath = resolve(root, "src", "app", "App.tsx");
const tokensPath = resolve(root, "src", "styles", "tokens.css");

function assert(condition, message) {
  if (!condition) {
    throw new Error(`test_T093_app_shell_and_accessible_status_badge_exist: ${message}`);
  }
}

assert(existsSync(appPath), "App Shell source should exist");
assert(existsSync(tokensPath), "Design token stylesheet should exist");

function readSources(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .map((entry) => {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory()) {
        return readSources(path);
      }
      if (entry.name.endsWith(".tsx") || entry.name.endsWith(".ts")) {
        return readFileSync(path, "utf-8");
      }
      return "";
    })
    .join("\n");
}

const app = [
  readSources(resolve(root, "src", "app")),
  readSources(resolve(root, "src", "components")),
].join("\n");
const tokens = readFileSync(tokensPath, "utf-8");

for (const token of [
  "--bg",
  "--sidebar",
  "--surface",
  "--card",
  "--soft",
  "--ink",
  "--text",
  "--muted",
  "--line",
  "--line2",
  "--blue",
  "--blueSoft",
  "--green",
  "--greenSoft",
  "--amber",
  "--amberSoft",
  "--red",
  "--redSoft",
  "--radius",
  "--shadow",
]) {
  assert(tokens.includes(token), `missing token ${token}`);
}

for (const text of [
  "工作台",
  "任务",
  "记忆",
  "治理",
  "评估",
  "设置",
  "对话",
  "改动",
  "检查",
  "ProposalCard",
  "Composer",
  "StatusBadge",
]) {
  assert(app.includes(text), `missing UI invariant ${text}`);
}

for (const semantic of [
  "aria-label=\"SE-Mentor 主导航\"",
  "role=\"tablist\"",
  "role=\"tab\"",
  "aria-selected",
  "role=\"tabpanel\"",
  "role=\"status\"",
]) {
  assert(app.includes(semantic), `missing semantic invariant ${semantic}`);
}

console.log("test_T093_app_shell_and_accessible_status_badge_exist PASS");
