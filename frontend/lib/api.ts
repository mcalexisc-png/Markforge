import type { HealthInfo, HistoryItem, Job, Preview, UploadedFile, UserSettings } from "@/lib/types";

const JSON_HEADERS = { "Content-Type": "application/json" };

export class AuthRequiredError extends Error {
  constructor() {
    super("Authorization required");
    this.name = "AuthRequiredError";
  }
}

async function parse<T>(response: Response): Promise<T> {
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

export async function uploadFiles(files: File[]): Promise<UploadedFile[]> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const response = await fetch("/api/files/upload", { method: "POST", body: form });
  return parse<UploadedFile[]>(response);
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

export async function downloadFile(url: string, filename: string): Promise<void> {
  const response = await fetch(url);
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent("markforge:unauthorized"));
    throw new AuthRequiredError();
  }
  if (!response.ok) {
    let detail = `Download failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep generic message */
    }
    throw new Error(detail);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
