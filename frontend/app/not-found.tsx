import Link from "next/link";
import { FileQuestion } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export default function NotFound() {
  return (
    <div className="container flex min-h-dvh max-w-2xl items-center justify-center py-16">
      <Card className="w-full">
        <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
          <FileQuestion className="h-10 w-10 text-muted-foreground/60" />
          <h1 className="text-lg font-semibold">Page not found</h1>
          <p className="max-w-md text-sm text-muted-foreground">
            That page does not exist. A conversion you are looking for may have
            been deleted, or removed by the retention cleanup.
          </p>
          <Link href="/" className={cn(buttonVariants(), "mt-2")}>
            Back to convert
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
