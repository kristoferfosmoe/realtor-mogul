"use client";

import { useMemo, useState } from "react";

import type { Recommendation } from "@/lib/api";
import { mult, pct, usd } from "@/lib/format";
import { signedPct } from "@/lib/markets";

export const SIGNAL_TONE: Record<string, string> = {
  "STRONG BUY": "up",
  BUY: "up",
  WATCH: "flat",
  PASS: "down",
};

type Col = { id: string; label: string; value: (r: Recommendation) => number | string | null };

const COLS: Col[] = [
  { id: "score", label: "Score", value: (r) => r.evaluation.score },
  { id: "address", label: "Listing", value: (r) => r.listing.address },
  { id: "price", label: "Price", value: (r) => r.listing.price },
  { id: "rent", label: "Est. rent", value: (r) => r.rent.monthly },
  { id: "rtp", label: "R/P", value: (r) => r.rent.monthly / r.listing.price },
  { id: "cap", label: "Cap", value: (r) => r.evaluation.metrics.cap_rate ?? null },
  { id: "coc", label: "CoC", value: (r) => r.evaluation.metrics.cash_on_cash ?? null },
  { id: "irr", label: "IRR", value: (r) => r.evaluation.metrics.levered_irr ?? null },
  { id: "dscr", label: "DSCR", value: (r) => r.evaluation.metrics.dscr ?? null },
  { id: "dom", label: "DOM", value: (r) => r.listing.days_on_market ?? null },
];

/** Ranked screener results, like a stock screener's result grid. */
export function ResultsTable({
  rows,
  selectedId,
  onSelect,
  targets,
}: {
  rows: Recommendation[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  targets: { irr: number; coc: number; dscr: number };
}) {
  const [sort, setSort] = useState<{ id: string; dir: 1 | -1 }>({ id: "score", dir: -1 });
  const [signals, setSignals] = useState<string[]>(["STRONG BUY", "BUY", "WATCH"]);

  const shown = useMemo(() => {
    const col = COLS.find((c) => c.id === sort.id) ?? COLS[0]!;
    return rows
      .filter((r) => signals.includes(r.evaluation.signal))
      .sort((a, b) => {
        const av = col.value(a);
        const bv = col.value(b);
        if (av == null) return 1;
        if (bv == null) return -1;
        return (av < bv ? -1 : av > bv ? 1 : 0) * sort.dir;
      });
  }, [rows, sort, signals]);

  const tone = (v: number | null | undefined, target: number) =>
    v == null ? "" : v >= target ? "up" : "down";

  return (
    <section className="panel">
      <div className="panel-head">
        <span>Results · {shown.length}</span>
        <span className="chips" role="group" aria-label="Signals shown">
          {["STRONG BUY", "BUY", "WATCH", "PASS"].map((s) => (
            <button
              key={s}
              type="button"
              className={`chip${signals.includes(s) ? " on" : ""}`}
              onClick={() => setSignals((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]))}
            >
              {s} {rows.filter((r) => r.evaluation.signal === s).length}
            </button>
          ))}
        </span>
      </div>
      <div className="table-scroll">
        <table className="grid num">
          <thead>
            <tr>
              <th>Signal</th>
              {COLS.map((c) => (
                <th
                  key={c.id}
                  className="sortable"
                  style={c.id === "address" ? { textAlign: "left" } : undefined}
                  onClick={() => setSort((s) => ({ id: c.id, dir: s.id === c.id ? ((-s.dir) as 1 | -1) : -1 }))}
                >
                  {c.label} {sort.id === c.id ? (sort.dir === 1 ? "▲" : "▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const l = r.listing;
              const m = r.evaluation.metrics;
              return (
                <tr
                  key={l.id}
                  className={`clickable${l.id === selectedId ? " selected" : ""}`}
                  onClick={() => onSelect(l.id)}
                >
                  <td>
                    <span className={`badge ${SIGNAL_TONE[r.evaluation.signal]}`}>{r.evaluation.signal}</span>
                    {r.is_new && (
                      <span className="badge flat" style={{ marginLeft: 4 }}>
                        NEW
                      </span>
                    )}
                  </td>
                  <td>
                    {r.evaluation.score.toFixed(0)}
                    <span className="score-bar">
                      <span
                        style={{
                          width: `${r.evaluation.score}%`,
                          background: r.evaluation.score >= 75 ? "var(--up)" : r.evaluation.score >= 50 ? "var(--accent)" : "var(--down)",
                        }}
                      />
                    </span>
                  </td>
                  <td style={{ textAlign: "left" }}>
                    <div style={{ color: "var(--text)", fontWeight: 600, fontFamily: "var(--font-sans)" }}>
                      {l.address}
                    </div>
                    <div className="muted" style={{ fontSize: 11 }}>
                      {l.city}, {l.state} · {l.beds ?? "?"}bd/{l.baths ?? "?"}ba
                      {l.sqft ? ` · ${l.sqft.toLocaleString()} sf` : ""}
                      {l.units > 1 ? ` · ${l.units}u` : ""}
                    </div>
                  </td>
                  <td>
                    <div>{usd(l.price)}</div>
                    {l.price_change != null && (
                      <div className={l.price_change < 0 ? "down" : "up"} style={{ fontSize: 11 }}>
                        {l.price_change < 0 ? "▼" : "▲"} {signedPct(l.price_change)}
                      </div>
                    )}
                  </td>
                  <td title={`${r.rent.basis} (${r.rent.confidence} confidence)`}>
                    {usd(r.rent.monthly)}
                    <span className={`conf ${r.rent.confidence}`} />
                  </td>
                  <td className={r.rent.monthly / l.price >= 0.01 ? "up" : ""}>{pct(r.rent.monthly / l.price, 2)}</td>
                  <td>{pct(m.cap_rate)}</td>
                  <td className={tone(m.cash_on_cash, targets.coc)}>{pct(m.cash_on_cash)}</td>
                  <td className={tone(m.levered_irr, targets.irr)}>{pct(m.levered_irr)}</td>
                  <td className={m.dscr == null ? "" : tone(m.dscr, targets.dscr)}>{mult(m.dscr)}</td>
                  <td>{l.days_on_market ?? "—"}</td>
                </tr>
              );
            })}
            {shown.length === 0 && (
              <tr>
                <td colSpan={COLS.length + 1} className="muted" style={{ textAlign: "center", padding: 24 }}>
                  No listings match. Loosen the buy box or show more signals.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
