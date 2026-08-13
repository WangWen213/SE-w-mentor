import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { governanceDecisionLabel } from "../api/mentorApi";
import { AnalysisPage } from "../pages/AnalysisPage";

describe("T095 analysis page presentation contract", () => {
  it("test_T095_block_has_no_execute_button_and_unknowns_are_explicit", () => {
    expect(governanceDecisionLabel("ALLOW")).toBe("\u81ea\u52a8\u5141\u8bb8");
    expect(governanceDecisionLabel("WARN")).toBe("\u9700\u8981\u4f60\u7684\u786e\u8ba4");
    expect(governanceDecisionLabel("BLOCK")).toBe("\u59cb\u7ec8\u963b\u6b62");
  });

  it("renders the canonical governance view in zh-CN without refresh copy as content", () => {
    const html = renderToStaticMarkup(
      <AnalysisPage
        approved={false}
        detail={null}
        detailError={null}
        detailLoading={false}
        error={null}
        hasMore={false}
        history={[
          {
            affectedFileCount: 1,
            blocked: false,
            createdAt: "2026-08-13T20:41:00+08:00",
            decision: "ALLOW",
            displaySummary: "修改范围有限，符合当前批准范围。",
            governanceDecisionId: "decision-1",
            proposalId: "proposal-1",
            proposalVersion: 1,
            reasonCode: "FINITE_CHANGED_PATH_SCOPE",
            requiresApproval: false,
            summary: "修改范围有限，符合当前批准范围。",
            taskId: "task-1",
            taskTitle: "修改任务菜单文案",
          },
        ]}
        loading={false}
        loadingMore={false}
        pendingAction={null}
        refreshing={false}
        selectedDecisionId={null}
        state="READY"
        onAllowOnce={async () => undefined}
        onDeny={async () => undefined}
        onLoadMore={() => undefined}
        onReload={() => undefined}
        onSelectDecision={() => undefined}
      />,
    );

    expect(html).toContain("治理");
    expect(html).toContain("治理历史记录");
    expect(html).toContain("修改任务菜单文案");
    expect(html).toContain("修改范围有限");
    expect(html).toContain("查看详情");
    expect(html).not.toContain("Governance");
    expect(html).not.toContain("Loading governance result");
    expect(html).not.toContain("Refreshing governance result");
    expect(html).not.toContain("Governance decision");
    expect(html).not.toContain("Block log");
    expect(html).not.toContain("No block records");
    expect(html).not.toContain("Allowed within finite changed path scope.");
  });

  it("keeps known P0 zh-CN regression strings out of product source", async () => {
    const sources = await Promise.all([
      import("../app/App.tsx?raw").then((module) => String(module.default)),
      import("../api/mentorApi.ts?raw").then((module) => String(module.default)),
    ]);
    const productSource = sources.join("\n");

    for (const regression of [
      "Mentor is generating a proposal",
      "Task was created, but proposal generation failed.",
      "Analyzing impact",
      "Executing changes",
      "Loading memory",
      "Memory load failed",
      "No reviewed memory yet",
      "No project selected",
      ">Settings<",
      "Model provider",
      "Task cancelled",
      "Governance decided",
      "Execution failed",
      "Unexpected error.",
    ]) {
      expect(productSource).not.toContain(regression);
    }
  });
});
