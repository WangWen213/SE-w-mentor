import { useEffect, useRef, useState } from "react";

import { Button } from "../components/Button";

interface NewTaskPageProps {
  disabled: boolean;
  error: string | null;
  pending: boolean;
  onSubmit: (request: string) => Promise<void>;
}

export function NewTaskPage({ disabled, error, pending, onSubmit }: NewTaskPageProps) {
  const [request, setRequest] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!request.trim() || pending || disabled) {
      return;
    }
    await onSubmit(request.trim());
    setRequest("");
  };

  return (
    <section className="view active workbench" aria-label="新任务">
      <header className="task-head">
        <div className="task-name-wrap">
          <div className="task-state">新任务</div>
          <h1 className="task-name">告诉 Mentor 你想修改什么</h1>
        </div>
      </header>
      <div className="empty-workbench">
        <div>
          <h2>先描述目标</h2>
          <p>Mentor 会先生成修改方案，并提示先分析治理；确认前不会立即修改。</p>
          {error ? (
            <div className="action-error" role="alert">
              <div>
                <strong>任务没有创建</strong>
                <span>{error}。请检查项目是否已打开，然后重新提交。</span>
              </div>
            </div>
          ) : null}
        </div>
      </div>
      <div className="composer-wrap show">
        <form className="composer" onSubmit={submit}>
          <label className="sr-only" htmlFor="new-task-request">
            新任务需求
          </label>
          <textarea
            ref={textareaRef}
            aria-label="新任务需求"
            disabled={pending || disabled}
            id="new-task-request"
            placeholder="例如：给用户模块增加 email 字段，并补充测试。"
            value={request}
            onChange={(event) => setRequest(event.currentTarget.value)}
          />
          <div className="composer-bottom">
            <span className="ghost">确认后才会进入后续治理和执行流程</span>
            <Button variant="dark" disabled={!request.trim() || pending || disabled} type="submit">
              {pending ? "创建中" : "创建任务"}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
