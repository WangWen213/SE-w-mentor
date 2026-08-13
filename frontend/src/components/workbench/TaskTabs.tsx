import type { TaskTab } from "../../app/fixtures";

const tabs: Array<{ key: TaskTab; label: string }> = [
  { key: "conversation", label: "\u5bf9\u8bdd" },
  { key: "changes", label: "\u6539\u52a8" },
  { key: "checks", label: "\u68c0\u67e5" },
];

interface TaskTabsProps {
  active: TaskTab;
  onChange: (tab: TaskTab) => void;
}

export function TaskTabs({ active, onChange }: TaskTabsProps) {
  return (
    <div aria-label="\u4efb\u52a1\u5185\u5bb9" className="tabs" role="tablist">
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
