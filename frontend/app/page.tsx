"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, FileClock, Lock, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { UploadDropzone } from "@/components/upload-dropzone";
import { SettingsPanel } from "@/components/settings-panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogClose } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createJob, getHealth, getSettings, saveSettings, verifyLanPassword } from "@/lib/api";
import type { UploadedFile, UserSettings } from "@/lib/types";
import { formatBytes, formatDate } from "@/lib/utils";
import { useHistory } from "@/hooks/use-history";
import { usePolling } from "@/hooks/use-polling";

const DEFAULT_SETTINGS: UserSettings = {
  output_mode: "fidelity",
  ocr_mode: "auto",
  preserve_boundaries: true,
  extract_images: true,
  convert_tables: true,
  preserve_links: true,
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
  const [authChecking, setAuthChecking] = React.useState(true);
  const { history, refresh } = useHistory(4);

  usePolling(refresh, 10_000, { enabled: history.length === 0 });

  React.useEffect(() => {
    void (async () => {
      try {
        const health = await getHealth();
        if (health.lan.auth_required) {
          setLocked(true);
        } else {
          const stored = await getSettings();
          setSettings(stored);
        }
      } catch {
        setLocked(true);
      } finally {
        setAuthChecking(false);
      }
    })();
  }, []);

  const handleVerify = async () => {
    setAuthError("");
    try {
      await verifyLanPassword(password);
      setLocked(false);
      const stored = await getSettings();
      setSettings(stored);
      toast.success("Access granted");
    } catch {
      setAuthError("Incorrect password. Try again.");
    }
  };

  const handleConvert = async () => {
    if (files.length === 0) {
      toast.error("Add at least one file first.");
      return;
    }
    setConverting(true);
    try {
      const job = await createJob(files.map((f) => f.id), settings);
      router.push(`/jobs/${job.id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to start conversion");
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
            PDF, DOCX, PPTX and XLSX — converted locally on your machine. Private, deterministic, and yours.
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
                  : `${files.length} file${files.length > 1 ? "s" : ""} ready · ${formatBytes(files.reduce((sum, f) => sum + f.size, 0))}`}
              </p>
              <Button
                size="lg"
                disabled={files.length === 0 || converting}
                onClick={handleConvert}
                className="w-full sm:w-auto"
              >
                {converting ? "Starting…" : files.length > 1 ? `Convert all (${files.length})` : "Convert to Markdown"}
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

          {history.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
                <FileClock className="h-8 w-8 text-muted-foreground/60" />
                <p className="text-sm font-medium">No conversions yet</p>
                <p className="max-w-sm text-sm text-muted-foreground">
                  Upload your first PDF, DOCX, PPTX or XLSX file to create Markdown.
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

      <Dialog open={locked} onOpenChange={(open) => !open && !authChecking && setLocked(false)}>
        <DialogContent>
          <DialogClose aria-label="Close" />
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
