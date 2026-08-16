"use client";

import * as React from "react";
import { getHistory } from "@/lib/api";
import type { HistoryItem } from "@/lib/types";

export function useHistory(limit = 50) {
  const [history, setHistory] = React.useState<HistoryItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    try {
      const items = await getHistory();
      setHistory(limit > 0 ? items.slice(0, limit) : items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  return { history, loading, error, refresh };
}
