import type { TaskFixture } from "../../app/fixtures";
import { Message } from "./Message";
import { ProposalCard } from "./ProposalCard";

interface ConversationProps {
  task: TaskFixture;
}

export function Conversation({ task }: ConversationProps) {
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
          <ProposalCard proposal={task.proposal} />
        </div>
      </div>
    </section>
  );
}
