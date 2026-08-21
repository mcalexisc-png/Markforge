import type { HealthInfo, HistoryItem, Job, Preview, SearchHit, UploadedFile, UserSettings } from "@/lib/types";

const JSON_HEADERS = { "Content-Type": "application/json" };

export class AuthRequiredError extends Error {
  constructor() {
    super("Authorization required");
    this.name = "AuthRequiredError";
  }
}

/** Signals the LAN gate to re-prompt. Shared by the fetch and XHR paths. */
function notifyUnauthorized() {
  window.dispatchEvent(new CustomEvent("markforge:unauthorized"));
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    notifyUnauthorized();
    throw new AuthRequiredError();
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep generic message */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

async function parseVoid(response: Response): Promise<void> {
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent("markforge:unauthorized"));
    throw new AuthRequiredError();
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep generic message */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return;
  await response.body?.cancel();
}

export class UploadAbortedError extends Error {
  constructor() {
    super("Upload cancelled");
    this.name = "UploadAbortedError";
  }
}

/**
 * Upload via XMLHttpRequest rather than fetch: `fetch` exposes no upload
 * progress, so a large batch showed a static "Uploading…" for minutes with no
 * way to stop it. `onProgress` receives 0..1, or null while the total size is
 * still unknown.
 */
export function uploadFiles(
  files: File[],
  options: { onProgress?: (fraction: number | null) => void; signal?: AbortSignal } = {},
): Promise<UploadedFile[]> {
  const { onProgress, signal } = options;

  return new Promise<UploadedFile[]>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new UploadAbortedError());
      return;
    }

    const form = new FormData();
    for (const file of files) form.append("files", file);

    const request = new XMLHttpRequest();
    request.open("POST", "/api/files/upload");
    request.responseType = "text";

    const onAbort = () => request.abort();
    signal?.addEventListener("abort", onAbort);
    const cleanup = () => signal?.removeEventListener("abort", onAbort);

    request.upload.onprogress = (event) => {
      if (!onProgress) return;
      onProgress(event.lengthComputable ? event.loaded / event.total : null);
    };

    request.onload = () => {
      cleanup();
      let body: unknown = null;
      try {
        body = JSON.parse(request.responseText);
      } catch {
        /* handled below */
      }
      if (request.status === 401) {
        notifyUnauthorized();
        reject(new AuthRequiredError());
        return;
      }
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(1);
        resolve((body ?? []) as UploadedFile[]);
        return;
      }
      const detail =
        body && typeof body === "object" && typeof (body as { detail?: unknown }).detail === "string"
          ? (body as { detail: string }).detail
          : `Upload failed (${request.status})`;
      reject(new Error(detail));
    };

    request.onerror = () => {
      cleanup();
      reject(new Error("Upload failed — is the backend running?"));
    };
    request.onabort = () => {
      cleanup();
      reject(new UploadAbortedError());
    };

    request.send(form);
  });
}

export async function createJob(fileIds: string[], settings: Partial<UserSettings>): Promise<Job> {
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ file_ids: fileIds, settings }),
  });
  return parse<Job>(response);
}

export async function getJob(id: string): Promise<Job> {
  return parse<Job>(await fetch(`/api/jobs/${id}`));
}

export async function getPreview(id: string, fileId?: string): Promise<Preview> {
  const suffix = fileId ? `?file_id=${fileId}` : "";
  return parse<Preview>(await fetch(`/api/jobs/${id}/preview${suffix}`));
}

export async function saveMarkdown(id: string, content: string, fileId?: string): Promise<void> {
  const response = await fetch(`/api/jobs/${id}/markdown`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ content, file_id: fileId }),
  });
  await parseVoid(response);
}

export async function resetMarkdown(id: string, fileId?: string): Promise<Preview> {
  const suffix = fileId ? `?file_id=${fileId}` : "";
  return parse<Preview>(await fetch(`/api/jobs/${id}/reset${suffix}`, { method: "POST" }));
}

export async function getHistory(): Promise<HistoryItem[]> {
  return parse<HistoryItem[]>(await fetch("/api/jobs/history"));
}

export async function searchDocuments(
  query: string,
  signal?: AbortSignal,
): Promise<SearchHit[]> {
  const params = new URLSearchParams({ q: query });
  return parse<SearchHit[]>(await fetch(`/api/search?${params}`, { signal }));
}

export async function deleteJob(id: string): Promise<void> {
  const response = await fetch(`/api/jobs/${id}`, { method: "DELETE" });
  await parseVoid(response);
}

export async function getSettings(): Promise<UserSettings> {
  return parse<UserSettings>(await fetch("/api/settings"));
}

export async function saveSettings(settings: UserSettings): Promise<UserSettings> {
  const response = await fetch("/api/settings", {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(settings),
  });
  return parse<UserSettings>(response);
}

export async function getHealth(): Promise<HealthInfo> {
  return parse<HealthInfo>(await fetch("/api/health"));
}

export async function verifyLanPassword(password: string): Promise<{ ok: boolean }> {
  const response = await fetch("/api/auth/verify", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ password }),
  });
  return parse<{ ok: boolean }>(response);
}

export function downloadUrl(jobId: string, fileId?: string): string {
  return fileId ? `/api/jobs/${jobId}/download?file_id=${fileId}` : `/api/jobs/${jobId}/download`;
}

export function zipUrl(jobId: string): string {
  return `/api/jobs/${jobId}/zip`;
}

/**
 * Trigger a download without buffering the file in memory.
 *
 * The previous implementation fetched the whole response into a Blob before
 * saving it, so a large ZIP was held in the tab's memory in full. Instead the
 * request is validated with a cheap HEAD (so a 401/404/409 surfaces as a real
 * error rather than a downloaded error page), then a same-origin anchor lets
 * the browser stream the body straight to disk. Cookies ride along and the
 * filename comes from the server's Content-Disposition.
 */
export async function downloadFile(url: string, filename: string): Promise<void> {
  const probe = await fetch(url, { method: "HEAD" });
  if (probe.status === 401) {
    notifyUnauthorized();
    throw new AuthRequiredError();
  }
  if (!probe.ok) {
    // HEAD carries no body, so fall back to GET only to read the error detail.
    let detail = `Download failed (${probe.status})`;
    try {
      const body = await (await fetch(url)).json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep generic message */
    }
    throw new Error(detail);
  }

  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
