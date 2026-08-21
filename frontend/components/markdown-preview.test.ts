import { describe, expect, it } from "vitest";
import { safeHref, safeSrc } from "@/components/markdown-preview";

// Converted Markdown is untrusted: it comes from whatever document the user
// fed in. These two guards are what stop a crafted document from executing
// script or reaching off the machine, so they are tested directly.

describe("safeHref", () => {
  it("allows http, https and mailto", () => {
    expect(safeHref("https://example.com")).toBe("https://example.com");
    expect(safeHref("http://example.com")).toBe("http://example.com");
    expect(safeHref("mailto:a@b.co")).toBe("mailto:a@b.co");
  });

  it("allows in-document and relative targets", () => {
    expect(safeHref("#section")).toBe("#section");
    expect(safeHref("/jobs")).toBe("/jobs");
    expect(safeHref("./other.md")).toBe("./other.md");
  });

  it.each([
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "  javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
  ])("rejects %s", (url) => {
    expect(safeHref(url)).toBeUndefined();
  });

  it("rejects non-string input", () => {
    expect(safeHref(undefined)).toBeUndefined();
    expect(safeHref(new Blob())).toBeUndefined();
  });
});

describe("safeSrc", () => {
  it("allows inline image data URIs", () => {
    expect(safeSrc("data:image/png;base64,AAAA")).toBe("data:image/png;base64,AAAA");
  });

  it("rejects non-image data URIs", () => {
    expect(safeSrc("data:text/html,<script>alert(1)</script>")).toBeUndefined();
  });

  it("rejects remote images so rendering cannot phone home", () => {
    expect(safeSrc("https://tracker.example/pixel.png")).toBeUndefined();
    expect(safeSrc("//tracker.example/pixel.png")).toBeUndefined();
  });

  it("rewrites extracted figures onto the job's asset route", () => {
    const base = "/api/jobs/abc/assets/def";
    expect(safeSrc("assets/image-001.png", base)).toBe(`${base}/image-001.png`);
    expect(safeSrc("./assets/image-002.png", base)).toBe(`${base}/image-002.png`);
  });

  it("encodes the asset name", () => {
    const out = safeSrc("assets/my figure.png", "/api/jobs/a/assets/b");
    expect(out).toBe("/api/jobs/a/assets/b/my%20figure.png");
  });

  it("refuses to build an asset URL that escapes the directory", () => {
    const base = "/api/jobs/abc/assets/def";
    expect(safeSrc("assets/../../document.md", base)).toBeUndefined();
    expect(safeSrc("assets/sub/dir.png", base)).toBeUndefined();
    expect(safeSrc("assets/", base)).toBeUndefined();
  });

  it("leaves asset paths alone when no base is supplied", () => {
    expect(safeSrc("assets/image-001.png")).toBeUndefined();
  });
});
