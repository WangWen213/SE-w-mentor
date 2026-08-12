import { useEffect, useRef, useState } from "react";

import { Button } from "../components/Button";

export type NewTaskStage =
  | "IDLE"
  | "TASK_CREATING"
  | "TASK_CREATED"
  | "PROPOSAL_GENERATING"
  | "PROPOSAL_READY"
  | "PROPOSAL_FAILED";

const text = {
  aria: "\u65b0\u4efb\u52a1",
  buttonCreate: "\u521b\u5efa\u4efb\u52a1\u4e2d",
  buttonGenerate: "\u751f\u6210\u65b9\u6848\u4e2d",
  buttonSend: "\u53d1\u9001",
  disabledBody: "\u9009\u62e9\u4e00\u4e2a\u672c\u5730 Git \u4ed3\u5e93\u540e\uff0c\u5c31\u53ef\u4ee5\u521b\u5efa\u4efb\u52a1\u3002",
  disabledTitle: "\u5148\u6253\u5f00\u672c\u5730\u4ed3\u5e93",
  hint: "\u786e\u8ba4\u65b9\u6848\u540e\u624d\u4f1a\u8fdb\u5165\u6cbb\u7406\u548c\u6267\u884c\u6d41\u7a0b",
  openSettings: "\u524d\u5f80\u8bbe\u7f6e",
  placeholder: "\u4f8b\u5982\uff1a\u66f4\u65b0 auth middleware\uff0c\u5e76\u8865\u5145\u76f8\u5173\u6d4b\u8bd5\u3002",
  requestLabel: "\u65b0\u4efb\u52a1\u9700\u6c42",
  taskCreateFailed: "\u4efb\u52a1\u6ca1\u6709\u521b\u5efa",
  title: "\u544a\u8bc9 Mentor \u4f60\u60f3\u4fee\u6539\u4ec0\u4e48",
  readyBody: "Mentor \u4f1a\u5148\u751f\u6210\u4fee\u6539\u65b9\u6848\uff1b\u786e\u8ba4\u524d\u4e0d\u4f1a\u4fee\u6539\u6587\u4ef6\u3002",
  readyTitle: "\u5148\u63cf\u8ff0\u76ee\u6807",
};

interface NewTaskPageProps {
  disabled: boolean;
  error: string | null;
  errorTitle: string | null;
  onOpenSettings: () => void;
  pending: boolean;
  stage: NewTaskStage;
  onSubmit: (request: string) => Promise<void>;
}

export function NewTaskPage({
  disabled,
  error,
  errorTitle,
  onOpenSettings,
  pending,
  stage,
  onSubmit,
}: NewTaskPageProps) {
  const [request, setRequest] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmitComposerRequest(request, pending, disabled)) {
      return;
    }
    try {
      await onSubmit(request.trim());
      setRequest("");
    } catch {
      textareaRef.current?.focus();
    }
  };

  return (
    <section className="view active workbench" aria-label={text.aria}>
      <header className="task-head">
        <div className="task-name-wrap">
          <div className="task-state">{text.aria}</div>
          <h1 className="task-name">{text.title}</h1>
        </div>
      </header>
      <div className="empty-workbench">
        <div>
          <h2>{disabled ? text.disabledTitle : text.readyTitle}</h2>
          <p>{disabled ? text.disabledBody : text.readyBody}</p>
          {error ? (
            <div className="action-error" role="alert">
              <div>
                <strong>{errorTitle ?? text.taskCreateFailed}</strong>
                <span>{error}</span>
              </div>
              {isProviderError(error) ? <Button onClick={onOpenSettings}>{text.openSettings}</Button> : null}
            </div>
          ) : null}
        </div>
      </div>
      <div className="composer-wrap show">
        <form className="composer" onSubmit={submit}>
          <label className="sr-only" htmlFor="new-task-request">
            {text.requestLabel}
          </label>
          <textarea
            ref={textareaRef}
            aria-label={text.requestLabel}
            disabled={pending || disabled}
            id="new-task-request"
            placeholder={text.placeholder}
            value={request}
            onChange={(event) => setRequest(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="composer-bottom">
            <span className="ghost">{text.hint}</span>
            <Button variant="dark" disabled={!request.trim() || pending || disabled} type="submit">
              {buttonLabel(stage)}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}

export function canSubmitComposerRequest(request: string, pending: boolean, disabled: boolean) {
  return Boolean(request.trim()) && !pending && !disabled;
}

function buttonLabel(stage: NewTaskStage): string {
  if (stage === "TASK_CREATING") {
    return text.buttonCreate;
  }
  if (stage === "PROPOSAL_GENERATING") {
    return text.buttonGenerate;
  }
  return text.buttonSend;
}

function isProviderError(error: string) {
  return error.includes("PROVIDER_UNAVAILABLE") || error.includes("\u51ed\u636e") || error.includes("API Key");
}
