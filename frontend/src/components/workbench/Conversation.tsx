import { useEffect, useRef } from "react";

import type {
  TaskFixture,
  WorkbenchMessage,
  WorkbenchTimelineItem,
  WorkbenchTimelineTarget,
} from "../../app/fixtures";
import { Message } from "./Message";
import { formatMessageTime } from "./messageTime";

interface ConversationProps {
  confirmDisabled?: boolean;
  confirmLabel?: string;
  onAdjustProposal?: () => void;
  onConfirmProposal?: () => void;
  onTimelineAction?: (target: WorkbenchTimelineTarget) => void;
  task: TaskFixture;
}

type ConversationEntry =
  | { createdAt: string; id: string; item: WorkbenchMessage; type: "message" }
  | { createdAt: string; id: string; item: WorkbenchTimelineItem; type: "timeline" };

export function Conversation({
  confirmDisabled,
  confirmLabel,
  onAdjustProposal,
  onConfirmProposal,
  onTimelineAction,
  task,
}: ConversationProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const entries = conversationEntries(task.messages, task.timeline ?? []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [entries.length]);

  return (
    <section
      aria-labelledby="tab-conversation"
      className="panel active"
      id="tabpanel-conversation"
      role="tabpanel"
    >
      <div className="conversation">
        <div className="thread">
          {entries.map((entry) => (
            entry.type === "message" ? (
              <Message
                confirmDisabled={confirmDisabled}
                confirmLabel={confirmLabel}
                key={entry.id}
                message={entry.item}
                onAdjustProposal={onAdjustProposal}
                onConfirmProposal={onConfirmProposal}
              />
            ) : (
              <TimelineNode
                key={entry.id}
                item={entry.item}
                onAction={onTimelineAction}
              />
            )
          ))}
          <div ref={bottomRef} aria-hidden="true" />
        </div>
      </div>
    </section>
  );
}

export function conversationEntries(
  messages: WorkbenchMessage[],
  timeline: WorkbenchTimelineItem[],
): ConversationEntry[] {
  const entries: ConversationEntry[] = [
    ...messages.map((message) => ({
      createdAt: message.createdAt,
      id: `message:${message.id}`,
      item: message,
      type: "message" as const,
    })),
    ...timeline.map((item) => ({
      createdAt: item.createdAt,
      id: `timeline:${item.id}`,
      item,
      type: "timeline" as const,
    })),
  ];
  return entries.sort((a, b) => {
    const time = timestamp(a.createdAt) - timestamp(b.createdAt);
    return time === 0 ? a.id.localeCompare(b.id) : time;
  });
}

function TimelineNode({
  item,
  onAction,
}: {
  item: WorkbenchTimelineItem;
  onAction?: (target: WorkbenchTimelineTarget) => void;
}) {
  const action = item.action;
  return (
    <article className={`message agent process-node process-node-${item.status.toLowerCase()}`}>
      <div className="process-dot" aria-hidden="true" />
      <div className="msg-wrap">
        <div className="msg-role">
          Mentor
          <time className="msg-time" dateTime={item.createdAt}>
            {formatMessageTime(item.createdAt)}
          </time>
        </div>
        <div className="process-card">
          <strong>{item.title}</strong>
          <p>{item.body}</p>
          {action ? (
            <button
              className="process-link"
              type="button"
              onClick={() => onAction?.(action.target)}
            >
              {action.label}
            </button>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Number.MAX_SAFE_INTEGER : parsed;
}
