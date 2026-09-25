"use client";

import Link from "next/link";

import { pct } from "@/lib/format";
import { indicatorQuote } from "@/lib/markets";
import { METRICS, tone } from "@/lib/metrics";

import { useMarketData } from "./MarketDataContext";
import { useWatchlist } from "./WatchlistContext";

const INDICATOR_SYMBOLS: Record<string, string> = {
  rent_index: "US.RENT",
  home_value: "US.HOME",
  mortgage_rate_30y: "MORT30",
  cpi_rent: "CPI.RENT",
  rental_vacancy: "US.VAC",
};

/** Scrolling strip: national indicators, then watchlist deals quoted by levered IRR. */
export function TickerTape() {
  const { deals, loaded } = useWatchlist();
  const { indicators } = useMarketData();

  const render = (dup: string) => [
    ...indicators.map((ind) => {
      const q = indicatorQuote(ind);
      const arrow = q.direction > 0 ? "▲" : q.direction < 0 ? "▼" : "•";
      const cls = q.direction > 0 ? "up" : q.direction < 0 ? "down" : "flat";
      return (
        <Link key={`i-${ind.metric}${dup}`} href="/markets" className="tape-item">
          <span className="tape-sym">{INDICATOR_SYMBOLS[ind.metric] ?? ind.label}</span>
          <span className="num">{q.value}</span>
          {q.change && (
            <span className={`num ${cls}`}>
              {arrow} {q.change}
            </span>
          )}
        </Link>
      );
    }),
    ...deals.map((d) => {
      const irrTone = tone(METRICS.levered_irr, d.metrics.levered_irr);
      return (
        <Link key={`d-${d.id}${dup}`} href={`/?deal=${d.id}`} className="tape-item">
          <span className="tape-sym">{ticker(d.name)}</span>
          <span className={`num ${irrTone}`}>
            {irrTone === "up" ? "▲" : irrTone === "down" ? "▼" : "•"} {pct(d.metrics.levered_irr)}
          </span>
          <span className="num muted">CAP {pct(d.metrics.cap_rate)}</span>
        </Link>
      );
    }),
  ];

  const items = render("");
  if (items.length === 0) {
    return (
      <div className="tape">
        <div className="tape-empty">
          {loaded ? "NO QUOTES — LOAD MARKET DATA OR SAVE A DEAL TO FILL THE TAPE" : ""}
        </div>
      </div>
    );
  }

  // Rendered twice so the -50% translate loops seamlessly.
  return (
    <div className="tape">
      <div className="tape-track" style={{ animationDuration: `${Math.max(30, items.length * 6)}s` }}>
        {items}
        {render("-dup")}
      </div>
    </div>
  );
}

/** "12 Maple St Duplex" -> "MAPLE.ST"; a short ticker-style symbol for a deal. */
export function ticker(name: string): string {
  const words = name
    .toUpperCase()
    .replace(/[^A-Z0-9 ]/g, "")
    .split(/\s+/)
    .filter((w) => w && !/^\d+$/.test(w));
  if (words.length === 0) return name.toUpperCase().slice(0, 6);
  return words
    .slice(0, 2)
    .map((w) => w.slice(0, 5))
    .join(".");
}
