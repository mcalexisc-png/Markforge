import { describe, expect, it } from "vitest";
import { cn, formatBytes } from "@/lib/utils";

describe("cn", () => {
  it("merges conflicting tailwind classes, last wins", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("drops falsy values", () => {
    expect(cn("a", false && "b", undefined, "c")).toBe("a c");
  });
});

describe("formatBytes", () => {
  it("formats zero", () => {
    expect(formatBytes(0)).toMatch(/0/);
  });

  it("scales units upward", () => {
    expect(formatBytes(1024)).toMatch(/KB/i);
    expect(formatBytes(1024 * 1024)).toMatch(/MB/i);
  });

  it("does not report bytes for a large value", () => {
    expect(formatBytes(5 * 1024 * 1024)).not.toMatch(/^\d+ B$/);
  });
});
