import { cn } from "@/lib/utils";

export function Logo({ className, size = 28 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={cn("shrink-0", className)}
    >
      <rect x="2" y="4" width="28" height="24" rx="6" fill="hsl(var(--primary) / 0.12)" />
      <path
        d="M9 12h14M9 16h14M9 20h8"
        stroke="hsl(var(--primary))"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path d="M9 11h14M9 15h14M9 19h8" stroke="hsl(var(--foreground))" strokeWidth="2.4" strokeLinecap="round" opacity="0.35" />
    </svg>
  );
}

export function BrandMark({ size = 28 }: { size?: number }) {
  return <Logo size={size} />;
}
