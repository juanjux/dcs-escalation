/**
 * The map is loaded from a file:// URL inside the Qt web view, where Chromium does not
 * expose navigator.clipboard at all, so the copy has to fall back to execCommand.
 */
import { copyText } from "./clipboard";

describe("copyText", () => {
  const clipboard = navigator.clipboard;

  afterEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: clipboard,
      configurable: true,
    });
    delete (document as any).execCommand;
  });

  function withClipboard(writeText: undefined | jest.Mock) {
    Object.defineProperty(navigator, "clipboard", {
      value: writeText === undefined ? undefined : { writeText },
      configurable: true,
    });
  }

  it("uses the modern API where there is one", async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    withClipboard(writeText);

    expect(await copyText("N36°35.316'")).toBe(true);
    expect(writeText).toHaveBeenCalledWith("N36°35.316'");
  });

  it("falls back when the page has no clipboard API", async () => {
    withClipboard(undefined);
    const exec = jest.fn().mockReturnValue(true);
    (document as any).execCommand = exec;

    expect(await copyText("N36°35.316'")).toBe(true);
    expect(exec).toHaveBeenCalledWith("copy");
  });

  it("falls back when the modern API refuses", async () => {
    withClipboard(jest.fn().mockRejectedValue(new Error("not allowed")));
    const exec = jest.fn().mockReturnValue(true);
    (document as any).execCommand = exec;

    expect(await copyText("N36°35.316'")).toBe(true);
    expect(exec).toHaveBeenCalledWith("copy");
  });

  it("leaves nothing behind in the document", async () => {
    withClipboard(undefined);
    (document as any).execCommand = jest.fn().mockReturnValue(true);

    await copyText("N36°35.316'");

    expect(document.querySelectorAll("textarea").length).toBe(0);
  });

  it("says so when neither route works", async () => {
    withClipboard(undefined);
    (document as any).execCommand = jest.fn().mockReturnValue(false);

    expect(await copyText("N36°35.316'")).toBe(false);
  });
});
