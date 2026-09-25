"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useMarketData } from "@/components/MarketDataContext";
import { api, type MarketDetail } from "@/lib/api";

import { AnnualTable } from "./AnnualTable";
import { MacroPanel } from "./MacroPanel";
import { MarketChart } from "./MarketChart";
import { MarketList } from "./MarketList";
import { MarketQuote } from "./MarketQuote";
import { RentBenchmarks } from "./RentBenchmarks";
import { SourcesPanel } from "./SourcesPanel";

export function MarketsView() {
  const router = useRouter();
  const param = useSearchParams().get("geo");
  const { markets, indicators, loaded, error } = useMarketData();
  const [detail, setDetail] = useState<{ id: number; data: MarketDetail } | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Default to the largest metro; the country row is one click away.
  const fallback = markets.find((m) => m.geography.kind !== "country") ?? markets[0];
  const selectedId = param && /^\d+$/.test(param) ? Number(param) : (fallback?.geography.id ?? null);

  useEffect(() => {
    if (selectedId == null) return;
    let cancelled = false;
    api
      .market(selectedId)
      .then((data) => {
        if (cancelled) return;
        setDetail({ id: selectedId, data });
        setDetailError(null);
      })
      .catch((e: unknown) => !cancelled && setDetailError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const current = detail?.id === selectedId ? detail.data : null;
  const series = (metric: string) => current?.series.find((s) => s.metric === metric)?.points ?? [];

  if (error) return <div className="empty down">{error}</div>;
  if (!loaded) return <div className="empty">LOADING…</div>;

  return (
    <>
      {markets.length === 0 ? (
        <main className="page">
          <section className="panel empty">
            <p>No market data yet.</p>
            <p className="muted">
              Run <code>make ingest</code> to pull rent and home-value history from Zillow, national
              indicators from FRED, Census median rents and (with <code>MOGUL_HUD_API_TOKEN</code>{" "}
              set) HUD fair market rents.
            </p>
          </section>
          <SourcesPanel />
        </main>
      ) : (
        <main className="workspace">
          <div className="col">
            <MarketList
              markets={markets}
              selectedId={selectedId}
              onSelect={(id) => router.replace(`/markets?geo=${id}`, { scroll: false })}
            />
          </div>
          <div className="col col-main">
            {current ? (
              <>
                <MarketQuote market={current.summary} />
                <MarketChart rent={series("rent_index")} value={series("home_value")} />
                <RentBenchmarks benchmarks={current.benchmarks} typical={current.summary.rent?.latest} />
                <AnnualTable rent={series("rent_index")} value={series("home_value")} />
              </>
            ) : (
              <div className="panel empty">
                {detailError ? <span className="down">{detailError}</span> : "LOADING…"}
              </div>
            )}
          </div>
          <div className="col col-right">
            <MacroPanel indicators={indicators} />
            <SourcesPanel />
          </div>
        </main>
      )}
    </>
  );
}
