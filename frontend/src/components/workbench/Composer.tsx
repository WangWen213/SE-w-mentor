import { Button } from "../Button";

const sendLabel = "\u7ed9 Mentor \u53d1\u9001\u6d88\u606f";

export function Composer() {
  return (
    <div className="composer-wrap show">
      <form className="composer">
        <label className="sr-only" htmlFor="mentor-composer">
          {sendLabel}
        </label>
        <textarea
          aria-label={sendLabel}
          id="mentor-composer"
          placeholder="继续描述你的修改目标..."
        />
        <div className="composer-bottom">
          <Button className="ghost" variant="link">
            {"\u9644\u52a0\u8bf4\u660e"}
          </Button>
          <button aria-label="发送消息" className="send" type="submit">
            -&gt;
          </button>
        </div>
      </form>
    </div>
  );
}
