import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SettingsViewV2, isOnlineSafeCredentialStatus } from "../app/App";
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

  it("shows replace wording without exposing server paths for an existing online project", () => {
    const html = renderToStaticMarkup(
      <AppShell
        activeView="tasks"
        project={{
          authorized: true,
          id: "p1",
          rootPath: "/var/lib/se-mentor/sessions/session-a/workspace",
        }}
        projectBootstrap={null}
        projectError={null}
        projectHydrationState="READY"
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

    expect(html).toContain("在线项目");
    expect(html).toContain("更换项目");
    expect(html).not.toContain("/var/lib/se-mentor");
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
    expect(projectHtml).toContain("下载修改后的项目");
    expect(projectHtml).toContain("下载变更 Patch");
  });

  it("makes CLOUD_DEMO and ONLINE_SAFE credential semantics explicit", () => {
    const cloudDemo = renderToStaticMarkup(
      <SettingsViewV2
        credentialError={null}
        credentialPending={null}
        credentialStatus={{
          configured: true,
          provider: "Mock",
          source: "CLOUD_DEMO",
        }}
        project={null}
        onClearCredential={async () => undefined}
        onSaveCredential={async () => undefined}
      />,
    );
    const onlineSafe = renderToStaticMarkup(
      <SettingsViewV2
        credentialError={null}
        credentialPending={null}
        credentialStatus={{
          configured: false,
          provider: "OpenAI",
          source: "ONLINE_SAFE",
        }}
        project={null}
        onClearCredential={async () => undefined}
        onSaveCredential={async () => undefined}
      />,
    );

    expect(cloudDemo).toContain("演示模式");
    expect(cloudDemo).toContain("当前使用内置 Mock 模型，无需 API Key");
    expect(cloudDemo).not.toContain("OpenAI 兼容接口");
    expect(onlineSafe).toContain("凭据仅保存在当前在线会话中");
    expect(onlineSafe).toContain("12 小时");
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
