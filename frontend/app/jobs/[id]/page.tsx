"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CircleDashed,
  Download,
  Eye,
  FileArchive,
  FileClock,
  Loader2,
  Pencil,
  RotateCcw,
  Save,
  Trash2,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { MarkdownEditor } from "@/components/markdown-editor";
import { MarkdownPreview } from "@/components/markdown-preview";
import { formatIcon } from "@/components/upload-dropzone";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { deleteJob, downloadUrl, getJob, getPreview, saveMarkdown, triggerDownload, zipUrl } from "@/lib/api";
import type { Job, JobFileState, Preview } from "@/lib/types";
import { formatBytes } from "@/lib/utils";

const ACTIVE_STATUSES = new Set(["queued", "running"]);

export default function JobWorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const jobId = params.id;

  const [job, setJob] = React.useState<Job | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [activeFileId, setActiveFileId] = React.useState<string | null>(null);
  const [preview, setPreview] = React.useState<Preview | null>(null);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [draft, setDraft] = React.useState<string>("");
  const [dirty, setDirty] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [view, setView] = React.useState<"edit" | "preview">("preview");
  const [deleting, setDeleting] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      const data = await getJob(jobId);
      setJob(data);
      setError(null);
      if (!activeFileId && data.items.length > 0) setActiveFileId(data.items[0].file_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load job");
    }
  }, [jobId, activeFileId]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const active = job?.items.find((i) => i.file_id === activeFileId) ?? null;
  const running = job !== null && ACTIVE_STATUSES.has(job.status);
  const finished = job !== null && !ACTIVE_STATUSES.has(job.status);

  React.useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(id);
  }, [running, refresh]);

  React.useEffect(() => {
    if (!active || active.status !== "completed" || activeFileId === null) return;
    let cancelled = false;
    setPreviewLoading(true);
    void (async () => {
      try {
        const data = await getPreview(jobId, activeFileId);
        if (cancelled) return;
        setPreview(data);
        setDraft(data.content);
        setDirty(false);
        if (data.content.length === 0 && view === "preview") setView("edit");
      } catch (err) {
        if (!cancelled) toast.error(err instanceof Error ? err.message : "Failed to load preview");
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFileId, active?.status]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveMarkdown(jobId, draft, activeFileId ?? undefined);
      setDirty(false);
      setPreview((p) => (p ? { ...p, content: draft } : p));
      toast.success("Markdown saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!preview) return;
    try {
      const data = await getPreview(jobId, activeFileId ?? undefined);
      setDraft(data.content);
      setDirty(false);
      toast.success("Restored extracted content");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to restore");
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteJob(jobId);
      toast.success("Conversion deleted");
      router.push("/");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete");
      setDeleting(false);
    }
  };

  return (
    <div className="min-h-dvh">
      <Header />
      <main className="container pb-16">
        <div className="mb-4 mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </Link>
            <div className="h-4 w-px bg-border" />
            <h1 className="text-sm font-semibold sm:text-base">Conversion workspace</h1>
            {job && (
              <Badge
                variant={
                  job.status === "completed"
                    ? "success"
                    : job.status === "partial"
                      ? "warning"
                      : job.status === "failed"
                        ? "destructive"
                        : "muted"
                }
              >
                {job.status}
              </Badge>
            )}
          </div>
          {finished && job && (
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => triggerDownload(zipUrl(jobId), `markforge-${jobId}.zip`)}>
                <FileArchive className="h-4 w-4" /> Download ZIP
              </Button>
              <Button variant="ghost" size="sm" className="text-destructive" onClick={handleDelete} disabled={deleting}>
                <Trash2 className="h-4 w-4" /> {deleting ? "Deleting…" : "Delete"}
              </Button>
            </div>
          )}
        </div>

        {error && !job && (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
              <XCircle className="h-8 w-8 text-destructive" />
              <p className="text-sm font-medium">{error}</p>
              <Link href="/" className="text-sm text-primary hover:underline">
                Return to dashboard
              </Link>
            </CardContent>
          </Card>
        )}

        {job && (
          <>
            {job.items.length > 1 && (
              <div className="no-scrollbar -mx-4 mb-4 flex gap-2 overflow-x-auto px-4 pb-1" role="tablist" aria-label="Files in this job">
                {job.items.map((item) => {
                  const Icon = formatIcon(item.format);
                  const selected = item.file_id === activeFileId;
                  return (
                    <button
                      key={item.file_id}
                      role="tab"
                      aria-selected={selected}
                      onClick={() => setActiveFileId(item.file_id)}
                      className={cn(
                        "flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
                        selected
                          ? "border-primary/60 bg-primary/5 text-foreground ring-1 ring-primary/30"
                          : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground"
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      <span className="max-w-[160px] truncate">{item.filename}</span>
                      {item.status === "running" && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />}
                      {item.status === "completed" && <CheckCircle2 className="h-3.5 w-3.5 text-success" />}
                      {item.status === "failed" && <XCircle className="h-3.5 w-3.5 text-destructive" />}
                      {item.status === "skipped" && <CircleDashed className="h-3.5 w-3.5 text-muted-foreground" />}
                    </button>
                  );
                })}
              </div>
            )}

            <FileCard
              item={active}
              previewLoading={previewLoading}
              finished={finished}
              onDownload={() => triggerDownload(downloadUrl(jobId, activeFileId ?? undefined))}
            />

            {active?.status === "completed" && (
              <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_340px]">
                <div className="flex min-h-[540px] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
                    <Tabs value={view} onValueChange={(v) => setView(v as "edit" | "preview")}>
                      <TabsList>
                        <TabsTrigger value="edit">
                          <Pencil className="h-3.5 w-3.5" /> Edit
                        </TabsTrigger>
                        <TabsTrigger value="preview">
                          <Eye className="h-3.5 w-3.5" /> Preview
                        </TabsTrigger>
                      </TabsList>
                    </Tabs>
                    <div className="flex items-center gap-2">
                      {dirty && <span className="text-xs text-warning">Unsaved changes</span>}
                      <Button variant="outline" size="sm" onClick={handleReset} disabled={saving || !dirty}>
                        <RotateCcw className="h-3.5 w-3.5" /> Reset
                      </Button>
                      <Button size="sm" onClick={handleSave} disabled={saving || !dirty}>
                        <Save className="h-3.5 w-3.5" /> {saving ? "Saving…" : "Save"}
                      </Button>
                    </div>
                  </div>
                  <div className="flex-1 overflow-hidden">
                    {view === "edit" ? (
                      <MarkdownEditor value={draft} onChange={(value) => { setDraft(value); setDirty(true); }} height="100%" />
                    ) : (
                      <div className="h-full overflow-y-auto">
                        <MarkdownPreview content={draft} />
                      </div>
                    )}
                  </div>
                </div>

                <aside className="lg:sticky lg:top-[4.5rem] lg:self-start">
                  <ResultSidebar
                    preview={preview}
                    loading={previewLoading}
                    onDownload={() => triggerDownload(downloadUrl(jobId, activeFileId ?? undefined), `${active.filename.replace(/\.\w+$/, "")}.md`)}
                  />
                </aside>
              </div>
            )}
          </>
        )}

        {!job && !error && <LoadingState />}
      </main>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}

function FileCard({
  item,
  previewLoading,
  finished,
  onDownload,
}: {
  item: JobFileState | null;
  previewLoading: boolean;
  finished: boolean;
  onDownload: () => void;
}) {
  if (!item) return null;
  const Icon = formatIcon(item.format);

  return (
    <Card>
      <CardContent className="space-y-4 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border bg-background text-muted-foreground">
              <Icon className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{item.filename}</p>
              <p className="text-xs text-muted-foreground">
                {item.format.toUpperCase()} · {item.phase}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {item.status === "running" && (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                {Math.round(item.progress * 100)}%
              </span>
            )}
            {item.status === "completed" && (
              <Button variant="outline" size="sm" onClick={onDownload}>
                <Download className="h-4 w-4" /> .md
              </Button>
            )}
          </div>
        </div>

        {(item.status === "queued" || item.status === "running") && (
          <Progress value={item.progress * 100} className="h-2" />
        )}

        {item.status === "completed" && (
          <div className="flex flex-wrap items-center gap-2">
            {previewLoading ? (
              <Skeleton className="h-5 w-40" />
            ) : (
              <>
                <span className="inline-flex items-center gap-1 text-xs text-success">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Converted
                </span>
                {item.ocr_used && <Badge variant="secondary">OCR applied</Badge>}
                {item.stats && <StatsInline stats={item.stats} />}
              </>
            )}
          </div>
        )}

        {item.status === "failed" && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div>
              <p className="font-medium">{item.error?.message ?? "Conversion failed"}</p>
              {item.error?.detail && <p className="mt-0.5 text-xs text-muted-foreground">{item.error.detail}</p>}
            </div>
          </div>
        )}

        {item.warnings.length > 0 && (
          <div className="space-y-1.5">
            {item.warnings.map((warning, index) => (
              <div key={`${warning.code}-${index}`} className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 p-2.5 text-sm">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                <div>
                  <p className="font-medium">{warning.message}</p>
                  {warning.detail && <p className="mt-0.5 text-xs text-muted-foreground">{warning.detail}</p>}
                </div>
              </div>
            ))}
          </div>
        )}

        {finished && (
          <p className="text-xs text-muted-foreground">
            <FileClock className="mr-1 inline h-3.5 w-3.5" />
            Done
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function StatsInline({ stats }: { stats: Record<string, number> }) {
  const labels: Record<string, string> = {
    pages: "pages",
    slides: "slides",
    sheets: "sheets",
    paragraphs: "paragraphs",
    tables: "tables",
    images: "images",
    headings: "headings",
    links: "links",
    words: "words",
    characters: "characters",
    comments: "comments",
    charts: "charts",
    ocr_pages: "OCR pages",
  };
  const entries = Object.entries(stats).filter(([key, value]) => value > 0 && labels[key]);
  if (entries.length === 0) return null;
  return (
    <span className="text-xs text-muted-foreground">
      {entries.slice(0, 6).map(([key, value], index) => (
        <span key={key}>
          {index > 0 && " · "}
          {value} {labels[key]}
        </span>
      ))}
    </span>
  );
}

function ResultSidebar({
  preview,
  loading,
  onDownload,
}: {
  preview: Preview | null;
  loading: boolean;
  onDownload: () => void;
}) {
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 py-4">
          <h2 className="text-sm font-semibold">Result</h2>
          {loading ? (
            <Skeleton className="h-20 w-full" />
          ) : preview ? (
            <>
              <p className="text-sm text-muted-foreground break-all">{preview.filename}</p>
              <div className="flex flex-wrap items-center gap-1.5">
                {preview.ocr_used && <Badge variant="secondary">OCR applied</Badge>}
                {preview.stats && <StatsInline stats={preview.stats} />}
              </div>
              <p className="text-xs text-muted-foreground">
                {formatBytes(new TextEncoder().encode(preview.content).length)} · edited on save
              </p>
              <Button className="w-full" onClick={onDownload}>
                <Download className="h-4 w-4" /> Download .md
              </Button>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No result available.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="py-4">
          <h2 className="mb-2 text-sm font-semibold">Tip</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Edit the Markdown freely and hit <span className="font-medium text-foreground">Save</span> — the file is
            written back to the job&apos;s output directory. <span className="font-medium text-foreground">Reset</span>{" "}
            restores the original extracted content.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
