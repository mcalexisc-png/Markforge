"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileClock, Hammer } from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { confirmDiscardChanges } from "@/lib/unsaved";

const navItems = [
  { href: "/", label: "Convert", icon: Hammer },
  { href: "/jobs", label: "History", icon: FileClock },
];

export function Header() {
  const pathname = usePathname();

  // Client-side navigation never fires `beforeunload`, so an unsaved draft
  // would vanish on a stray click here. Ask first.
  const guard = (event: React.MouseEvent) => {
    if (!confirmDiscardChanges()) event.preventDefault();
  };
  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur-md">
      <div className="container flex h-14 items-center justify-between gap-4">
        <Link href="/" onClick={guard} className="flex items-center gap-2.5 focus-visible:rounded-md" aria-label="Markforge home">
          <Logo size={26} />
          <span className="text-[17px] font-semibold tracking-tight">
            Mark<span className="text-primary">forge</span>
          </span>
        </Link>

        <nav className="flex items-center gap-1" aria-label="Main navigation">
          {navItems.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={guard}
                // The label is hidden below `sm`, so without this the link is
                // an icon with no accessible name on a phone.
                aria-label={item.label}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                )}
              >
                <item.icon className="h-4 w-4" />
                <span className="hidden sm:inline">{item.label}</span>
              </Link>
            );
          })}
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
