import type { DiffTrace } from "../api/mentorApi";

interface DiffViewerProps {
  trace: DiffTrace | null;
}

export function DiffViewer({ trace }: DiffViewerProps) {
  if (!trace) {
    return (
      <section className="result-card" aria-label="代码差异">
        <div className="result-title">尚未产生可展示的后端 Diff</div>
        <p className="detail-text">等待后端返回真实文件变更记录。</p>
      </section>
    );
  }

  return (
    <section className="result-card" aria-label="代码差异">
      <div className="result-top">
        <div>
          <div className="result-title">{trace.filePath}</div>
          <div className="result-time">
            {trace.modified ? "已修改" : "未修改"} · {trace.backedUp ? "已备份" : "未备份"} ·{" "}
            {trace.rolledBack ? "已回滚" : "未回滚"}
          </div>
        </div>
      </div>
      <div className="diff-viewer">
        {trace.lines.map((line) => (
          <div
            className={`diff-line ${line.type} ${line.outsideScope ? "outside-scope" : ""}`}
            key={`${line.type}-${line.lineNumber}-${line.content}`}
          >
            <span className="diff-stat">{line.lineNumber}</span>
            <code>{line.content}</code>
            {line.outsideScope ? <span className="memory-tag warn">范围外</span> : null}
          </div>
        ))}
      </div>
    </section>
  );
}
