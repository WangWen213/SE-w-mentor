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
          placeholder="\u7ee7\u7eed\u63cf\u8ff0\u4f60\u7684\u4fee\u6539\u76ee\u6807..."
        />
        <div className="composer-bottom">
          <Button className="ghost" variant="link">
            {"\u9644\u52a0\u8bf4\u660e"}
          </Button>
          <button aria-label="\u53d1\u9001\u6d88\u606f" className="send" type="submit">
            -&gt;
          </button>
        </div>
      </form>
    </div>
  );
}
