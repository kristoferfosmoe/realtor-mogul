"use client";

import Link from "next/link";

import { pct } from "@/lib/format";
import { METRICS, tone } from "@/lib/metrics";

import { useWatchlist } from "./WatchlistContext";

/** Scrolling strip of watchlist deals, quoted like tickers by their levered IRR. */
export function TickerTape() {
  const { deals, loaded } = useWatchlist();

  if (loaded && deals.length === 0) {
    return (
      <div className="tape">
        <div className="tape-empty">
          WATCHLIST EMPTY — SAVE A DEAL FROM THE ANALYZER TO ADD IT TO THE TAPE
        </div>
      </div>
    );
  }

  // Rendered twice so the -50% translate loops seamlessly.
  const items = [...deals, ...deals];
  return (
    <div className="tape">
      <div className="tape-track" style={{ animationDuration: `${Math.max(30, deals.length * 8)}s` }}>
        {items.map((d, i) => {
          const irrTone = tone(METRICS.levered_irr, d.metrics.levered_irr);
          return (
            <Link key={`${d.id}-${i}`} href={`/?deal=${d.id}`} className="tape-item">
              <span className="tape-sym">{ticker(d.name)}</span>
              <span className={`num ${irrTone}`}>
                {irrTone === "up" ? "▲" : irrTone === "down" ? "▼" : "•"}{" "}
                {pct(d.metrics.levered_irr)}
              </span>
              <span className="num muted">CAP {pct(d.metrics.cap_rate)}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

/** "12 Maple St Duplex" -> "MAPLE-DPLX"-ish short symbol for the tape. */
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
