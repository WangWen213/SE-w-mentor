import { useEffect, useRef } from "react";

import type { TaskFixture } from "../../app/fixtures";
import { Message } from "./Message";

interface ConversationProps {
  task: TaskFixture;
}

export function Conversation({ task }: ConversationProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [task.messages.length]);

  return (
    <section
      aria-labelledby="tab-conversation"
      className="panel active"
      id="tabpanel-conversation"
      role="tabpanel"
    >
      <div className="conversation">
        <div className="thread">
          {task.messages.map((message) => (
            <Message key={message.id} message={message} />
          ))}
          <div ref={bottomRef} aria-hidden="true" />
        </div>
      </div>
    </section>
  );
}
