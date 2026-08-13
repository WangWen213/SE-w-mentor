import { describe, expect, it } from "vitest";

import { taskEventLabel } from "../api/mentorApi";

describe("T096 execution presentation contract", () => {
  it("test_T096_warn_cannot_start_before_explicit_approval", () => {
    expect(taskEventLabel("EXECUTION_STARTED")).toBe("正在修改");
    expect(taskEventLabel("CANCEL_REQUESTED")).toBe("正在停止");
  });
});
