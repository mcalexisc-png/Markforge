import { afterEach, describe, expect, it, vi } from "vitest";
import {
  confirmDiscardChanges,
  hasUnsavedChanges,
  setUnsavedChanges,
} from "@/lib/unsaved";

afterEach(() => {
  setUnsavedChanges(false);
  vi.restoreAllMocks();
});

describe("unsaved changes guard", () => {
  it("starts clean", () => {
    expect(hasUnsavedChanges()).toBe(false);
  });

  it("navigating is allowed with no unsaved work, without prompting", () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    expect(confirmDiscardChanges()).toBe(true);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("prompts when there are unsaved changes and honours a cancel", () => {
    setUnsavedChanges(true);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    expect(confirmDiscardChanges()).toBe(false);
  });

  it("allows navigation when the user confirms", () => {
    setUnsavedChanges(true);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    expect(confirmDiscardChanges()).toBe(true);
  });
});
