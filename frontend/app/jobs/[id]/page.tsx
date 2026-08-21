"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
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
import { ConfirmDialog } from "@/components/confirm-dialog";
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
import { confirmDiscardChanges, setUnsavedChanges } from "@/lib/unsaved";
import { deleteJob, downloadFile, downloadUrl, getJob, getPreview, resetMarkdown, saveMarkdown, zipUrl } from "@/lib/api";
import type { Job, JobFileState, Preview } from "@/lib/types";
import { formatBytes } from "@/lib/utils";

const ACTIVE_STATUSES = new Set(["queued", "running"]);

export default function JobWorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const jobId = params.id;
  // Search results deep-link to a specific file within the job.
  const requestedFileId = searchParams.get("file");

  const [job, setJob] = React.useState<Job | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [activeFileId, setActiveFileId] = React.useState<string | null>(null);
  const [preview, setPreview] = React.useState<Preview | null>(null);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [draft, setDraft] = React.useState<string>("");
  const draftRef = React.useRef("");
  const [dirty, setDirty] = React.useState(false);
  // The content as last loaded or saved. Comparing against it keeps "Unsaved
  // changes" (and an enabled Save) from appearing when nothing really changed.
  const savedRef = React.useRef("");
  const [saving, setSaving] = React.useState(false);
  const [view, setView] = React.useState<"edit" | "preview">("preview");
  const [deleting, setDeleting] = React.useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = React.useState(false);
  const [confirmResetOpen, setConfirmResetOpen] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      const data = await getJob(jobId);
      setJob(data);
      setError(null);
      if (!activeFileId && data.items.length > 0) {
        const requested = requestedFileId
          ? data.items.find((i) => i.file_id === requestedFileId)
          : undefined;
        const preferred =
          requested ?? data.items.find((i) => i.status === "completed" || i.status === "running");
        setActiveFileId((preferred ?? data.items[0]).file_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load job");
    }
  }, [jobId, activeFileId, requestedFileId]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const active = job?.items.find((i) => i.file_id === activeFileId) ?? null;
  // Relative `assets/...` paths in the Markdown resolve against this for the
  // rendered preview only; the saved and downloaded file keeps them relative.
  const assetBase = activeFileId ? `/api/jobs/${jobId}/assets/${activeFileId}` : undefined;
  const running = job !== null && ACTIVE_STATUSES.has(job.status);
  const finished = job !== null && !ACTIVE_STATUSES.has(job.status);

  // Held in a ref so the stream below depends only on the job, not on the
  // identity of `refresh` -- which changes whenever a file tab is selected and
  // would otherwise tear down and rebuild the connection on every click.
  const refreshRef = React.useRef(refresh);
  React.useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  // Live progress over Server-Sent Events. One server-side reader replaces a
  // per-second poll from every open tab; polling remains only as a fallback if
  // the stream cannot be established, and backs off instead of hammering.
  React.useEffect(() => {
    if (!running) return;

    let cancelled = false;
    let doneReceived = false;
    let source: EventSource | null = null;
    let pollTimer: number | undefined;

    const startFallbackPolling = () => {
      if (cancelled || doneReceived || pollTimer !== undefined) return;
      let attempts = 0;
      const tick = () => {
        if (cancelled) return;
        attempts += 1;
        void refreshRef.current();
        const delay = Math.min(1000 * 2 ** Math.floor(attempts / 5), 10_000);
        pollTimer = window.setTimeout(tick, delay);
      };
      pollTimer = window.setTimeout(tick, 1000);
    };

    try {
      source = new EventSource(`/api/jobs/${jobId}/events`);
      source.addEventListener("job", (event) => {
        if (cancelled) return;
        try {
          setJob(JSON.parse((event as MessageEvent).data) as Job);
          setError(null);
        } catch {
          /* ignore a malformed frame rather than killing the stream */
        }
      });
      source.addEventListener("done", () => {
        doneReceived = true;
        source?.close();
      });
      source.onerror = () => {
        source?.close();
        source = null;
        // A normal close after `done` is not a failure.
        startFallbackPolling();
      };
    } catch {
      startFallbackPolling();
    }

    return () => {
      cancelled = true;
      source?.close();
      if (pollTimer !== undefined) window.clearTimeout(pollTimer);
    };
  }, [running, jobId]);

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
        draftRef.current = data.content;
        savedRef.current = data.content;
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

  // Publish dirty state so the header nav and Back link can guard on it, and
  // always clear it on unmount so a stale flag cannot block later navigation.
  React.useEffect(() => {
    setUnsavedChanges(dirty);
    return () => setUnsavedChanges(false);
  }, [dirty]);

  React.useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Browsers show their own wording; a non-empty returnValue is what
      // actually triggers the prompt.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const handleSave = async () => {
    setSaving(true);
    const content = draftRef.current;
    try {
      await saveMarkdown(jobId, content, activeFileId ?? undefined);
      savedRef.current = content;
      setDirty(false);
      setPreview((p) => (p ? { ...p, content } : p));
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
      const data = await resetMarkdown(jobId, activeFileId ?? undefined);
      setPreview(data);
      setDraft(data.content);
      draftRef.current = data.content;
      savedRef.current = data.content;
      setDirty(false);
      void refresh();
      toast.success("Restored original extracted content");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to restore");
    }
  };

  const handleDownload = async (url: string, filename: string) => {
    try {
      await downloadFile(url, filename);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Download failed");
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

  const confirmDelete = async () => {
    setConfirmDeleteOpen(false);
    await handleDelete();
  };

  const confirmReset = async () => {
    setConfirmResetOpen(false);
    await handleReset();
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
             onClick={(event) => { if (!confirmDiscardChanges()) event.preventDefault(); }}>
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
              <Button variant="outline" size="sm" onClick={() => void handleDownload(zipUrl(jobId), `markforge-${jobId}.zip`)}>
                <FileArchive className="h-4 w-4" /> Download ZIP
              </Button>
              <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setConfirmDeleteOpen(true)} disabled={deleting}>
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
                      onClick={() => {
                        if (dirty && item.file_id !== activeFileId) {
                          const proceed = window.confirm("You have unsaved changes for the current file. Switch anyway?");
                          if (!proceed) return;
                        }
                        setActiveFileId(item.file_id);
                      }}
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
              onDownload={() => void handleDownload(downloadUrl(jobId, activeFileId ?? undefined), `${active?.filename.replace(/\.\w+$/, "") ?? "document"}.md`)}
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
                      <Button variant="outline" size="sm" onClick={() => setConfirmResetOpen(true)} disabled={saving || !(dirty || active?.edited)}>
                        <RotateCcw className="h-3.5 w-3.5" /> Reset
                      </Button>
                      <Button size="sm" onClick={handleSave} disabled={saving || !dirty}>
                        <Save className="h-3.5 w-3.5" /> {saving ? "Saving…" : "Save"}
                      </Button>
                    </div>
                  </div>
                  <div className="flex-1 overflow-hidden">
                    {view === "edit" ? (
                      <MarkdownEditor
                        value={draft}
                        onChange={(value) => {
                          draftRef.current = value;
                          setDraft(value);
                          setDirty(value !== savedRef.current);
                        }}
                        height="100%"
                      />
                    ) : (
                      <div className="h-full overflow-y-auto">
                        <MarkdownPreview content={draft} assetBase={assetBase} />
                      </div>
                    )}
                  </div>
                </div>

                <aside className="lg:sticky lg:top-[4.5rem] lg:self-start">
                  <ResultSidebar
                    preview={preview}
                    loading={previewLoading}
                    onDownload={() => void handleDownload(downloadUrl(jobId, activeFileId ?? undefined), `${active.filename.replace(/\.\w+$/, "")}.md`)}
                  />
                </aside>
              </div>
            )}
          </>
        )}

        {!job && !error && <LoadingState />}

        <ConfirmDialog
          open={confirmDeleteOpen}
          onOpenChange={setConfirmDeleteOpen}
          title="Delete this conversion?"
          description={`This permanently removes "${job?.items[0]?.filename ?? "this job"}" and all of its outputs from this machine. This cannot be undone.`}
          confirmLabel="Delete"
          busy={deleting}
          onConfirm={() => void confirmDelete()}
        />
        <ConfirmDialog
          open={confirmResetOpen}
          onOpenChange={setConfirmResetOpen}
          title="Reset to original?"
          description={`Any edits to "${active?.filename ?? "this file"}" will be discarded and replaced with the original extracted content.`}
          confirmLabel="Reset"
          destructive={false}
          onConfirm={() => void confirmReset()}
        />
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
