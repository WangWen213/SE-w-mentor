import { useState } from "react";

import type { GovernanceReport } from "../api/mentorApi";
import { Button } from "./Button";

interface ImpactReportProps {
  report: GovernanceReport;
}

export function ImpactReport({ report }: ImpactReportProps) {
  const [open, setOpen] = useState(false);

  return (
    <section className={`evidence-box ${open ? "open" : ""}`} aria-label="治理依据">
      <div className="approval-impact">
        影响范围：{report.impactScope.summary}{" "}
        <Button variant="link" onClick={() => setOpen((current) => !current)}>
          查看依据
        </Button>
      </div>
      {open ? (
        <div>
          <strong>主要依据</strong>
          {report.facts.map((fact) => (
            <p key={`${fact.file}:${fact.line}`}>
              {fact.summary}（{fact.file}:{fact.line}）
            </p>
          ))}
          <div className="evidence-unknown">
            <strong>推断</strong>
            {report.inferences.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
          {report.unknowns.length > 0 ? (
            <div className="evidence-unknown">
              <strong>还不能确认</strong>
              {report.unknowns.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </div>
          ) : null}
          <div className="evidence-unknown">
            <strong>证据</strong>
            {report.evidence.map((item) => (
              <p key={`${item.file}:${item.line}:${item.label}`}>
                {item.label}：{item.detail}（{item.file}:{item.line}）
              </p>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
