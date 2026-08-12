import type { WorkbenchMessage } from "../../app/fixtures";
import { LoadingText } from "./LoadingDots";
import { ProposalCard } from "./ProposalCard";
import { formatMessageTime } from "./messageTime";

const userLabel = "\u4f60";

interface MessageProps {
  message: WorkbenchMessage;
}

export function Message({ message }: MessageProps) {
  const isUser = message.role === "USER";
  const isSystem = message.role === "SYSTEM";
  const showLoadingDots =
    message.kind === "PROGRESS" &&
    message.role === "MENTOR" &&
    message.status === "PENDING";
  return (
    <article className={`message ${isUser ? "user" : "agent"} message-kind-${message.kind.toLowerCase()}`}>
      <div className="msg-avatar" aria-hidden="true">
        {isUser ? userLabel : isSystem ? "S" : "M"}
      </div>
      <div className="msg-wrap">
        <div className="msg-role">
          {isUser ? userLabel : isSystem ? "System" : "Mentor"}
          <time className="msg-time" dateTime={message.createdAt}>
            {formatMessageTime(message.createdAt)}
          </time>
        </div>
        {isUser ? (
          <div className="msg-body">
            <p>{message.text}</p>
          </div>
        ) : (
          <div className="msg-body">
            <div className="mentor-message-bubble">
              {showLoadingDots ? (
                <p className="message-progress-text">
                  <LoadingText text={message.text} />
                </p>
              ) : (
                <MessageText text={message.text} />
              )}
              {message.proposal ? <ProposalCard proposal={message.proposal} /> : null}
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

function MessageText({ text }: { text: string }) {
  const lines = text.split(/\r?\n/);
  return (
    <div className="message-text">
      {lines.map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) {
          return <span className="message-spacer" aria-hidden="true" key={index} />;
        }
        if (/^\d+\.\s+/.test(trimmed)) {
          return (
            <p className="message-list-title" key={index}>
              {trimmed}
            </p>
          );
        }
        if (trimmed.startsWith("- ")) {
          return (
            <p className="message-bullet" key={index}>
              {trimmed.slice(2)}
            </p>
          );
        }
        if (isSectionHeading(trimmed)) {
          return (
            <p className="message-section-heading" key={index}>
              {trimmed}
            </p>
          );
        }
        return <p key={index}>{trimmed}</p>;
      })}
    </div>
  );
}

function isSectionHeading(value: string): boolean {
  return ["已经完成", "还没有完成", "验证与治理状态", "建议下一步"].includes(value);
}
