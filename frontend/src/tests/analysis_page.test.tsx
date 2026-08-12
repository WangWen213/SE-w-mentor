import { describe, expect, it } from "vitest";

import { governanceDecisionLabel } from "../api/mentorApi";

describe("T095 analysis page presentation contract", () => {
  it("test_T095_block_has_no_execute_button_and_unknowns_are_explicit", () => {
    expect(governanceDecisionLabel("ALLOW")).toBe("\u81ea\u52a8\u5141\u8bb8");
    expect(governanceDecisionLabel("WARN")).toBe("\u9700\u8981\u4f60\u7684\u786e\u8ba4");
    expect(governanceDecisionLabel("BLOCK")).toBe("\u59cb\u7ec8\u963b\u6b62");
  });
});
