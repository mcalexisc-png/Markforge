import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AuthRequiredError,
  UploadAbortedError,
  downloadFile,
  searchDocuments,
  uploadFiles,
} from "@/lib/api";

/** Minimal XMLHttpRequest stand-in so the upload path can be driven directly. */
class FakeXhr {
  static last: FakeXhr;
  upload = { onprogress: null as ((e: unknown) => void) | null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 200;
  responseText = "[]";
  responseType = "";
  sent = false;

  constructor() {
    FakeXhr.last = this;
  }
  open() {}
  send() {
    this.sent = true;
  }
  abort() {
    this.onabort?.();
  }
  finish(status: number, body: unknown) {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total });
  }
}

beforeEach(() => {
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("uploadFiles", () => {
  const file = () => new File(["x"], "a.pdf", { type: "application/pdf" });

  it("resolves with the uploaded records", async () => {
    const promise = uploadFiles([file()]);
    FakeXhr.last.finish(200, [{ id: "1", name: "a.pdf" }]);
    await expect(promise).resolves.toEqual([{ id: "1", name: "a.pdf" }]);
  });

  it("reports upload progress as a 0..1 fraction", async () => {
    const seen: (number | null)[] = [];
    const promise = uploadFiles([file()], { onProgress: (v) => seen.push(v) });
    FakeXhr.last.progress(50, 200);
    FakeXhr.last.finish(200, []);
    await promise;
    expect(seen[0]).toBeCloseTo(0.25);
    // Completion always reports 1, so a bar cannot be left short.
    expect(seen[seen.length - 1]).toBe(1);
  });

  it("surfaces the server's error detail", async () => {
    const promise = uploadFiles([file()]);
    FakeXhr.last.finish(400, { detail: "Unsupported file type." });
    await expect(promise).rejects.toThrow("Unsupported file type.");
  });

  it("raises AuthRequiredError on 401", async () => {
    const promise = uploadFiles([file()]);
    FakeXhr.last.finish(401, { detail: "nope" });
    await expect(promise).rejects.toBeInstanceOf(AuthRequiredError);
  });

  it("rejects with UploadAbortedError when cancelled mid-flight", async () => {
    const controller = new AbortController();
    const promise = uploadFiles([file()], { signal: controller.signal });
    controller.abort();
    await expect(promise).rejects.toBeInstanceOf(UploadAbortedError);
  });

  it("does not start a request for an already-aborted signal", async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(
      uploadFiles([file()], { signal: controller.signal }),
    ).rejects.toBeInstanceOf(UploadAbortedError);
  });
});

describe("downloadFile", () => {
  it("validates with HEAD, then streams via an anchor rather than a blob", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    await downloadFile("/api/jobs/1/download", "out.md");

    expect(fetchMock).toHaveBeenCalledWith("/api/jobs/1/download", { method: "HEAD" });
    expect(click).toHaveBeenCalledOnce();
    // Buffering the body into memory is exactly what this avoids.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("throws with the server detail and downloads nothing on failure", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 409 })
      .mockResolvedValueOnce({ json: async () => ({ detail: "No result yet." }) });
    vi.stubGlobal("fetch", fetchMock);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    await expect(downloadFile("/api/jobs/1/download", "out.md")).rejects.toThrow(
      "No result yet.",
    );
    expect(click).not.toHaveBeenCalled();
  });
});

describe("searchDocuments", () => {
  it("encodes the query", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);
    await searchDocuments("a & b");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/search?q=a+%26+b");
  });
});
