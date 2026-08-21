"use client";

import * as React from "react";
import {
  BookOpen,
  File,
  FileCode,
  FileJson,
  FilePlus2,
  FileText,
  Globe,
  Mail,
  NotebookText,
  Presentation,
  Sheet,
  UploadCloud,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { UploadedFile } from "@/lib/types";
import { UploadAbortedError, uploadFiles } from "@/lib/api";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/utils";
import { toast } from "sonner";

// Mirrors ALLOWED_EXTENSIONS in backend/converters/__init__.py. Local-only
// formats only -- audio and standalone images are deliberately excluded because
// MarkItDown converts them through network services.
const ACCEPTED = [
  ".pdf",
  ".docx",
  ".pptx",
  ".xlsx",
  ".csv",
  ".tsv",
  ".html",
  ".htm",
  ".txt",
  ".md",
  ".json",
  ".xml",
  ".epub",
  ".msg",
  ".ipynb",
];

const MAX_FILE_MB = 100;
const MAX_FILES = 25;

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

type FormatMeta = { icon: typeof FileText; label: string; color: string };

/** Shown for any format without an entry below, so an unknown format from the
 *  backend degrades to a generic row instead of crashing the list. */
const DEFAULT_FORMAT_META: FormatMeta = {
  icon: File,
  label: "FILE",
  color: "text-muted-foreground",
};

const formatMeta: Record<string, FormatMeta> = {
  pdf: { icon: FileText, label: "PDF", color: "text-red-500/80 dark:text-red-400/80" },
  docx: { icon: FileText, label: "DOCX", color: "text-blue-500/80 dark:text-blue-400/80" },
  pptx: { icon: Presentation, label: "PPTX", color: "text-orange-500/80 dark:text-orange-400/80" },
  xlsx: { icon: Sheet, label: "XLSX", color: "text-green-600/80 dark:text-green-400/80" },
  csv: { icon: Sheet, label: "CSV", color: "text-emerald-600/80 dark:text-emerald-400/80" },
  tsv: { icon: Sheet, label: "TSV", color: "text-emerald-600/80 dark:text-emerald-400/80" },
  html: { icon: Globe, label: "HTML", color: "text-sky-500/80 dark:text-sky-400/80" },
  htm: { icon: Globe, label: "HTML", color: "text-sky-500/80 dark:text-sky-400/80" },
  txt: { icon: FileText, label: "TXT", color: "text-slate-500/80 dark:text-slate-400/80" },
  md: { icon: FileText, label: "MD", color: "text-slate-500/80 dark:text-slate-400/80" },
  json: { icon: FileJson, label: "JSON", color: "text-amber-500/80 dark:text-amber-400/80" },
  xml: { icon: FileCode, label: "XML", color: "text-violet-500/80 dark:text-violet-400/80" },
  epub: { icon: BookOpen, label: "EPUB", color: "text-purple-500/80 dark:text-purple-400/80" },
  msg: { icon: Mail, label: "MSG", color: "text-cyan-600/80 dark:text-cyan-400/80" },
  ipynb: { icon: NotebookText, label: "IPYNB", color: "text-rose-500/80 dark:text-rose-400/80" },
};

function metaFor(format: string): FormatMeta {
  return formatMeta[format] ?? DEFAULT_FORMAT_META;
}

export function formatIcon(format: string) {
  return metaFor(format).icon;
}

interface DropzoneProps {
  files: UploadedFile[];
  onFilesAdded: (files: UploadedFile[]) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}

export function UploadDropzone({ files, onFilesAdded, onRemove, onClear }: DropzoneProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [progress, setProgress] = React.useState<number | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const dragCounter = React.useRef(0);

  // Deliberately no abort-on-unmount. React's dev StrictMode mounts, unmounts
  // and remounts, so an unmount cleanup cancels any upload that started during
  // that window -- exactly what a fast drop-then-interact does. An upload that
  // outlives the component is harmless (the file lands server-side and
  // unreferenced uploads are pruned), so cancelling stays an explicit act via
  // the Cancel button.

  const handleFiles = async (list: FileList | File[]) => {
    const incoming = Array.from(list);
    if (incoming.length === 0) return;

    const badType = incoming.filter((f) => !ACCEPTED.includes(extensionOf(f.name)));
    const oversized = incoming.filter((f) => f.size > MAX_FILE_MB * 1024 * 1024);
    let valid = incoming.filter((f) => ACCEPTED.includes(extensionOf(f.name)) && f.size <= MAX_FILE_MB * 1024 * 1024);

    const remaining = Math.max(0, MAX_FILES - files.length);
    if (valid.length > remaining) {
      toast.error(`You can convert at most ${MAX_FILES} files per job.`);
      valid = valid.slice(0, remaining);
    }
    if (badType.length > 0) {
      toast.error(
        `${badType.length} file${badType.length > 1 ? "s" : ""} skipped — ${ACCEPTED.map((e) => e.slice(1)).join(", ")} are supported.`,
      );
    }
    if (oversized.length > 0) {
      toast.error(`${oversized.length} file${oversized.length > 1 ? "s" : ""} skipped — files must be ${MAX_FILE_MB} MB or smaller.`);
    }
    if (valid.length === 0) return;

    const controller = new AbortController();
    abortRef.current = controller;
    setUploading(true);
    setProgress(0);
    try {
      const records = await uploadFiles(valid, {
        onProgress: setProgress,
        signal: controller.signal,
      });
      onFilesAdded(records);
      const dupes = records.filter((r) => r.duplicate_of);
      if (dupes.length > 0) {
        toast.info(`${dupes.length} duplicate file${dupes.length > 1 ? "s" : ""} skipped`);
      }
    } catch (error) {
      // Cancelling is a deliberate act, not an error to apologise for.
      if (error instanceof UploadAbortedError) {
        toast.info("Upload cancelled");
      } else {
        toast.error(error instanceof Error ? error.message : "Upload failed");
      }
    } finally {
      abortRef.current = null;
      setUploading(false);
      setProgress(null);
    }
  };

  const dropHandlers = {
    onDragEnter: (event: React.DragEvent) => {
      event.preventDefault();
      dragCounter.current += 1;
      setDragging(true);
    },
    onDragOver: (event: React.DragEvent) => event.preventDefault(),
    onDragLeave: (event: React.DragEvent) => {
      event.preventDefault();
      dragCounter.current -= 1;
      if (dragCounter.current <= 0) setDragging(false);
    },
    onDrop: (event: React.DragEvent) => {
      event.preventDefault();
      dragCounter.current = 0;
      setDragging(false);
      void handleFiles(event.dataTransfer.files);
    },
  };

  return (
    <div className="space-y-3">
      <div
        {...dropHandlers}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}
        aria-label="Upload documents: drag and drop, or press Enter to browse"
        className={cn(
          "group relative flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-all duration-200 sm:py-12",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          dragging
            ? "border-primary bg-primary/5 scale-[1.01]"
            : "border-border bg-card/50 hover:border-primary/50 hover:bg-accent/40"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED.join(",")}
          className="sr-only"
          onChange={(event) => {
            void handleFiles(event.target.files ?? []);
            event.target.value = "";
          }}
        />
        <div
          className={cn(
            "flex h-12 w-12 items-center justify-center rounded-xl border bg-background shadow-sm transition-transform duration-200",
            dragging ? "scale-110 border-primary text-primary" : "text-muted-foreground group-hover:text-primary"
          )}
        >
          <UploadCloud className="h-6 w-6" />
        </div>
        <div>
          <p className="text-sm font-semibold">
            {dragging ? "Release to add files" : "Drop files here"}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            or <span className="font-medium text-primary underline-offset-2 group-hover:underline">browse your device</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-1.5">
          {["PDF", "DOCX", "PPTX", "XLSX"].map((label) => (
            <span
              key={label}
              className="rounded-md border border-border bg-background/70 px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
            >
              {label}
            </span>
          ))}
        </div>
        {uploading && (
          <div className="w-full max-w-sm space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground" role="status" aria-live="polite">
                {progress === null
                  ? "Uploading…"
                  : `Uploading… ${Math.round(progress * 100)}%`}
              </p>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={(event) => {
                  event.stopPropagation();
                  abortRef.current?.abort();
                }}
              >
                Cancel
              </Button>
            </div>
            <Progress value={(progress ?? 0) * 100} />
          </div>
        )}
      </div>

      {files.length > 0 && (
        <ul className="animate-fade-in divide-y divide-border overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-label="Files ready for conversion">
          {files.map((file) => {
            const meta = metaFor(file.format);
            const Icon = meta.icon;
            return (
              <li key={file.id} className="flex items-center gap-3 px-4 py-3">
                <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border bg-background", meta.color)}>
                  <Icon className="h-4.5 w-4.5 h-[18px] w-[18px]" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {meta.label} · {formatBytes(file.size)}
                    {file.duplicate_of && <span className="ml-1.5 text-warning">duplicate</span>}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onRemove(file.id)}
                  aria-label={`Remove ${file.name}`}
                  className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <FilePlus2 className="h-4 w-4 rotate-45" />
                </button>
              </li>
            );
          })}
          <li className="flex justify-end px-4 py-2">
            <button
              type="button"
              onClick={onClear}
              className="text-xs font-medium text-muted-foreground transition-colors hover:text-destructive"
            >
              Clear all
            </button>
          </li>
        </ul>
      )}
    </div>
  );
}
