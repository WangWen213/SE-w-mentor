import { describe, expect, it } from "vitest";

import { createMentorApi, parseTaskEvents } from "../api/mentorApi";

describe("T097 result and recovery integration contract", () => {
  it("test_T097_error_view_states_modified_backed_up_rolled_back_and_next_action", async () => {
    const calls: string[] = [];
    const api = createMentorApi(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${input}`);
      if (input === "/api/diffs/change-1/trace") {
        return jsonResponse({
          backedUp: true,
          changeId: "change-1",
          filePath: "auth/middleware.py",
          lines: [{ content: "+ guard()", lineNumber: 12, outsideScope: true, type: "added" }],
          modified: true,
          rolledBack: false,
        });
      }
      if (input === "/api/recovery") {
        return jsonResponse({
          items: [{ conflict: true, sideEffects: "modified backed_up", status: "RECOVERY_REQUIRED", taskId: "task-1" }],
        });
      }
      if (input === "/api/recovery/task-1/resolve") {
        return jsonResponse({ action: "rollback", status: "RESOLVED", taskId: "task-1" });
      }
      throw new Error(`unexpected request ${input}`);
    });

    const events = parseTaskEvents(
      "task-1",
      [
        'id: 1\nevent: status\ndata: {"changeId":"change-1","validation":[{"name":"pytest","status":"FAIL","message":"failed","failureCategory":"TEST"}],"completionGate":[{"label":"tests","status":"FAIL"}]}',
        "",
      ].join("\n"),
    );
    const diff = await api.getDiffTrace(events[0].payload.changeId ?? "");
    const recovery = await api.listRecovery();
    const resolved = await api.resolveRecovery("task-1", "rollback");

    expect(diff.modified).toBe(true);
    expect(diff.backedUp).toBe(true);
    expect(diff.rolledBack).toBe(false);
    expect(diff.lines[0].outsideScope).toBe(true);
    expect(events[0].payload.validation?.[0].failureCategory).toBe("TEST");
    expect(events[0].payload.completionGate?.[0].status).toBe("FAIL");
    expect(recovery.items[0].conflict).toBe(true);
    expect(resolved.action).toBe("rollback");
    expect(calls).toEqual([
      "GET /api/diffs/change-1/trace",
      "GET /api/recovery",
      "POST /api/recovery/task-1/resolve",
    ]);
  });
});

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify({ data, error: null, meta: {} }), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
