"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ticker } from "@/components/TickerTape";
import { useWatchlist } from "@/components/WatchlistContext";
import { api, type SavedDeal } from "@/lib/api";
import { mult, pct, usd } from "@/lib/format";
import { METRICS, type MetricDef, signal, tone } from "@/lib/metrics";

type Column = {
  id: string;
  label: string;
  value: (d: SavedDeal) => number | string | null;
  render: (d: SavedDeal) => React.ReactNode;
};

const metricColumn = (def: MetricDef): Column => ({
  id: def.key,
  label: def.short,
  value: (d) => d.metrics[def.key] ?? null,
  render: (d) => {
    const v = d.metrics[def.key];
    const text = def.format === "pct" ? pct(v) : def.format === "mult" ? mult(v) : usd(v);
    return <span className={tone(def, v)}>{text}</span>;
  },
});

const COLUMNS: Column[] = [
  {
    id: "name",
    label: "Deal",
    value: (d) => d.name.toLowerCase(),
    render: (d) => (
      <div>
        <div style={{ fontWeight: 700, color: "var(--text)" }}>
          {ticker(d.name)} <span className="muted" style={{ fontWeight: 400 }}>{d.name}</span>
        </div>
        <div className="muted" style={{ fontSize: 11, fontFamily: "var(--font-sans)" }}>
          {d.address ?? "—"}
        </div>
      </div>
    ),
  },
  {
    id: "signal",
    label: "Signal",
    value: (d) => ["BUY", "WATCH", "PASS"].indexOf(signal(d.metrics)),
    render: (d) => {
      const s = signal(d.metrics);
      return <span className={`badge ${s === "BUY" ? "up" : s === "PASS" ? "down" : "flat"}`}>{s}</span>;
    },
  },
  {
    id: "status",
    label: "Status",
    value: (d) => d.status,
    render: (d) => <span className="badge neutral">{d.status.toUpperCase()}</span>,
  },
  {
    id: "price",
    label: "Price",
    value: (d) => d.inputs.purchase_price,
    render: (d) => usd(d.inputs.purchase_price),
  },
  {
    id: "rent",
    label: "Rent/mo",
    value: (d) => d.inputs.monthly_rent,
    render: (d) => usd(d.inputs.monthly_rent),
  },
  metricColumn(METRICS.levered_irr),
  metricColumn(METRICS.roic),
  metricColumn(METRICS.cap_rate),
  metricColumn(METRICS.cash_on_cash),
  metricColumn(METRICS.dscr),
  metricColumn(METRICS.cash_flow_year1),
  metricColumn(METRICS.equity_multiple),
];

/** Screener-style table of every saved deal. */
export default function WatchlistPage() {
  const router = useRouter();
  const { deals, loaded, error, refresh } = useWatchlist();
  const [sort, setSort] = useState<{ id: string; dir: 1 | -1 }>({ id: "levered_irr", dir: -1 });

  const rows = useMemo(() => {
    const col = COLUMNS.find((c) => c.id === sort.id) ?? COLUMNS[0]!;
    return [...deals].sort((a, b) => {
      const av = col.value(a);
      const bv = col.value(b);
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av < bv ? -1 : av > bv ? 1 : 0) * sort.dir;
    });
  }, [deals, sort]);

  const remove = async (d: SavedDeal) => {
    if (!window.confirm(`Remove "${d.name}" from the watchlist?`)) return;
    await api.deleteDeal(d.id);
    await refresh();
  };

  const buys = deals.filter((d) => signal(d.metrics) === "BUY").length;

  return (
    <main className="page">
      <section className="panel">
        <div className="panel-head">
          <span>Watchlist · {deals.length} deals</span>
          <span className="muted">
            <span className="up">{buys} BUY</span> · sorted by {sort.id.replace("_", " ")}
          </span>
        </div>
        {error ? (
          <div className="empty down">{error}</div>
        ) : !loaded ? (
          <div className="empty">LOADING…</div>
        ) : deals.length === 0 ? (
          <div className="empty">
            No deals yet. Underwrite one in the analyzer and hit <b>ADD TO WATCHLIST</b>.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="grid num">
              <thead>
                <tr>
                  {COLUMNS.map((c) => (
                    <th
                      key={c.id}
                      className="sortable"
                      aria-sort={sort.id === c.id ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                      onClick={() =>
                        setSort((s) => ({ id: c.id, dir: s.id === c.id ? ((-s.dir) as 1 | -1) : -1 }))
                      }
                    >
                      {c.label} {sort.id === c.id ? (sort.dir === 1 ? "▲" : "▼") : ""}
                    </th>
                  ))}
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.id} className="clickable" onClick={() => router.push(`/?deal=${d.id}`)}>
                    {COLUMNS.map((c) => (
                      <td key={c.id}>{c.render(d)}</td>
                    ))}
                    <td>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          void remove(d);
                        }}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
