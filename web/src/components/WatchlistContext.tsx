"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, type SavedDeal } from "@/lib/api";

interface WatchlistState {
  deals: SavedDeal[];
  loaded: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const WatchlistContext = createContext<WatchlistState | null>(null);

/** Saved deals shared by the ticker tape, the watchlist page and the analyzer. */
export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const [deals, setDeals] = useState<SavedDeal[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDeals(await api.listDeals());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .listDeals()
      .then((d) => !cancelled && (setDeals(d), setError(null)))
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setLoaded(true));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <WatchlistContext.Provider value={{ deals, loaded, error, refresh }}>
      {children}
    </WatchlistContext.Provider>
  );
}

export function useWatchlist(): WatchlistState {
  const ctx = useContext(WatchlistContext);
  if (!ctx) throw new Error("useWatchlist must be used inside WatchlistProvider");
  return ctx;
}
