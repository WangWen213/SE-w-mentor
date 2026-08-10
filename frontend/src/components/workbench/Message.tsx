import type { MessageFixture } from "../../app/fixtures";

interface MessageProps {
  message: MessageFixture;
}

export function Message({ message }: MessageProps) {
  const isUser = message.author === "user";
  return (
    <article className={`message ${isUser ? "user" : "agent"}`}>
      <div className="msg-avatar" aria-hidden="true">
        {isUser ? "你" : "M"}
      </div>
      <div className="msg-wrap">
        <div className="msg-role">
          {isUser ? "你" : "Mentor"}
          <time className="msg-time">{message.time}</time>
        </div>
        <div className="msg-body">
          <p>{message.body}</p>
        </div>
      </div>
    </article>
  );
}
