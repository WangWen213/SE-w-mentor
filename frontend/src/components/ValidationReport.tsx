import type { CompletionGate, ValidationResult } from "../api/mentorApi";
import { StatusBadge } from "./StatusBadge";

interface ValidationReportProps {
  gates: CompletionGate[];
  results: ValidationResult[];
}

export function ValidationReport({ gates, results }: ValidationReportProps) {
  return (
    <section className="result-card" aria-label="验证结果">
      <div className="result-title">验证与完成门禁</div>
      <div className="check-grid">
        {gates.map((gate) => (
          <div className="check-item" key={gate.label}>
            <i>{gate.status === "PASS" ? "✓" : "!"}</i>
            <span>{gate.label}</span>
            <StatusBadge tone={gate.status === "PASS" ? "allow" : "warn"}>{gate.status}</StatusBadge>
          </div>
        ))}
      </div>
      <div className="memory-list">
        {results.map((result) => (
          <div className="memory-card" key={result.name}>
            <span className="memory-icon" aria-hidden="true">
              V
            </span>
            <span>
              <span className="memory-title">{result.name}</span>
              <span className="memory-text">{result.message}</span>
              <span className="memory-meta">
                <span className={result.status === "PASS" ? "memory-tag ok" : "memory-tag warn"}>
                  {result.status}
                </span>
                {result.failureCategory ? <span>{result.failureCategory}</span> : null}
              </span>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
