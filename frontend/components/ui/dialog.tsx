"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}

interface DialogContextValue {
  close: () => void;
  titleId: string;
  descriptionId: string;
}

const DialogContext = React.createContext<DialogContextValue | null>(null);

function useDialogContext() {
  const ctx = React.useContext(DialogContext);
  if (!ctx) throw new Error("Dialog components must be used inside <Dialog>");
  return ctx;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function Dialog({ open, onOpenChange, children }: DialogProps) {
  const titleId = React.useId();
  const descriptionId = React.useId();
  const panelRef = React.useRef<HTMLDivElement>(null);
  const previousFocus = React.useRef<HTMLElement | null>(null);

  React.useEffect(() => {
    if (!open) return;
    previousFocus.current = document.activeElement as HTMLElement | null;

    const panel = panelRef.current;
    const focusables = () =>
      Array.from(panel?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    const first = () => focusables()[0];
    const last = () => focusables()[focusables().length - 1];

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onOpenChange(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const current = document.activeElement;
      const index = items.indexOf(current as HTMLElement);
      if (event.shiftKey && (index <= 0 || current === panel)) {
        event.preventDefault();
        last()?.focus();
      } else if (!event.shiftKey && (index === items.length - 1 || index === -1)) {
        event.preventDefault();
        first()?.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    // Move focus inside the dialog (the close button is the last node).
    window.setTimeout(() => first()?.focus(), 0);

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previousFocus.current?.focus();
    };
  }, [open, onOpenChange]);

  if (!open) return null;

  const close = () => onOpenChange(false);
  const value: DialogContextValue = { close, titleId, descriptionId };

  return (
    <DialogContext.Provider value={value}>
      <div
        className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <div
          className="absolute inset-0 bg-black/50 backdrop-blur-[2px] animate-fade-in"
          onClick={() => onOpenChange(false)}
        />
        <div ref={panelRef} className="relative z-10 w-full max-w-md animate-scale-in">
          {children}
        </div>
      </div>
    </DialogContext.Provider>
  );
}

const DialogHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col gap-1.5", className)} {...props} />
  )
);
DialogHeader.displayName = "DialogHeader";

const DialogTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => {
    const ctx = useDialogContext();
    return (
      <h2 ref={ref} id={ctx.titleId} className={cn("text-base font-semibold leading-none tracking-tight", className)} {...props} />
    );
  }
);
DialogTitle.displayName = "DialogTitle";

const DialogDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => {
    const ctx = useDialogContext();
    return (
      <p ref={ref} id={ctx.descriptionId} className={cn("text-sm text-muted-foreground", className)} {...props} />
    );
  }
);
DialogDescription.displayName = "DialogDescription";

const DialogContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("rounded-xl border border-border bg-card p-5 shadow-2xl", className)}
      {...props}
    >
      {children}
    </div>
  )
);
DialogContent.displayName = "DialogContent";

const DialogClose = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ className, onClick, ...props }, ref) => {
    const ctx = useDialogContext();
    return (
      <button
        ref={ref}
        type="button"
        aria-label="Close dialog"
        className={cn(
          "absolute right-3.5 top-3.5 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
          className
        )}
        onClick={(event) => {
          onClick?.(event);
          ctx.close();
        }}
        {...props}
      >
        <X className="h-4 w-4" />
      </button>
    );
  }
);
DialogClose.displayName = "DialogClose";

export { Dialog, DialogHeader, DialogTitle, DialogDescription, DialogContent, DialogClose };