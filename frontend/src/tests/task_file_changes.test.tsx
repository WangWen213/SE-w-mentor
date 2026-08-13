import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { createMentorApi } from "../api/mentorApi";
import { ChangesPanel } from "../components/workbench/ChangesPanel";

describe("task file changes read model", () => {
  it("loads task-scoped FileChange records from the authoritative API", async () => {
    const calls: string[] = [];
    const api = createMentorApi(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${input}`);
      if (input === "/api/diffs/tasks/task-1/changes") {
        return jsonResponse({
          count: 1,
          items: [
            {
              backedUp: true,
              changeId: "change-1",
              diff: "--- a/app.py\n+++ b/app.py\n-value = 1\n+value = 2\n",
              filePath: "app.py",
              lines: [],
              modified: true,
              operation: "MODIFY",
              rolledBack: false,
            },
          ],
          taskId: "task-1",
        });
      }
      throw new Error(`unexpected request ${input}`);
    });

    const result = await api.getTaskFileChanges("task-1");

    expect(result.count).toBe(1);
    expect(result.items[0].changeId).toBe("change-1");
    expect(result.items[0].filePath).toBe("app.py");
    expect(calls).toEqual(["GET /api/diffs/tasks/task-1/changes"]);
  });

  it("renders real FileChange rows instead of proposal-stage empty state", () => {
    const html = renderToStaticMarkup(
      <ChangesPanel
        active
        changes={[
          {
            backedUp: true,
            changeId: "change-1",
            diff: "--- a/app.py\n+++ b/app.py\n-old\n+new\n",
            filePath: "app.py",
            lines: [],
            modified: true,
            operation: "MODIFY",
            rolledBack: false,
          },
        ]}
        taskStatus="EXECUTING"
      />,
    );

    expect(html).toContain("app.py");
    expect(html).toContain("change-1");
    expect(html).toContain("+new");
    expect(html).not.toContain("灏氭湭浜х敓鐪熷疄鏀瑰姩");
  });

  it("keeps diff rows stable during refresh without rendering refresh text as content", () => {
    const html = renderToStaticMarkup(
      <ChangesPanel
        active
        hasLoaded
        loading
        changes={[
          {
            backedUp: true,
            changeId: "change-1",
            diff: "--- a/app.py\n+++ b/app.py\n-old\n+new\n",
            filePath: "app.py",
            lines: [],
            modified: true,
            operation: "MODIFY",
            rolledBack: false,
          },
        ]}
        taskStatus="EXECUTING"
      />,
    );

    expect(html).toContain("app.py");
    expect(html).toContain("+new");
    expect(html).not.toContain("正在更新改动");
    expect(html).not.toContain("\\u6b63\\u5728\\u66f4\\u65b0\\u6539\\u52a8");
  });
});

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify({ data, error: null, meta: {} }), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
