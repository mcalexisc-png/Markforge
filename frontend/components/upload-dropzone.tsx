"use client";

import * as React from "react";
import { FilePlus2, FileText, Presentation, Sheet, UploadCloud } from "lucide-react";
import { cn } from "@/lib/utils";
import type { UploadedFile } from "@/lib/types";
import { uploadFiles } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import { toast } from "sonner";

const ACCEPTED = [".pdf", ".docx", ".pptx", ".xlsx"];

const formatMeta: Record<string, { icon: typeof FileText; label: string; color: string }> = {
  pdf: { icon: FileText, label: "PDF", color: "text-red-500/80 dark:text-red-400/80" },
  docx: { icon: FileText, label: "DOCX", color: "text-blue-500/80 dark:text-blue-400/80" },
  pptx: { icon: Presentation, label: "PPTX", color: "text-orange-500/80 dark:text-orange-400/80" },
  xlsx: { icon: Sheet, label: "XLSX", color: "text-green-600/80 dark:text-green-400/80" },
};

export function formatIcon(format: string) {
  return formatMeta[format]?.icon ?? FileText;
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
  const dragCounter = React.useRef(0);

  const handleFiles = async (list: FileList | File[]) => {
    const incoming = Array.from(list);
    if (incoming.length === 0) return;
    setUploading(true);
    try {
      const records = await uploadFiles(incoming);
      onFilesAdded(records);
      const dupes = records.filter((r) => r.duplicate_of);
      if (dupes.length > 0) {
        toast.info(`${dupes.length} duplicate file${dupes.length > 1 ? "s" : ""} skipped`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setUploading(false);
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
          <p className="text-xs text-muted-foreground animate-pulse-soft" role="status">
            Uploading…
          </p>
        )}
      </div>

      {files.length > 0 && (
        <ul className="animate-fade-in divide-y divide-border overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-label="Files ready for conversion">
          {files.map((file) => {
            const meta = formatMeta[file.format];
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
