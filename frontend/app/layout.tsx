import type { Metadata, Viewport } from "next";
import { ThemeProvider } from "@/components/theme-provider";
import { LanGate } from "@/components/lan-gate";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Markforge — Local-first document to Markdown",
    template: "%s · Markforge",
  },
  description:
    "Convert PDF, Office, EPUB and text documents into clean, structured Markdown. Local-first, private, self-hosted.",
  icons: { icon: "/favicon.svg" },
  manifest: "/manifest.webmanifest",
  // The app is local-only; never let a crawler index a LAN-exposed instance.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafaf8" },
    { media: "(prefers-color-scheme: dark)", color: "#12141a" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-dvh font-sans">
        <ThemeProvider>
          <LanGate>{children}</LanGate>
        </ThemeProvider>
      </body>
    </html>
  );
}
