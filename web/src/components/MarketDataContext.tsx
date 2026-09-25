"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, type Indicator, type MarketSummary } from "@/lib/api";

interface MarketData {
  markets: MarketSummary[];
  indicators: Indicator[];
  loaded: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const MarketDataContext = createContext<MarketData | null>(null);

async function load() {
  return Promise.all([api.markets(), api.indicators()]);
}

/** Market summaries and national indicators, shared by the tape, Markets page and analyzer. */
export function MarketDataProvider({ children }: { children: React.ReactNode }) {
  const [markets, setMarkets] = useState<MarketSummary[]>([]);
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((result: Awaited<ReturnType<typeof load>>) => {
    setMarkets(result[0]);
    setIndicators(result[1]);
    setError(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      apply(await load());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [apply]);

  useEffect(() => {
    let cancelled = false;
    load()
      .then((r) => !cancelled && apply(r))
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setLoaded(true));
    return () => {
      cancelled = true;
    };
  }, [apply]);

  return (
    <MarketDataContext.Provider value={{ markets, indicators, loaded, error, refresh }}>
      {children}
    </MarketDataContext.Provider>
  );
}

export function useMarketData(): MarketData {
  const ctx = useContext(MarketDataContext);
  if (!ctx) throw new Error("useMarketData must be used inside MarketDataProvider");
  return ctx;
}
