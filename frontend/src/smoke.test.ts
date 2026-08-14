import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./app/App";

describe("frontend scaffold", () => {
  it("has a working test runner", () => {
    expect("SE-Mentor").toBe("SE-Mentor");
  });

  it("test_T093_app_shell_and_accessible_status_badge_exist", () => {
    const html = renderToStaticMarkup(React.createElement(App));

    for (const label of [
      "工作台",
      "任务",
      "记忆",
      "治理",
      "评估",
      "设置",
    ]) {
      expect(html).toContain(label);
    }

    expect(html).toContain('aria-label="SE-Mentor 主导航"');
    expect(html).toContain('data-testid="mentor-sidebar"');
    expect(html).toContain('data-testid="mentor-topbar"');
    expect(html).toContain('role="tablist"');
    expect(html).toContain('role="tab"');
    expect(html).toContain('aria-selected="true"');
    expect(html).toContain('role="tabpanel"');
    expect(html).toContain("正在恢复工作台");
    expect(html).toContain("新任务需求");
    expect(html).toContain("确认方案后才会进入治理和执行流程");
  });
});
