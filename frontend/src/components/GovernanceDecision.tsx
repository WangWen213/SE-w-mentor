import type { GovernanceReport } from "../api/mentorApi";
import { governanceDecisionLabel } from "../api/mentorApi";
import { Button } from "./Button";

interface GovernanceDecisionProps {
  report: GovernanceReport;
}

export function GovernanceDecision({ report }: GovernanceDecisionProps) {
  const label = governanceDecisionLabel(report.decision);
  const isBlock = report.decision === "BLOCK";
  const isWarn = report.decision === "WARN";
  const decisionLegend = "自动允许 / 需要你的确认 / 始终阻止";

  return (
    <section className={`approval-card ${isBlock ? "block-card" : ""}`}>
      <div>
        <div className="approval-kicker">{label}</div>
        <span className="sr-only">{decisionLegend}</span>
        <div className="approval-title">{decisionTitle(report)}</div>
        <div className="approval-sub">{decisionBody(report)}</div>
        <div className="approval-impact">规则：{report.ruleHits.map((hit) => hit.reason).join("、")}</div>
      </div>
      <div className="approval-actions">
        {isWarn ? (
          <>
            <Button disabled>暂不允许</Button>
            <Button disabled variant="dark">
              执行授权将在下一阶段接入
            </Button>
          </>
        ) : null}
        {isBlock ? <Button disabled>不可通过授权绕过</Button> : null}
        {report.decision === "ALLOW" ? <Button disabled>后续执行将在下一阶段接入</Button> : null}
      </div>
    </section>
  );
}

function decisionTitle(report: GovernanceReport): string {
  if (report.decision === "ALLOW") {
    return "该修改可以按当前范围继续";
  }
  if (report.decision === "WARN") {
    return "需要你的确认";
  }
  return "已阻止危险操作";
}

function decisionBody(report: GovernanceReport): string {
  if (report.decision === "BLOCK") {
    return "后端治理判断该操作不可批准，不能通过用户授权绕过。";
  }
  return report.inferences[0] ?? "治理结果来自后端。";
}
