export type OutputMode = "fidelity" | "clean";
export type OcrMode = "auto" | "always" | "never";
export type JobStatus = "queued" | "running" | "completed" | "partial" | "failed";

export interface UploadedFile {
  id: string;
  name: string;
  size: number;
  format: string;
  sha256: string;
  duplicate_of?: string | null;
}

export interface FileReference {
  id: string;
  name: string;
  size: number;
  format: string;
}

export interface JobWarning {
  code: string;
  message: string;
  detail?: string | null;
  severity?: "info" | "warning";
}

export interface JobFileState {
  file_id: string;
  filename: string;
  format: string;
  status: "queued" | "running" | "completed" | "failed" | "skipped";
  progress: number;
  phase: string;
  message: string;
  warnings: JobWarning[];
  stats: Record<string, number>;
  output_dir: string | null;
  markdown_filename: string | null;
  ocr_used: boolean;
  error: { code: string; message: string; detail?: string | null } | null;
}

export interface Job {
  id: string;
  status: JobStatus;
  progress: number;
  phase: string;
  files: FileReference[];
  items: JobFileState[];
  settings: Record<string, unknown>;
  error: { code: string; message: string } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Preview {
  job_id: string;
  filename: string;
  content: string;
  stats: Record<string, number>;
  warnings: JobWarning[];
  ocr_used: boolean;
}

export interface HistoryItem {
  id: string;
  filename: string;
  format: string;
  status: JobStatus;
  created_at: string;
  finished_at: string | null;
  output_size: number;
  warning_count: number;
  stats: Record<string, number>;
}

export interface UserSettings {
  output_mode: OutputMode;
  ocr_mode: OcrMode;
  preserve_boundaries: boolean;
  extract_images: boolean;
  convert_tables: boolean;
  preserve_links: boolean;
}

export interface HealthInfo {
  status: string;
  version: string;
  redis: string;
  worker: string;
  storage: string;
  lan: { enabled: boolean; auth_required: boolean };
}
