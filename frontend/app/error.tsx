"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Route-level error boundary. Without this, any render-time throw left the
 * user on a blank white page with no way back.
 */
export default function RouteError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  // Next 16 renamed this from `reset`; `retry()` re-fetches and re-renders the
  // boundary's children rather than only clearing the error state.
  retry: () => void;
}) {
  React.useEffect(() => {
    console.error("Markforge route error:", error);
  }, [error]);

  return (
    <div className="container flex min-h-dvh max-w-2xl items-center justify-center py-16">
      <Card className="w-full">
        <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
          <AlertTriangle className="h-10 w-10 text-destructive/70" />
          <h1 className="text-lg font-semibold">Something broke on this page</h1>
          <p className="max-w-md text-sm text-muted-foreground">
            Your documents are safe — this is a display error, not a data error.
            Nothing has been deleted from your machine.
          </p>
          {error.digest && (
            <p className="font-mono text-xs text-muted-foreground">
              Reference: {error.digest}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
            <Button onClick={() => retry()}>Try again</Button>
            <Link href="/" className={cn(buttonVariants({ variant: "outline" }))}>
              Back to convert
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
