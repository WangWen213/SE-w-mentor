import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { isOnlineSafeCredentialStatus } from "../app/App";
import { AppShell } from "../app/AppShell";
import { ProjectsPage } from "../pages/ProjectsPage";

describe("ONLINE_SAFE project ZIP import presentation", () => {
  it("uses upload project as the primary project action in ONLINE_SAFE", () => {
    const html = renderToStaticMarkup(
      <AppShell
        activeView="tasks"
        project={null}
        projectBootstrap={null}
        projectError={null}
        projectHydrationState="EMPTY"
        projectOpening={false}
        taskCount={0}
        onlineSafe
        onNewTask={() => undefined}
        onOpenProject={() => undefined}
        onViewChange={() => undefined}
      >
        <div />
      </AppShell>,
    );

    expect(html).toContain("上传项目");
    expect(html).toContain("上传 ZIP 项目");
    expect(html).not.toContain("打开本地仓库");
  });

  it("keeps local repository wording outside ONLINE_SAFE", () => {
    const html = renderToStaticMarkup(
      <AppShell
        activeView="tasks"
        project={null}
        projectBootstrap={null}
        projectError={null}
        projectHydrationState="EMPTY"
        projectOpening={false}
        taskCount={0}
        onNewTask={() => undefined}
        onOpenProject={() => undefined}
        onViewChange={() => undefined}
      >
        <div />
      </AppShell>,
    );

    expect(html).toContain("打开本地仓库");
  });

  it("shows ZIP import and export controls for online projects", () => {
    const emptyHtml = renderToStaticMarkup(
      <ProjectsPage
        error={null}
        loading={false}
        lockStatus={null}
        project={null}
        tasks={[]}
        onlineSafe
        onDownloadPatch={() => undefined}
        onDownloadZip={() => undefined}
        onOpenTask={() => undefined}
        onStartNewTask={() => undefined}
      />,
    );
    const projectHtml = renderToStaticMarkup(
      <ProjectsPage
        error={null}
        loading={false}
        lockStatus={{ projectId: "p1", status: "UNLOCKED" }}
        project={{ authorized: true, id: "p1", rootPath: "Uploaded Project" }}
        tasks={[]}
        onlineSafe
        onDownloadPatch={() => undefined}
        onDownloadZip={() => undefined}
        onOpenTask={() => undefined}
        onStartNewTask={() => undefined}
      />,
    );

    expect(emptyHtml).toContain("先上传项目 ZIP");
    expect(projectHtml).toContain("下载项目 ZIP");
    expect(projectHtml).toContain("下载变更 Patch");
  });

  it("detects ONLINE_SAFE credential status", () => {
    expect(
      isOnlineSafeCredentialStatus({
        configured: false,
        provider: "OpenAI",
        source: "ONLINE_SAFE",
      }),
    ).toBe(true);
    expect(
      isOnlineSafeCredentialStatus({
        configured: true,
        provider: "Mock",
        source: "CLOUD_DEMO",
      }),
    ).toBe(false);
  });
});
