"use client";

import * as React from "react";

export function usePolling(
  callback: () => void,
  intervalMs: number,
  options?: { enabled?: boolean }
) {
  const enabled = options?.enabled ?? true;
  const callbackRef = React.useRef(callback);
  callbackRef.current = callback;

  React.useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => callbackRef.current(), intervalMs);
    return () => window.clearInterval(id);
  }, [enabled, intervalMs]);
}
