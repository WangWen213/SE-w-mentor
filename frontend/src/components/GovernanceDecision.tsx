import type { GovernanceReport } from "../api/mentorApi";
import { governanceDecisionLabel } from "../api/mentorApi";
import { Button } from "./Button";

const text = {
  allowOnce: "允许本次",
  approvePending: "批准中",
  blockedBody: "后端治理判断该操作不可批准，不能通过用户授权绕过。",
  blockedTitle: "已阻止危险操作",
  cannotOverride: "不可通过授权绕过",
  continueTitle: "该修改可以按当前范围继续",
  deny: "暂不允许",
  execute: "执行",
  processing: "处理中",
  rules: "规则",
  sourceFallback: "治理结果来自后端。",
  unknown: "暂未确定",
  warnTitle: "需要你的确认",
};

interface GovernanceDecisionProps {
  approved?: boolean;
  onAllowOnce?: () => Promise<void>;
  onDeny?: () => Promise<void>;
  onExecute?: () => Promise<void>;
  pendingAction?: string | null;
  report: GovernanceReport;
}

export function GovernanceDecision({
  approved = false,
  onAllowOnce,
  onDeny,
  onExecute,
  pendingAction = null,
  report,
}: GovernanceDecisionProps) {
  const isBlock = report.decision === "BLOCK";
  const isWarn = report.decision === "WARN";

  return (
    <section className={`approval-card ${isBlock ? "block-card" : ""}`}>
      <div>
        <div className="approval-kicker">{governanceDecisionLabel(report.decision)}</div>
        <div className="approval-title">{decisionTitle(report)}</div>
        <div className="approval-sub">{decisionBody(report)}</div>
        <div className="approval-impact">
          {text.rules}：{report.ruleHits.map((hit) => presentReason(hit.reason)).join("、")}
        </div>
      </div>
      <div className="approval-actions">
        {isWarn ? (
          <>
            <Button disabled={pendingAction !== null || !onDeny} onClick={onDeny}>
              {pendingAction === "deny" ? text.processing : text.deny}
            </Button>
            <Button disabled={pendingAction !== null || !onAllowOnce} variant="dark" onClick={onAllowOnce}>
              {pendingAction === "allow" ? text.approvePending : text.allowOnce}
            </Button>
            {onExecute ? (
              <Button disabled={!approved || pendingAction !== null} variant="dark" onClick={onExecute}>
                {text.execute}
              </Button>
            ) : null}
          </>
        ) : null}
        {isBlock ? <Button disabled>{text.cannotOverride}</Button> : null}
        {report.decision === "ALLOW" && onExecute ? (
          <Button disabled={pendingAction !== null} variant="dark" onClick={onExecute}>
            {text.execute}
          </Button>
        ) : null}
      </div>
    </section>
  );
}

function decisionTitle(report: GovernanceReport): string {
  if (report.decision === "ALLOW") {
    return text.continueTitle;
  }
  if (report.decision === "WARN") {
    return text.warnTitle;
  }
  return text.blockedTitle;
}

function decisionBody(report: GovernanceReport): string {
  if (report.decision === "BLOCK") {
    return text.blockedBody;
  }
  return presentReason(report.inferences[0] ?? text.sourceFallback);
}

function presentReason(value: string) {
  const trimmed = value.trim();
  if (!trimmed || trimmed.toUpperCase() === "UNKNOWN") {
    return text.unknown;
  }
  const labels: Record<string, string> = {
    "Allowed within finite changed path scope.": "修改范围有限，符合当前批准范围。",
    "Public or authentication-related changes require user approval.": "公共接口或认证相关修改需要你的确认。",
    "Sensitive credential or environment files are blocked.": "敏感凭据或环境文件修改已被阻止。",
  };
  return labels[trimmed] ?? trimmed;
}
