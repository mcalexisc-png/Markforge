"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, AlertCircle, FileClock, Lock, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { UploadDropzone } from "@/components/upload-dropzone";
import { SettingsPanel } from "@/components/settings-panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createJob, getSettings, saveSettings, verifyLanPassword, AuthRequiredError } from "@/lib/api";
import type { UploadedFile, UserSettings } from "@/lib/types";
import { formatBytes, formatDate } from "@/lib/utils";
import { useHistory } from "@/hooks/use-history";
import { usePolling } from "@/hooks/use-polling";

const DEFAULT_SETTINGS: UserSettings = {
  output_mode: "fidelity",
  ocr_mode: "auto",
  preserve_boundaries: true,
  convert_tables: true,
  preserve_links: true,
  extract_images: true,
};

export default function DashboardPage() {
  const router = useRouter();
  const [files, setFiles] = React.useState<UploadedFile[]>([]);
  const [settings, setSettings] = React.useState<UserSettings>(DEFAULT_SETTINGS);
  const [converting, setConverting] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [locked, setLocked] = React.useState(false);
  const [password, setPassword] = React.useState("");
  const [authError, setAuthError] = React.useState("");
  const { history, loading: historyLoading, error: historyError, refresh } = useHistory(4);

  const readyFiles = files.filter((f) => !f.duplicate_of);

  // Refresh the recent list while anything is still converting. The condition
  // was inverted: `history.length === 0` stopped refreshing as soon as a job
  // existed, which is exactly when there is something to watch.
  const historyPending = history.some(
    (item) => item.status === "queued" || item.status === "running",
  );
  usePolling(refresh, 5_000, { enabled: historyPending && !historyError });

  React.useEffect(() => {
    void (async () => {
      try {
        if (window.location.search.includes("locked=1")) {
          setLocked(true);
          return;
        }
        const stored = await getSettings();
        setSettings(stored);
      } catch (error) {
        if (error instanceof AuthRequiredError) {
          setLocked(true);
        } else {
          toast.error(error instanceof Error ? error.message : "Could not reach the conversion service.");
        }
      }
    })();
  }, []);

  const handleVerify = async () => {
    setAuthError("");
    try {
      await verifyLanPassword(password);
      setLocked(false);
      setPassword("");
      const stored = await getSettings();
      setSettings(stored);
      toast.success("Access granted");
    } catch (error) {
      if (error instanceof AuthRequiredError) {
        setAuthError("Incorrect password. Try again.");
      } else if (error instanceof Error && error.message.includes("Too many attempts")) {
        setAuthError("Too many attempts. Please wait a minute and try again.");
      } else {
        setAuthError("Could not reach the service. Check your connection and try again.");
      }
    }
  };

  const handleConvert = async () => {
    if (readyFiles.length === 0) {
      toast.error("Add at least one file first.");
      return;
    }
    setConverting(true);
    try {
      const job = await createJob(readyFiles.map((f) => f.id), settings);
      router.push(`/jobs/${job.id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to start conversion");
    } finally {
      setConverting(false);
    }
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      await saveSettings(settings);
      toast.success("Default settings saved");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-dvh">
      <Header />

      <main className="container pb-20">
        <section className="flex flex-col items-center gap-3 py-10 text-center sm:py-14">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="gap-1.5">
              <ShieldCheck className="h-3 w-3" />
              Local-first
            </Badge>
            <Badge variant="secondary" className="gap-1.5">
              <Sparkles className="h-3 w-3" />
              No cloud required
            </Badge>
          </div>
          <h1 className="max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
            Convert documents into clean, structured Markdown
          </h1>
          <p className="max-w-xl text-balance text-muted-foreground">
            PDF, Office, EPUB and text formats — converted locally on your machine. Private, deterministic, and yours.
          </p>
        </section>

        <div className="mx-auto grid max-w-5xl gap-5 lg:grid-cols-[1fr_340px]">
          <section aria-label="Upload documents">
            <UploadDropzone
              files={files}
              onFilesAdded={(added) => setFiles((prev) => [...prev, ...added])}
              onRemove={(id) => setFiles((prev) => prev.filter((f) => f.id !== id))}
              onClear={() => setFiles([])}
            />

            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-muted-foreground">
                {files.length === 0
                  ? "Upload one or more documents to begin."
                  : `${readyFiles.length} file${readyFiles.length > 1 ? "s" : ""} ready · ${formatBytes(files.reduce((sum, f) => sum + f.size, 0))}`}
              </p>
              <Button
                size="lg"
                disabled={readyFiles.length === 0 || converting}
                onClick={handleConvert}
                className="w-full sm:w-auto"
              >
                {converting ? "Starting…" : readyFiles.length > 1 ? `Convert all (${readyFiles.length})` : "Convert to Markdown"}
                {!converting && <ArrowRight className="h-4 w-4" />}
              </Button>
            </div>
          </section>

          <aside className="lg:sticky lg:top-[4.5rem] lg:self-start">
            <SettingsPanel
              settings={settings}
              onChange={setSettings}
              onSave={handleSaveSettings}
              saving={saving}
            />
          </aside>
        </div>

        <section className="mx-auto mt-12 max-w-5xl" aria-label="Recent conversions">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Recent conversions</h2>
            <Link href="/jobs" className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>

          {historyLoading && history.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
                {[0, 1].map((i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </CardContent>
            </Card>
          ) : historyError ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
                <AlertCircle className="h-8 w-8 text-destructive" />
                <p className="text-sm font-medium">Couldn&apos;t load your conversions</p>
                <p className="max-w-sm text-sm text-muted-foreground">{historyError}</p>
                <Button variant="outline" size="sm" onClick={() => void refresh()}>
                  Retry
                </Button>
              </CardContent>
            </Card>
          ) : history.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
                <FileClock className="h-8 w-8 text-muted-foreground/60" />
                <p className="text-sm font-medium">No conversions yet</p>
                <p className="max-w-sm text-sm text-muted-foreground">
                  Upload your first document to create Markdown.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card shadow-sm">
              {history.map((item) => (
                <Link
                  key={item.id}
                  href={`/jobs/${item.id}`}
                  className="flex items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-accent/50"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{item.filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {item.format.toUpperCase()} · {formatDate(item.created_at)}
                    </p>
                  </div>
                  <Badge
                    variant={
                      item.status === "completed"
                        ? "success"
                        : item.status === "partial"
                          ? "warning"
                          : item.status === "failed"
                            ? "destructive"
                            : "muted"
                    }
                  >
                    {item.status}
                  </Badge>
                </Link>
              ))}
            </div>
          )}
        </section>
      </main>

      <Dialog open={locked} onOpenChange={() => {}}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Lock className="h-4 w-4 text-primary" />
              Markforge is password-protected
            </DialogTitle>
            <DialogDescription>
              This instance is exposed on your local network. Enter the access password set by the administrator.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void handleVerify();
            }}
            className="mt-2 space-y-3"
          >
            <Label htmlFor="lan-password">Access password</Label>
            <Input
              id="lan-password"
              type="password"
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
            />
            {authError && <p className="text-sm text-destructive">{authError}</p>}
            <Button type="submit" className="w-full" disabled={!password}>
              Unlock
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
