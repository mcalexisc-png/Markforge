"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, FileArchive, FileClock, Search, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Header } from "@/components/header";
import { formatIcon } from "@/components/upload-dropzone";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { deleteJob, downloadFile, getHistory, searchDocuments, zipUrl } from "@/lib/api";
import type { HistoryItem, SearchHit } from "@/lib/types";
import { cn, formatBytes, formatDate } from "@/lib/utils";

const statusVariant = (status: HistoryItem["status"]) =>
  status === "completed"
    ? "success"
    : status === "partial"
      ? "warning"
      : status === "failed"
        ? "destructive"
        : "muted";

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = React.useState<HistoryItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [deleting, setDeleting] = React.useState(false);
  const [pendingDelete, setPendingDelete] = React.useState<{ id: string; filename: string } | null>(null);
  const [query, setQuery] = React.useState("");
  const [hits, setHits] = React.useState<SearchHit[] | null>(null);
  const [searching, setSearching] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await getHistory();
      setItems(data);
      setLoadError(null);
    } catch (error) {
      // An error state, not an empty state: "Nothing here yet" would read as
      // "you have no conversions" when the backend is simply unreachable.
      setLoadError(error instanceof Error ? error.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced so typing does not fire a request per keystroke.
  React.useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setHits(null);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchDocuments(trimmed, controller.signal)
        .then(setHits)
        .catch((error) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          toast.error(error instanceof Error ? error.message : "Search failed");
          setHits([]);
        })
        .finally(() => setSearching(false));
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleDelete = async (id: string, filename: string) => {
    setDeleting(true);
    try {
      await deleteJob(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
      toast.success(`Deleted "${filename}"`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete");
    } finally {
      setDeleting(false);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const { id, filename } = pendingDelete;
    setPendingDelete(null);
    await handleDelete(id, filename);
  };

  return (
    <div className="min-h-dvh">
      <Header />
      <main className="container max-w-4xl pb-20">
        <div className="mt-8 mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">Conversion history</h1>
          <p className="mt-1 text-sm text-muted-foreground">Every job is stored locally on this machine.</p>
        </div>

        <div className="relative mb-6">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search inside every converted document…"
            aria-label="Search converted documents"
            className="pl-9 pr-9"
          />
          {query && (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Clear search"
              className="absolute right-1.5 top-1/2 -translate-y-1/2"
              onClick={() => setQuery("")}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>

        {loadError ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
              <AlertCircle className="h-10 w-10 text-destructive/70" />
              <p className="text-sm font-medium">Could not load your history</p>
              <p className="max-w-sm text-sm text-muted-foreground">{loadError}</p>
              <Button className="mt-2" onClick={() => void refresh()}>
                Try again
              </Button>
            </CardContent>
          </Card>
        ) : hits !== null ? (
          <SearchResults hits={hits} searching={searching} query={query} />
        ) : loading ? (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-16 w-full rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
              <FileClock className="h-10 w-10 text-muted-foreground/60" />
              <p className="text-sm font-medium">Nothing here yet</p>
              <p className="max-w-sm text-sm text-muted-foreground">
                When you convert documents they will show up in this list.
              </p>
              <Link href="/" className={cn(buttonVariants(), "mt-2")}>
                Convert a document <ArrowRight className="h-4 w-4" />
              </Link>
            </CardContent>
          </Card>
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card shadow-sm">
            {items.map((item) => {
              const Icon = formatIcon(item.format.split(",")[0]);
              return (
                <li key={item.id} className="group flex items-center gap-3 px-4 py-3.5">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border bg-background text-muted-foreground">
                    <Icon className="h-5 w-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <Link href={`/jobs/${item.id}`} className="block truncate text-sm font-medium hover:text-primary">
                      {item.filename}
                    </Link>
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                      <span>{item.format.toUpperCase().replace(",", ", ")}</span>
                      <span aria-hidden>·</span>
                      <span>{formatDate(item.created_at)}</span>
                      {item.output_size > 0 && (
                        <>
                          <span aria-hidden>·</span>
                          <span>{formatBytes(item.output_size)} output</span>
                        </>
                      )}
                      {item.warning_count > 0 && (
                        <>
                          <span aria-hidden>·</span>
                          <span className="text-warning">{item.warning_count} warning{item.warning_count > 1 ? "s" : ""}</span>
                        </>
                      )}
                    </p>
                  </div>
                  <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                  <div className="flex items-center gap-1">
                    {item.status === "completed" && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Download ZIP for ${item.filename}`}
                        onClick={() => {
                        void downloadFile(zipUrl(item.id), `markforge-${item.id}.zip`).catch((error) =>
                          toast.error(error instanceof Error ? error.message : "Download failed"),
                        );
                      }}
                      >
                        <FileArchive className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Delete ${item.filename}`}
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => setPendingDelete({ id: item.id, filename: item.filename })}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="max-sm:hidden"
                    onClick={() => router.push(`/jobs/${item.id}`)}
                  >
                    Open <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}

        <ConfirmDialog
          open={pendingDelete !== null}
          onOpenChange={(open) => {
            if (!open && !deleting) setPendingDelete(null);
          }}
          title="Delete this conversion?"
          description={`This permanently removes "${pendingDelete?.filename ?? "this conversion"}" and all of its outputs from this machine. This cannot be undone.`}
          confirmLabel="Delete"
          busy={deleting}
          onConfirm={() => void confirmDelete()}
        />
      </main>
    </div>
  );
}


/** FTS5 wraps each match in square brackets; render those runs as <mark>. */
function Snippet({ text }: { text: string }) {
  const parts = text.split(/(\[[^\]]*\])/g);
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith("[") && part.endsWith("]") ? (
          <mark key={index} className="rounded bg-primary/20 px-0.5 text-foreground">
            {part.slice(1, -1)}
          </mark>
        ) : (
          <React.Fragment key={index}>{part}</React.Fragment>
        ),
      )}
    </>
  );
}

function SearchResults({
  hits,
  searching,
  query,
}: {
  hits: SearchHit[];
  searching: boolean;
  query: string;
}) {
  if (searching && hits.length === 0) {
    return (
      <div className="space-y-3">
        {[0, 1].map((i) => (
          <Skeleton key={i} className="h-16 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (hits.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
          <Search className="h-10 w-10 text-muted-foreground/60" />
          <p className="text-sm font-medium">No matches for “{query.trim()}”</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Search covers the Markdown of every completed conversion.
          </p>
        </CardContent>
      </Card>
    );
  }
  return (
    <>
      <p className="mb-3 text-xs text-muted-foreground">
        {hits.length} match{hits.length > 1 ? "es" : ""} for “{query.trim()}”
      </p>
      <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        {hits.map((hit) => (
          <li key={`${hit.job_id}-${hit.file_id}`}>
            <Link
              href={`/jobs/${hit.job_id}?file=${encodeURIComponent(hit.file_id)}`}
              className="block px-4 py-3.5 transition-colors hover:bg-muted/50"
            >
              <p className="truncate text-sm font-medium">{hit.filename}</p>
              <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                <Snippet text={hit.snippet} />
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
