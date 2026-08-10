import type { TaskTab } from "../../app/fixtures";

const tabs: Array<{ key: TaskTab; label: string }> = [
  { key: "conversation", label: "对话" },
  { key: "changes", label: "改动" },
  { key: "checks", label: "检查" },
];

interface TaskTabsProps {
  active: TaskTab;
  onChange: (tab: TaskTab) => void;
}

export function TaskTabs({ active, onChange }: TaskTabsProps) {
  return (
    <div aria-label="任务内容" className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          aria-controls={`tabpanel-${tab.key}`}
          aria-selected={active === tab.key}
          className={`tab ${active === tab.key ? "active" : ""}`}
          id={`tab-${tab.key}`}
          role="tab"
          type="button"
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
