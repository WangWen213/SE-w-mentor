import type { BadgeTone } from "../app/fixtures";

interface StatusBadgeProps {
  children: string;
  tone: BadgeTone;
}

const toneLabels: Record<BadgeTone, string> = {
  allow: "允许",
  warn: "需要确认",
  block: "阻止",
  neutral: "等待",
  info: "运行中",
};

export function StatusBadge({ children, tone }: StatusBadgeProps) {
  return (
    <span
      aria-label={`${toneLabels[tone]}：${children}`}
      className={`status-badge ${tone}`}
      role="status"
    >
      <span aria-hidden="true" className="status-dot" />
      <span>{children}</span>
    </span>
  );
}
