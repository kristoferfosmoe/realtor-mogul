"use client";

import { useMemo, useState } from "react";

import { Sparkline } from "@/components/Sparkline";
import type { MarketSummary } from "@/lib/api";
import { pct, usd } from "@/lib/format";
import { marketSymbol, shortName, signedPct } from "@/lib/markets";

const SORTS = [
  { id: "size", label: "SIZE" },
  { id: "yoy", label: "RENT YOY" },
  { id: "yield", label: "YIELD" },
] as const;
type SortId = (typeof SORTS)[number]["id"];

/** Left-hand "market watch": every metro quoted by its current rent and YoY change. */
export function MarketList({
  markets,
  selectedId,
  onSelect,
}: {
  markets: MarketSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortId>("size");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = markets.filter((m) => !q || m.geography.name.toLowerCase().includes(q));
    const key = (m: MarketSummary): number =>
      sort === "yoy"
        ? -(m.rent?.yoy ?? -Infinity)
        : sort === "yield"
          ? -(m.gross_yield ?? -Infinity)
          : m.geography.kind === "country"
            ? -1
            : (m.geography.size_rank ?? 1e9);
    return [...filtered].sort((a, b) => key(a) - key(b));
  }, [markets, query, sort]);

  return (
    <section className="panel market-list">
      <div className="panel-head">
        <span>Market watch</span>
        <span className="muted">{markets.length}</span>
      </div>
      <div className="heat-controls">
        <input
          className="text-input"
          placeholder="Search metros…"
          aria-label="Search metros"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="range-tabs stretch" role="group" aria-label="Sort markets">
          {SORTS.map((s) => (
            <button
              key={s.id}
              type="button"
              className={sort === s.id ? "on" : ""}
              onClick={() => setSort(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
      <ul className="mkt-rows">
        {rows.map((m) => {
          const yoy = m.rent?.yoy;
          const tone = yoy == null ? "flat" : yoy >= 0 ? "up" : "down";
          return (
            <li key={m.geography.id}>
              <button
                type="button"
                className={`mkt-row${m.geography.id === selectedId ? " selected" : ""}`}
                onClick={() => onSelect(m.geography.id)}
              >
                <span className="mkt-id">
                  <span className="tape-sym">{marketSymbol(m.geography.name)}</span>
                  <span className="muted mkt-name">{shortName(m.geography.name)}</span>
                </span>
                <Sparkline values={m.rent_spark} width={56} height={20} />
                <span className="mkt-quote num">
                  <span>{usd(m.rent?.latest)}</span>
                  <span className={tone}>
                    {yoy == null ? "—" : signedPct(yoy)}
                    {sort === "yield" && (
                      <span className="muted"> · {pct(m.gross_yield, 1)}</span>
                    )}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
        {rows.length === 0 && <li className="empty">No matching metros</li>}
      </ul>
    </section>
  );
}
