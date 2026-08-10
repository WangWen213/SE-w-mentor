import type { ProposalFixture } from "../../app/fixtures";
import { Button } from "../Button";

interface ProposalCardProps {
  proposal: ProposalFixture;
}

export function ProposalCard({ proposal }: ProposalCardProps) {
  return (
    <section className="proposal" data-testid="proposal-card" aria-label="本次修改方案">
      <div className="proposal-head">本次方案</div>
      <div className="proposal-main">
        <div className="proposal-goal">{proposal.goal}</div>
      </div>
      <div className="proposal-list">
        {proposal.items.map((item) => (
          <div className="proposal-row" key={item}>
            <span className="proposal-dot" aria-hidden="true" />
            <span>{item}</span>
          </div>
        ))}
      </div>
      <div className="proposal-meta">
        <span>
          <b>影响</b> {proposal.files}
        </span>
        <span>
          <b>风险</b> {proposal.risk}
        </span>
      </div>
      <div className="proposal-foot">
        <span className="hint">确认后 Mentor 才会开始修改。</span>
        <Button>再调整</Button>
        <Button variant="dark">确认方案</Button>
      </div>
    </section>
  );
}
