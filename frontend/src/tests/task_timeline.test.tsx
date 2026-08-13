import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { createMentorApi } from "../api/mentorApi";
import { Conversation, conversationEntries } from "../components/workbench/Conversation";

describe("workbench execution timeline", () => {
  it("loads task-scoped timeline from the authoritative API", async () => {
    const calls: string[] = [];
    const api = createMentorApi(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${input}`);
      if (input === "/api/tasks/task-1/timeline") {
        return jsonResponse({
          count: 1,
          items: [
            {
              body: "frontend/src/app/fixtures.ts\n任务7 -> 任务8",
              createdAt: "2026-08-13T07:42:22Z",
              id: "FileChange:change-1:FILE_CHANGED",
              kind: "FILE_CHANGED",
              sequence: 1,
              source: { id: "change-1", type: "FileChange" },
              status: "SUCCESS",
              title: "文件修改成功",
              action: { label: "查看改动", target: "changes" },
            },
          ],
          taskId: "task-1",
        });
      }
      throw new Error(`unexpected request ${input}`);
    });

    const result = await api.getTaskTimeline("task-1");

    expect(result.items[0].kind).toBe("FILE_CHANGED");
    expect(result.items[0].source.type).toBe("FileChange");
    expect(calls).toEqual(["GET /api/tasks/task-1/timeline"]);
  });

  it("merges natural messages and process nodes by timestamp", () => {
    const entries = conversationEntries(
      [
        {
          createdAt: "2026-08-13T07:39:10Z",
          id: "message-1",
          kind: "TEXT",
          role: "USER",
          status: "DONE",
          taskId: "task-1",
          text: "把任务7改成任务8",
        },
      ],
      [
        {
          body: "frontend/src/app/fixtures.ts\n任务7 -> 任务8",
          createdAt: "2026-08-13T07:42:22Z",
          id: "FileChange:change-1:FILE_CHANGED",
          status: "SUCCESS",
          taskId: "task-1",
          title: "文件修改成功",
          action: { label: "查看改动", target: "changes" },
        },
      ],
    );

    expect(entries.map((entry) => entry.type)).toEqual(["message", "timeline"]);
  });

  it("renders compact process nodes with action links", () => {
    const html = renderToStaticMarkup(
      <Conversation
        task={{
          changes: [],
          checks: [],
          messages: [],
          status: "范围已确认",
          title: "改导航文案",
          timeline: [
            {
              body: "frontend/src/app/fixtures.ts\n任务7 -> 任务8",
              createdAt: "2026-08-13T07:42:22Z",
              id: "FileChange:change-1:FILE_CHANGED",
              status: "SUCCESS",
              taskId: "task-1",
              title: "文件修改成功",
              action: { label: "查看改动", target: "changes" },
            },
          ],
        }}
      />,
    );

    expect(html).toContain("文件修改成功");
    expect(html).toContain("frontend/src/app/fixtures.ts");
    expect(html).toContain("查看改动");
  });
});

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify({ data, error: null, meta: {} }), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
