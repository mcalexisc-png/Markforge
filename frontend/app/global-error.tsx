"use client";

/**
 * Last-resort boundary for errors thrown in the root layout itself.
 *
 * This file replaces the root layout when active, so it gets none of the app's
 * global styles, fonts or providers, and `metadata` exports are unsupported.
 * Everything below is therefore inline, the title uses React's <title>, and the
 * colours follow the OS scheme rather than the app's theme toggle (which cannot
 * reach here).
 */
export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100dvh",
          display: "grid",
          placeItems: "center",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
          colorScheme: "light dark",
          padding: "2rem",
        }}
      >
        <title>Markforge could not start</title>
        <main style={{ maxWidth: "34rem", textAlign: "center" }}>
          <h1 style={{ fontSize: "1.125rem", marginBottom: "0.5rem" }}>
            Markforge could not start
          </h1>
          <p style={{ fontSize: "0.875rem", opacity: 0.75, lineHeight: 1.6 }}>
            Your documents are safe on disk. Try again; if this keeps happening,
            check that the backend is running.
          </p>
          {error.digest && (
            <p
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "0.75rem",
                opacity: 0.6,
              }}
            >
              Reference: {error.digest}
            </p>
          )}
          <button
            onClick={() => retry()}
            style={{
              marginTop: "1.25rem",
              padding: "0.5rem 1rem",
              borderRadius: "0.5rem",
              border: "1px solid currentColor",
              background: "transparent",
              color: "inherit",
              font: "inherit",
              fontSize: "0.875rem",
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
