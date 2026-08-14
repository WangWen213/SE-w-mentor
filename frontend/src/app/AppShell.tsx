import type { ReactNode } from "react";

import type { Project } from "../api/mentorApi";
import { Button } from "../components/Button";
import type { NavKey } from "./fixtures";
import { navItems } from "./fixtures";

const shellText = {
  booting: "\u6b63\u5728\u6062\u590d\u5de5\u4f5c\u53f0",
  bootstrapFailed: "\u9879\u76ee\u5206\u6790\u5931\u8d25\uff0c\u4ecd\u53ef\u8fdb\u5165\u5de5\u4f5c\u53f0",
  bootstrapping: "\u6b63\u5728\u5206\u6790\u9879\u76ee",
  currentProject: "\u5f53\u524d\u9879\u76ee",
  localUser: "\u672c\u5730\u4f7f\u7528\u8005",
  localWorkbench: "\u672c\u5730\u5de5\u4f5c\u53f0",
  nav: "SE-Mentor \u4e3b\u5bfc\u822a",
  newTask: "\u65b0\u5efa\u4efb\u52a1",
  noProject: "\u672a\u6253\u5f00\u9879\u76ee",
  openLocalRepo: "\u6253\u5f00\u672c\u5730\u4ed3\u5e93",
  opening: "\u6b63\u5728\u6253\u5f00",
  ready: "\u9879\u76ee\u5206\u6790\u5b8c\u6210",
  registered: "\u9879\u76ee\u5df2\u6ce8\u518c",
  selectRepo: "\u8bf7\u9009\u62e9\u672c\u5730 Git \u4ed3\u5e93",
  uploadProject: "\u4e0a\u4f20\u9879\u76ee",
  uploadZip: "\u4e0a\u4f20 ZIP \u9879\u76ee",
};

interface AppShellProps {
  activeView: NavKey;
  children: ReactNode;
  onNewTask: () => void;
  onOpenProject: () => void;
  onViewChange: (view: NavKey) => void;
  onlineSafe?: boolean;
  projectHydrationState?: "BOOTING" | "READY" | "EMPTY" | "ERROR";
  project: Project | null;
  projectBootstrap: Project["bootstrap"] | null;
  projectError: string | null;
  projectOpening: boolean;
  taskCount: number;
}

export function AppShell({
  activeView,
  children,
  onNewTask,
  onOpenProject,
  onViewChange,
  onlineSafe = false,
  projectHydrationState = "READY",
  project,
  projectBootstrap,
  projectError,
  projectOpening,
  taskCount,
}: AppShellProps) {
  const projectName = project?.rootPath
    ? project.rootPath.replaceAll("\\", "/").split("/").filter(Boolean).at(-1) ?? project.id
    : projectHydrationState === "BOOTING"
      ? shellText.booting
      : shellText.noProject;
  const branch = project?.branch ?? "main";
  const openProjectLabel = onlineSafe ? shellText.uploadProject : shellText.openLocalRepo;

  return (
    <div className="app">
      <aside className="sidebar" data-testid="mentor-sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            M
          </div>
          <div className="brand-name">Mentor</div>
        </div>

        <section className="project-card" aria-label={shellText.currentProject}>
          <div className="project-label">{shellText.currentProject}</div>
          <div className="project-name">
            <span className="project-dot" aria-hidden="true" />
            {projectName}
          </div>
          <div className="project-meta">
            {project
              ? `${branch} - ${project.rootPath ?? project.id}`
              : projectHydrationState === "BOOTING"
                ? shellText.booting
                : onlineSafe
                  ? shellText.uploadZip
                  : shellText.selectRepo}
          </div>
          {project && projectBootstrap?.status && projectBootstrap.status !== "READY" ? (
            <div className={`project-bootstrap ${projectBootstrap.status.toLowerCase()}`}>
              {projectBootstrap.message ?? bootstrapStatusLabel(projectBootstrap.status)}
            </div>
          ) : null}
          <button
            className="project-open"
            disabled={projectOpening}
            type="button"
            onClick={onOpenProject}
          >
            {projectOpening ? shellText.opening : openProjectLabel}
          </button>
          {projectError ? (
            <div className="project-error" role="alert">
              {projectError}
            </div>
          ) : null}
        </section>

        <nav aria-label={shellText.nav} className="nav">
          {navItems.map((item) => {
            const count = item.key === "tasks" && taskCount > 0 ? String(taskCount) : undefined;
            return (
              <button
                key={item.key}
                aria-current={activeView === item.key ? "page" : undefined}
                className={`nav-item ${activeView === item.key ? "active" : ""}`}
                type="button"
                onClick={() => onViewChange(item.key)}
              >
                <span className="nav-marker" aria-hidden="true">
                  {item.marker}
                </span>
                <span>{item.label}</span>
                {count ? <span className="badge">{count}</span> : null}
              </button>
            );
          })}
        </nav>

        <div className="side-spacer" />
        <div className="side-bottom">
          <div className="profile">
            <div className="avatar" aria-hidden="true">
              WW
            </div>
            <div>
              <strong>{shellText.localUser}</strong>
              <small>{shellText.localWorkbench}</small>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar" data-testid="mentor-topbar">
          <div className="top-project">{projectName}</div>
          <div className="branch">{branch}</div>
          <div className="top-spacer" />
          <Button variant="dark" onClick={onNewTask}>
            {shellText.newTask}
          </Button>
        </header>
        {children}
      </main>
    </div>
  );
}

function bootstrapStatusLabel(status: NonNullable<Project["bootstrap"]>["status"]): string {
  const labels = {
    BOOTSTRAP_FAILED: shellText.bootstrapFailed,
    BOOTSTRAPPING: shellText.bootstrapping,
    READY: shellText.ready,
    REGISTERED: shellText.registered,
  };
  return labels[status];
}
