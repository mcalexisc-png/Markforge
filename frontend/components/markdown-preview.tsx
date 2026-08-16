"use client";

/* eslint-disable @next/next/no-img-element -- rendered markdown images should bypass next/image */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface MarkdownPreviewProps {
  content: string;
  className?: string;
}

export function MarkdownPreview({ content, className }: MarkdownPreviewProps) {
  return (
    <div className={cn("markdown-body px-5 py-4", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          img: ({ alt, src }) => (
            <span className="my-2 block">
              <img src={src} alt={alt} className="max-h-[420px] w-auto max-w-full rounded-lg border border-border" loading="lazy" />
            </span>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
