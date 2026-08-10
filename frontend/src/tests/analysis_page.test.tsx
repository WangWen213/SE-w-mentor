import { describe, expect, it } from "vitest";

import { governanceDecisionLabel } from "../api/mentorApi";

describe("T095 analysis page presentation contract", () => {
  it("test_T095_block_has_no_execute_button_and_unknowns_are_explicit", () => {
    expect(governanceDecisionLabel("ALLOW")).toBe("自动允许");
    expect(governanceDecisionLabel("WARN")).toBe("需要你的确认");
    expect(governanceDecisionLabel("BLOCK")).toBe("始终阻止");
  });
});
