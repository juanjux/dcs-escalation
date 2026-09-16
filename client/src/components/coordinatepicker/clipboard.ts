// Copy text to the clipboard from the map.
//
// The map is loaded from a file:// URL inside the Qt web view, where
// navigator.clipboard is defined but rejects every write, so the copy goes through the
// deprecated textarea and execCommand route. That route needs
// JavascriptCanAccessClipboard on the page, which QLiberationMap sets.
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
