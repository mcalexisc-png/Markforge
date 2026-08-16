import type { HealthInfo, HistoryItem, Job, Preview, UploadedFile, UserSettings } from "@/lib/types";

const JSON_HEADERS = { "Content-Type": "application/json" };

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent("markforge:unauthorized"));
    throw new Error("Authorization required");
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
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || "Failed to save");
  }
}

export async function getHistory(): Promise<HistoryItem[]> {
  return parse<HistoryItem[]>(await fetch("/api/jobs/history"));
}

export async function deleteJob(id: string): Promise<void> {
  const response = await fetch(`/api/jobs/${id}`, { method: "DELETE" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || "Failed to delete");
  }
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

export function triggerDownload(url: string, filename?: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  if (filename) anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
