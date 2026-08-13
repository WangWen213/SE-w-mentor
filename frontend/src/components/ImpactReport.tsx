import { useState } from "react";

import type { GovernanceReport } from "../api/mentorApi";
import { Button } from "./Button";

const text = {
  collapse: "收起依据",
  evidence: "证据",
  impactEvidence: "影响证据",
  impactReport: "治理依据",
  impactScope: "影响范围",
  inference: "推断",
  mainEvidence: "主要依据",
  showEvidence: "查看依据",
  unknown: "暂未确定",
  unknowns: "尚未确定",
};

interface ImpactReportProps {
  report: GovernanceReport;
}

export function ImpactReport({ report }: ImpactReportProps) {
  const [open, setOpen] = useState(false);

  return (
    <section className={`evidence-box ${open ? "open" : ""}`} aria-label={text.impactReport}>
      <div className="approval-impact">
        {text.impactScope}：{impactScopeSummary(report)}{" "}
        <Button variant="link" onClick={() => setOpen((current) => !current)}>
          {open ? text.collapse : text.showEvidence}
        </Button>
      </div>
      {open ? (
        <div>
          <strong>{text.mainEvidence}</strong>
          {report.facts.map((fact) => (
            <p key={`${fact.file}:${fact.line}`}>
              {presentFact(fact.summary)}（{fact.file}:{fact.line}）
            </p>
          ))}
          <div className="evidence-unknown">
            <strong>{text.inference}</strong>
            {report.inferences.length > 0 ? (
              report.inferences.map((item) => <p key={item}>{presentReason(item)}</p>)
            ) : (
              <p>{text.unknown}</p>
            )}
          </div>
          {report.unknowns.length > 0 ? (
            <div className="evidence-unknown">
              <strong>{text.unknowns}</strong>
              {report.unknowns.map((item) => (
                <p key={item}>{presentUnknown(item)}</p>
              ))}
            </div>
          ) : null}
          <div className="evidence-unknown">
            <strong>{text.evidence}</strong>
            {report.evidence.map((item) => (
              <p key={`${item.file}:${item.line}:${item.label}`}>
                {presentEvidenceLabel(item.label)}：{presentUnknown(item.detail)}（{item.file}:{item.line}）
              </p>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function presentUnknown(value: string) {
  const trimmed = value.trim();
  return !trimmed || trimmed.toUpperCase() === "UNKNOWN" ? text.unknown : value;
}

function impactScopeSummary(report: GovernanceReport) {
  const count = report.impactScope.files.length || report.changedPaths.length;
  return count > 0 ? `${count} 个文件受影响` : text.unknown;
}

function presentEvidenceLabel(value: string) {
  return value === "impact_evidence" || value === "Impact evidence" ? text.impactEvidence : presentUnknown(value);
}

function presentFact(value: string) {
  const match = value.match(/^(FILE|TABLE|SYMBOL|MODULE) impact: (.*)$/i);
  if (!match) {
    return presentUnknown(value);
  }
  return `直接影响：${match[2] || text.unknown}`;
}

function presentReason(value: string) {
  const trimmed = value.trim();
  const labels: Record<string, string> = {
    "Allowed within finite changed path scope.": "修改范围有限，符合当前批准范围。",
    "Public or authentication-related changes require user approval.": "公共接口或认证相关修改需要你的确认。",
    "Sensitive credential or environment files are blocked.": "敏感凭据或环境文件修改已被阻止。",
  };
  return labels[trimmed] ?? presentUnknown(value);
}
