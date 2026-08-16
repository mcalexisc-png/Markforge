"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, FileArchive, FileClock, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { formatIcon } from "@/components/upload-dropzone";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { deleteJob, getHistory, triggerDownload, zipUrl } from "@/lib/api";
import type { HistoryItem } from "@/lib/types";
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

  const refresh = React.useCallback(async () => {
    try {
      const data = await getHistory();
      setItems(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleDelete = async (id: string, filename: string) => {
    try {
      await deleteJob(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
      toast.success(`Deleted "${filename}"`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete");
    }
  };

  return (
    <div className="min-h-dvh">
      <Header />
      <main className="container max-w-4xl pb-20">
        <div className="mt-8 mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">Conversion history</h1>
          <p className="mt-1 text-sm text-muted-foreground">Every job is stored locally on this machine.</p>
        </div>

        {loading ? (
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
                        onClick={() => triggerDownload(zipUrl(item.id), `markforge-${item.id}.zip`)}
                      >
                        <FileArchive className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Delete ${item.filename}`}
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => handleDelete(item.id, item.filename)}
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
      </main>
    </div>
  );
}
