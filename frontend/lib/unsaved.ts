/**
 * Tracks whether an editor somewhere has unsaved changes.
 *
 * `beforeunload` only covers reloads and closing the tab; Next's client-side
 * navigation never triggers it. The header's links and the workspace's Back
 * link consult this before navigating, so a draft cannot be lost by a stray
 * click on "History".
 *
 * Deliberately a tiny module-level store rather than context: the header and
 * the workspace are not in a shared provider, and this is one boolean.
 */

let unsaved = false;

export function setUnsavedChanges(value: boolean): void {
  unsaved = value;
}

export function hasUnsavedChanges(): boolean {
  return unsaved;
}

/** Returns true when it is safe to navigate away. */
export function confirmDiscardChanges(
  message = "You have unsaved changes to this Markdown. Leave without saving?",
): boolean {
  if (!unsaved) return true;
  return window.confirm(message);
}
