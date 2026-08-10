import { describe, expect, it } from "vitest";

import { taskStateLabel } from "../api/mentorApi";

describe("T094 proposal flow presentation contract", () => {
  it("test_T094_incomplete_proposal_shows_missing_information_and_no_execute", () => {
    expect(taskStateLabel("NEEDS_INFORMATION")).toBe("需补充");
    expect(taskStateLabel("CREATED")).toBe("待确认");
  });
});
