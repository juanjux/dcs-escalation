// Copy text to the clipboard from a page that is not in a secure context.
//
// The map is loaded from a file:// URL inside the Qt web view, and Chromium only
// exposes navigator.clipboard on https and localhost, so the modern API is not there
// at all and the copy failed silently. The textarea and execCommand route is
// deprecated but still works everywhere, and is the only one that works here.
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      // Falls through to the older route: a denied permission or an insecure context
      // both land here.
    }
  }

  const area = document.createElement("textarea");
  area.value = text;
  // Off-screen and unfocusable-looking, but it has to be in the document and visible
  // enough to be selectable, or the copy does nothing.
  area.style.position = "fixed";
  area.style.top = "-1000px";
  area.setAttribute("readonly", "");
  document.body.appendChild(area);
  try {
    area.select();
    area.setSelectionRange(0, text.length);
    return document.execCommand("copy");
  } catch (error) {
    console.error("Could not copy to the clipboard", error);
    return false;
  } finally {
    document.body.removeChild(area);
  }
}
