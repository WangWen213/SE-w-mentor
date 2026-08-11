import { useState } from "react";

import type { Project } from "../api/mentorApi";
import type { NavKey } from "./fixtures";
import { navItems } from "./fixtures";
import { Button } from "../components/Button";

interface AppShellProps {
  activeView: NavKey;
  children: React.ReactNode;
  onNewTask: () => void;
  onOpenProject: (rootPath: string) => void;
  onViewChange: (view: NavKey) => void;
  project: Project | null;
}

export function AppShell({
  activeView,
  children,
  onNewTask,
  onOpenProject,
  onViewChange,
  project,
}: AppShellProps) {
  const projectName = project?.id ?? "未打开项目";
  const branch = project?.branch ?? "main";
  const [rootPath, setRootPath] = useState(project?.rootPath ?? "");

  return (
    <div className="app">
      <aside className="sidebar" data-testid="mentor-sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            M
          </div>
          <div className="brand-name">Mentor</div>
        </div>

        <section className="project-card" aria-label="当前项目">
          <div className="project-label">当前项目</div>
          <div className="project-name">
            <span className="project-dot" aria-hidden="true" />
            {projectName}
          </div>
          <div className="project-meta">{branch} · 本地工作区</div>
          <form
            className="project-open-form"
            onSubmit={(event) => {
              event.preventDefault();
              onOpenProject(rootPath);
            }}
          >
            <label className="sr-only" htmlFor="project-root-path">
              本地 Git 项目路径
            </label>
            <input
              id="project-root-path"
              className="project-path-input"
              name="rootPath"
              placeholder="输入本地 Git 项目路径"
              type="text"
              value={rootPath}
              onChange={(event) => setRootPath(event.target.value)}
            />
            <button className="project-open" type="submit">
              打开本地项目
            </button>
          </form>
        </section>

        <nav aria-label="SE-Mentor 主导航" className="nav">
          {navItems.map((item) => (
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
              {item.count ? <span className="badge">{item.count}</span> : null}
            </button>
          ))}
        </nav>

        <div className="side-spacer" />
        <div className="side-bottom">
          <div className="profile">
            <div className="avatar" aria-hidden="true">
              WW
            </div>
            <div>
              <strong>本地使用者</strong>
              <small>Mock 模式可用</small>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar" data-testid="mentor-topbar">
          <div className="top-project">{projectName}</div>
          <div className="branch">{branch}</div>
          <div className="top-spacer" />
          <Button>同步状态</Button>
          <Button variant="dark" onClick={onNewTask}>
            新建任务
          </Button>
        </header>
        {children}
      </main>
    </div>
  );
}
