import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { NewTaskPage, canSubmitComposerRequest } from "../pages/NewTaskPage";

describe("composer runtime corrective", () => {
  it("renders an editable composer control, not a presentation-only mock", () => {
    const html = renderToStaticMarkup(
      <NewTaskPage
        disabled={false}
        error={null}
        errorTitle={null}
        pending={false}
        stage="IDLE"
        onOpenSettings={() => undefined}
        onSubmit={async () => undefined}
      />,
    );

    expect(html).toContain("<textarea");
    expect(html).toContain("id=\"new-task-request\"");
    expect(html).toContain("type=\"submit\"");
    expect(html).not.toContain("The requested behavior is implemented within the confirmed scope.");
    expect(html).not.toContain("Do not modify files outside the confirmed execution boundary.");
  });

  it("uses one submit contract for click and Enter paths", () => {
    expect(canSubmitComposerRequest("Update README", false, false)).toBe(true);
    expect(canSubmitComposerRequest("   ", false, false)).toBe(false);
    expect(canSubmitComposerRequest("Update README", true, false)).toBe(false);
    expect(canSubmitComposerRequest("Update README", false, true)).toBe(false);
  });
});
