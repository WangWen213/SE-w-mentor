import type { ProposalFixture } from "../../app/fixtures";

const label = {
  acceptance: "验收标准",
  change: "准备修改",
  current: "当前方案",
  decisionComplete: "完整，可确认",
  decisionClarification: "需要你决定",
  decisionTechnical: "Mentor 正在补全技术分析",
  expected: "目标",
  foot: "确认后 Mentor 才会进入正式影响分析、治理检查和执行。",
  impact: "预期影响",
  nonGoal: "不在本次范围",
  proposal: "本次修改方案",
  proposalHead: "本次方案",
  risk: "主要风险",
  step: "准备怎么改",
  superseded: "已被新版方案替代",
  technical: "技术待补全",
  understanding: "需求理解",
  unknown: "暂未确定",
  userDecision: "需要你决定",
  validation: "验证计划",
};

interface ProposalCardProps {
  confirmDisabled?: boolean;
  confirmLabel?: string;
  onAdjust?: () => void;
  onConfirm?: () => void;
  proposal: ProposalFixture;
}

export function ProposalCard({
  confirmDisabled = false,
  confirmLabel,
  onAdjust,
  onConfirm,
  proposal,
}: ProposalCardProps) {
  const display = proposal.display;
  const completeness = proposal.completeness;
  const preparedChanges = display?.preparedChanges ?? proposal.changes ?? [];
  const risks = display?.risks ?? (proposal.risk ? [proposal.risk] : []);
  const validation = display?.validation ?? proposal.validation ?? [];
  const userDecisions = display?.needsUserDecision ?? ["暂无需要你决定的问题。"];
  const expectedImpact = display?.expectedImpact ?? [proposal.files];
  const canShowActions = !proposal.superseded && proposal.status !== "CONFIRMED" && proposal.status !== "SUPERSEDED";
  return (
    <section className="proposal" data-testid="proposal-card" aria-label={label.proposal}>
      <div className="proposal-head">
        {proposal.version ? `Proposal v${proposal.version}` : label.proposalHead}
        <span className="proposal-state">
          {proposal.superseded || proposal.status === "SUPERSEDED" ? label.superseded : label.current}
        </span>
      </div>
      {completeness ? <CompletenessPill decision={completeness.decision} /> : null}
      <div className="proposal-main">
        <div className="proposal-goal">{presentValue(display?.title ?? proposal.goal)}</div>
      </div>
      <ProposalSection title={label.understanding} values={[display?.understanding ?? proposal.understanding ?? ""]} />
      <ProposalSection title={label.expected} values={[display?.goal ?? proposal.expectedBehavior ?? ""]} />
      <ProposalChangeSection changes={preparedChanges} />
      <ProposalSection title={label.step} values={display?.steps ?? proposal.steps ?? []} numbered />
      <ProposalSection title={label.impact} values={expectedImpact} />
      <ProposalSection title={label.risk} values={risks} />
      <ProposalSection title={label.validation} values={validation} />
      <ProposalSection title={label.nonGoal} values={display?.nonGoals ?? proposal.nonGoals ?? []} />
      {display?.technicalUnknowns && display.technicalUnknowns.length > 0 ? (
        <ProposalSection title={label.technical} values={display.technicalUnknowns} />
      ) : null}
      <ProposalSection title={label.userDecision} values={userDecisions} />
      <div className="proposal-foot">
        <span className="hint">{label.foot}</span>
        {canShowActions && onAdjust ? (
          <button className="btn small" type="button" onClick={onAdjust}>
            方案调整
          </button>
        ) : null}
        {canShowActions && onConfirm ? (
          <button className="btn small dark" disabled={confirmDisabled} type="button" onClick={onConfirm}>
            {confirmLabel ?? "确认此范围"}
          </button>
        ) : null}
      </div>
    </section>
  );
}

function CompletenessPill({ decision }: { decision: string }) {
  const text =
    decision === "COMPLETE"
      ? label.decisionComplete
      : decision === "NEEDS_USER_CLARIFICATION"
        ? label.decisionClarification
        : label.decisionTechnical;
  return <div className={`proposal-completeness ${decision.toLowerCase()}`}>{text}</div>;
}

function ProposalChangeSection({ changes }: { changes: Array<{ action: string; path: string; reason: string; symbol?: string | null }> }) {
  if (changes.length === 0) {
    return null;
  }
  return (
    <div className="proposal-list">
      <div className="proposal-section-title">{label.change}</div>
      {changes.map((change, index) => (
        <div className="proposal-row" key={`${change.path}:${change.symbol ?? ""}:${index}`}>
          <span className="proposal-dot" aria-hidden="true" />
          <span>
            <b>{String(index + 1).padStart(2, "0")} {presentValue(change.path)}</b>
            {change.symbol ? ` / ${change.symbol}` : ""}
            <br />
            {presentValue(change.action)}
            <br />
            {presentValue(change.reason)}
          </span>
        </div>
      ))}
    </div>
  );
}

function ProposalSection({ numbered = false, title, values }: { numbered?: boolean; title: string; values: string[] }) {
  const visible = values.map(presentValue).filter((value) => value !== label.unknown);
  if (visible.length === 0) {
    return null;
  }
  return (
    <div className="proposal-list">
      <div className="proposal-section-title">{title}</div>
      {visible.map((value, index) => (
        <div className="proposal-row" key={`${title}:${value}:${index}`}>
          <span className="proposal-dot" aria-hidden="true" />
          <span>{numbered ? `${index + 1}. ` : ""}{value}</span>
        </div>
      ))}
    </div>
  );
}

function presentValue(value: string) {
  const trimmed = value.trim();
  if (!trimmed || trimmed.toUpperCase() === "UNKNOWN") {
    return label.unknown;
  }
  if (/^scope is unknown$/i.test(trimmed)) {
    return label.unknown;
  }
  return value;
}
