"use client";

/* eslint-disable @next/next/no-img-element -- rendered markdown images should bypass next/image */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface MarkdownPreviewProps {
  content: string;
  className?: string;
}

/** Allow safe link targets and reject anything that could execute script. */
function safeHref(url: string | Blob | undefined): string | undefined {
  if (typeof url !== "string") return undefined;
  if (/^(https?:|mailto:)/i.test(url)) return url;
  if (url.startsWith("/") || url.startsWith("#") || url.startsWith("./") || url.startsWith("../")) return url;
  return undefined;
}

/** Images may only come from the local output directory or embedded data URIs. */
function safeSrc(url: string | Blob | undefined): string | undefined {
  if (typeof url !== "string") return undefined;
  if (/^data:image\//i.test(url)) return url;
  if (url.startsWith("/") || url.startsWith("./") || url.startsWith("../")) return url;
  return undefined;
}

export function MarkdownPreview({ content, className }: MarkdownPreviewProps) {
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
            const safe = safeSrc(src);
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
