"use client";

/* eslint-disable @next/next/no-img-element -- rendered markdown images should bypass next/image */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface MarkdownPreviewProps {
  content: string;
  className?: string;
  /** Base URL that relative `assets/...` paths resolve against, e.g.
   *  `/api/jobs/{jobId}/assets/{fileId}`. The stored Markdown deliberately
   *  keeps relative paths so a downloaded ZIP stays portable; only this
   *  rendered view rewrites them. */
  assetBase?: string;
}

/** Allow safe link targets and reject anything that could execute script.
 *  Exported for unit testing: this is a security boundary, not a detail. */
export function safeHref(url: string | Blob | undefined): string | undefined {
  if (typeof url !== "string") return undefined;
  if (/^(https?:|mailto:)/i.test(url)) return url;
  if (url.startsWith("/") || url.startsWith("#") || url.startsWith("./") || url.startsWith("../")) return url;
  return undefined;
}

/** Images may only come from the local output directory or embedded data URIs.
 *  Exported for unit testing: this is a security boundary, not a detail. */
export function safeSrc(url: string | Blob | undefined, assetBase?: string): string | undefined {
  if (typeof url !== "string") return undefined;
  if (/^data:image\//i.test(url)) return url;
  // Figures we extracted are written as `assets/<name>`; point them at the
  // job's asset route. The name is encoded rather than interpolated raw, and
  // anything with a path separator is rejected outright.
  const relative = url.replace(/^\.\//, "");
  if (assetBase && relative.startsWith("assets/")) {
    const name = relative.slice("assets/".length);
    if (!name || name.includes("/") || name.includes("..")) return undefined;
    return `${assetBase}/${encodeURIComponent(name)}`;
  }
  // `//host/path` is protocol-relative: the browser resolves it against the
  // page scheme and fetches it from `host`. It starts with "/", so a naive
  // same-origin check lets a crafted document beacon out on preview.
  if (url.startsWith("//")) return undefined;
  if (url.startsWith("/") || url.startsWith("./") || url.startsWith("../")) return url;
  return undefined;
}

export function MarkdownPreview({ content, className, assetBase }: MarkdownPreviewProps) {
  return (
    <div className={cn("markdown-body px-5 py-4", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, href, ...props }) => (
            <a {...props} href={safeHref(href) ?? undefined} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          img: ({ alt, src }) => {
            if (!src) return null;
            const safe = safeSrc(src, assetBase);
            if (!safe) return null;
            return (
              <span className="my-2 block">
                <img src={safe} alt={alt} className="max-h-[420px] w-auto max-w-full rounded-lg border border-border" loading="lazy" />
              </span>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
