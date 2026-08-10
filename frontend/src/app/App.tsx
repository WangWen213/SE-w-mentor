import { useState } from "react";

import { cards, type NavKey, type TaskTab, taskFixture } from "./fixtures";
import { AppShell } from "./AppShell";
import { Button } from "../components/Button";
import { Drawer } from "../components/Drawer";
import { EmptyState } from "../components/EmptyState";
import { Modal } from "../components/Modal";
import { StatusBadge } from "../components/StatusBadge";
import { ChangesPanel } from "../components/workbench/ChangesPanel";
import { ChecksPanel } from "../components/workbench/ChecksPanel";
import { Composer } from "../components/workbench/Composer";
import { Conversation } from "../components/workbench/Conversation";
import { TaskHeader } from "../components/workbench/TaskHeader";
import { TaskTabs } from "../components/workbench/TaskTabs";

export function App() {
  const [activeView, setActiveView] = useState<NavKey>("workbench");
  const [activeTab, setActiveTab] = useState<TaskTab>("conversation");
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <AppShell activeView={activeView} onViewChange={setActiveView}>
      {activeView === "workbench" ? (
        <WorkbenchView
          activeTab={activeTab}
          onModalOpen={() => setModalOpen(true)}
          onTabChange={setActiveTab}
        />
      ) : null}
      {activeView === "tasks" ? <TasksView /> : null}
      {activeView === "memory" ? <MemoryView onOpenDrawer={() => setDrawerOpen(true)} /> : null}
      {activeView === "governance" ? <GovernanceView /> : null}
      {activeView === "evaluation" ? <EvaluationView /> : null}
      {activeView === "settings" ? <SettingsView /> : null}
      <Modal open={modalOpen} title="任务已停止" onClose={() => setModalOpen(false)}>
        本次已修改 3 个文件。你可以保留当前改动，也可以回滚本次任务产生的修改。
      </Modal>
      <Drawer open={drawerOpen} title="项目经验" onClose={() => setDrawerOpen(false)}>
        <div className="detail-section">
          <div className="detail-label">内容</div>
          <div className="detail-text">用户模块字段变化需要同步 schema、service 与相关测试。</div>
        </div>
      </Drawer>
      <div className="toast" role="status" aria-live="polite">
        当前为本地演示数据
      </div>
    </AppShell>
  );
}

function WorkbenchView({
  activeTab,
  onModalOpen,
  onTabChange,
}: {
  activeTab: TaskTab;
  onModalOpen: () => void;
  onTabChange: (tab: TaskTab) => void;
}) {
  return (
    <section className="view active workbench" aria-label="工作台">
      <TaskHeader task={taskFixture} onStop={onModalOpen} />
      <TaskTabs active={activeTab} onChange={onTabChange} />
      {activeTab === "conversation" ? <Conversation task={taskFixture} /> : null}
      <ChangesPanel active={activeTab === "changes"} task={taskFixture} />
      <ChecksPanel active={activeTab === "checks"} task={taskFixture} />
      <Composer />
    </section>
  );
}

function TasksView() {
  return (
    <Page title="任务" action="新建任务">
      <div className="task-list">
        {cards.tasks.map(([title, state, statusClass]) => (
          <button className="task-card" key={title} type="button">
            <span>
              <span className="task-card-title">{title}</span>
              <span className="task-card-meta">SE-w-mentor · 最近更新</span>
            </span>
            <span className={`status ${statusClass}`}>{state}</span>
          </button>
        ))}
      </div>
    </Page>
  );
}

function MemoryView({ onOpenDrawer }: { onOpenDrawer: () => void }) {
  return (
    <Page title="记忆">
      <div className="memory-tools">
        <button className="filter active" type="button">
          全部
        </button>
        <button className="filter" type="button">
          已验证
        </button>
        <button className="filter" type="button">
          待复核
        </button>
      </div>
      <div className="memory-list">
        {cards.memory.map(([title, text, state]) => (
          <button className="memory-card" key={title} type="button" onClick={onOpenDrawer}>
            <span className="memory-icon" aria-hidden="true">
              M
            </span>
            <span>
              <span className="memory-title">{title}</span>
              <span className="memory-text">{text}</span>
              <span className="memory-meta">
                <span className="memory-tag ok">{state}</span>
                <span>来源：最近任务</span>
              </span>
            </span>
            <span className="memory-date">今天</span>
          </button>
        ))}
      </div>
    </Page>
  );
}

function GovernanceView() {
  return (
    <Page title="治理" action="查看当前规则">
      <section className="approval-card">
        <div>
          <div className="approval-kicker">需要确认</div>
          <div className="approval-title">公共接口变化需要你确认范围</div>
          <div className="approval-sub">Mentor 会在确认后继续，不会自行扩大修改。</div>
        </div>
        <div className="approval-actions">
          <Button>查看依据</Button>
          <Button variant="dark">允许本次</Button>
        </div>
      </section>
      <div className="policy-list">
        {cards.policies.map(([level, items]) => (
          <div className="policy-row" key={level}>
            <div className="policy-level">
              <span className={`level-dot ${level === "允许" ? "allow" : level === "阻止" ? "block" : "ask"}`} />
              {level}
            </div>
            <div className="policy-items">
              {items.split("、").map((item) => (
                <span className="policy-chip" key={item}>
                  {item}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Page>
  );
}

function EvaluationView() {
  return (
    <Page title="评估" action="查看完整记录">
      <section className="result-card">
        <div className="result-top">
          <div className="result-icon" aria-hidden="true">
            ✓
          </div>
          <div>
            <div className="result-title">最近一次任务已通过全部检查</div>
            <div className="result-time">补充订单字段校验 · 昨天 21:16</div>
          </div>
        </div>
        <div className="result-summary">
          <span>
            <b>4</b> 个文件修改
          </span>
          <span>
            <b>18</b> 项检查通过
          </span>
          <span>没有超出已确认范围</span>
        </div>
        <div className="check-grid">
          {["需求已满足", "相关测试已通过", "修改没有超出范围", "没有待处理确认"].map((item) => (
            <div className="check-item" key={item}>
              <i>✓</i>
              {item}
            </div>
          ))}
        </div>
      </section>
    </Page>
  );
}

function SettingsView() {
  return (
    <Page title="设置">
      <div className="settings-grid">
        <section className="setting-card">
          <div className="setting-head">
            <div className="setting-title">模型与凭据</div>
            <StatusBadge tone="allow">已配置</StatusBadge>
          </div>
          <div className="setting-row">
            <div className="setting-label">OpenAI</div>
            <div className="setting-value">
              凭据已配置
              <span className="setting-sub">Windows 凭据管理器</span>
            </div>
            <div className="page-actions">
              <Button size="small">更新</Button>
              <Button size="small" variant="danger">
                删除
              </Button>
            </div>
          </div>
        </section>
        <EmptyState title="本地项目" body="当前目录：C:\\Users\\ww\\Desktop\\SE-w-mentor" />
      </div>
    </Page>
  );
}

function Page({
  action,
  children,
  title,
}: {
  action?: string;
  children: React.ReactNode;
  title: string;
}) {
  return (
    <section className="view active">
      <div className="page">
        <div className="page-head">
          <h1 className="page-title">{title}</h1>
          {action ? (
            <div className="page-actions">
              <Button>{action}</Button>
            </div>
          ) : null}
        </div>
        {children}
      </div>
    </section>
  );
}
