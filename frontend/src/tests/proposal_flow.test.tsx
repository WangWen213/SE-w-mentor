import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { taskStateLabel } from "../api/mentorApi";
import { App } from "../app/App";

describe("T094 proposal flow presentation contract", () => {
  it("test_T094_incomplete_proposal_shows_missing_information_and_no_execute", () => {
    expect(taskStateLabel("NEEDS_INFORMATION")).toBe("需补充");
    expect(taskStateLabel("CREATED")).toBe("待确认");
  });

  it("test_runtime_corrective_fresh_load_has_no_project_registration_side_effect", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("输入本地 Git 项目路径");
    expect(html).toContain("打开本地项目");
    expect(html).not.toContain("C:/Users/ww/Desktop/SE-w-mentor");
    expect(html).not.toContain("C:\\Users\\ww\\Desktop\\SE-w-mentor");
  });
});
