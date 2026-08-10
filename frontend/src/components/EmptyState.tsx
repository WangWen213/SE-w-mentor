import { Button } from "./Button";

interface EmptyStateProps {
  title: string;
  body: string;
  action?: string;
}

export function EmptyState({ title, body, action }: EmptyStateProps) {
  return (
    <div className="state-card">
      <div>
        <strong>{title}</strong>
        <p>{body}</p>
        {action ? <Button>{action}</Button> : null}
      </div>
    </div>
  );
}
