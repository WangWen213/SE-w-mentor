import { Button } from "../Button";

export function Composer() {
  return (
    <div className="composer-wrap show">
      <form className="composer">
        <label className="sr-only" htmlFor="mentor-composer">
          给 Mentor 发送消息
        </label>
        <textarea
          aria-label="给 Mentor 发送消息"
          id="mentor-composer"
          placeholder="继续描述你的修改目标..."
        />
        <div className="composer-bottom">
          <Button className="ghost" variant="link">
            附加说明
          </Button>
          <button aria-label="发送消息" className="send" type="submit">
            ↑
          </button>
        </div>
      </form>
    </div>
  );
}
