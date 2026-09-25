"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EquityChart } from "@/components/EquityChart";
import { api, type Portfolio } from "@/lib/api";
import { mult, pct, usd } from "@/lib/format";
import { signedPct } from "@/lib/markets";
import { toneOf, typeLabel } from "@/lib/portfolio";

import { Kpi } from "./Kpi";

export function PortfolioView() {
  const router = useRouter();
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .portfolio()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <div className="empty down">{error}</div>;
  if (!data) return <div className="empty">LOADING…</div>;

  const t = data.totals;
  if (data.holdings.length === 0) {
    return (
      <main className="page">
        <section className="panel empty">
          <p>No properties yet.</p>
          <p className="muted">
            Add one you own, or convert a watchlist deal once you close on it. Then record rent
            and expenses (or import a bank CSV) to track actual returns.
          </p>
          <Link href="/portfolio/new" className="btn btn-buy">
            + ADD PROPERTY
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="workspace portfolio-grid">
      <div className="col col-main">
        <section className="panel">
          <div className="quote">
            <div className="quote-id">
              <div className="quote-name">Portfolio</div>
              <div className="quote-addr">
                {t.properties} held · {t.units} units · as of {data.as_of}
              </div>
            </div>
            <div>
              <div className="stat-label">Net equity</div>
              <div className="quote-price num">
                <span className="big">{usd(t.equity)}</span>
                <span className={`chg ${toneOf(t.gain)}`}>
                  {t.gain >= 0 ? "+" : "−"}
                  {usd(Math.abs(t.gain))} ({t.cost_basis ? signedPct(t.gain / t.cost_basis) : "—"})
                  unrealized
                </span>
              </div>
            </div>
            <Link href="/portfolio/new" className="btn btn-buy" style={{ marginLeft: "auto" }}>
              + ADD PROPERTY
            </Link>
          </div>
          <div className="kpis">
            <Kpi label="Est. value" value={usd(t.value)} sub={`cost ${usd(t.cost_basis)}`} />
            <Kpi label="Debt" value={usd(t.loan_balance)} sub={`LTV ${pct(t.ltv, 1)}`} />
            <Kpi label="NOI · annualized" value={usd(t.noi_annualized)} tone={toneOf(t.noi_annualized)} />
            <Kpi
              label="Cash flow · annualized"
              value={usd(t.cash_flow_annualized)}
              sub={`${usd(t.cash_flow_annualized / 12)}/mo`}
              tone={toneOf(t.cash_flow_annualized)}
            />
            <Kpi label="Cap rate (value)" value={pct(t.cap_rate_on_value)} tone={toneOf(t.cap_rate_on_value, 0.06)} />
            <Kpi label="Cash on cash" value={pct(t.cash_on_cash)} tone={toneOf(t.cash_on_cash, 0.08)} />
            <Kpi
              label="IRR since purchase"
              value={pct(t.irr)}
              tone={toneOf(t.irr, 0.12)}
              title="Mark-to-market: as if everything sold today, net of 6% selling costs"
            />
            <Kpi label="Total return" value={usd(t.total_return)} tone={toneOf(t.total_return)} />
            <Kpi
              label="Occupancy"
              value={pct(t.occupancy, 0)}
              sub={`${t.occupied_units}/${t.units} units`}
              tone={toneOf(t.occupancy, 0.9)}
            />
            <Kpi label="Scheduled rent" value={usd(t.scheduled_rent)} sub="per month" />
          </div>
        </section>

        <EquityChart title="Portfolio equity" points={data.months} />

        <section className="panel">
          <div className="panel-head">
            <span>Positions</span>
            <span className="muted">T12 annualized</span>
          </div>
          <div className="table-scroll">
            <table className="grid num">
              <thead>
                <tr>
                  <th>Property</th>
                  <th>Units</th>
                  <th>Occ.</th>
                  <th>Cost basis</th>
                  <th>Est. value</th>
                  <th>Gain</th>
                  <th>Debt</th>
                  <th>Equity</th>
                  <th>NOI</th>
                  <th>Cap</th>
                  <th>CoC</th>
                  <th>IRR</th>
                  <th>EM</th>
                </tr>
              </thead>
              <tbody>
                {data.holdings.map(({ property: p, performance: f }) => (
                  <tr
                    key={p.id}
                    className={`clickable${f.sold ? " dim" : ""}`}
                    onClick={() => router.push(`/portfolio/${p.id}`)}
                  >
                    <td>
                      <div style={{ fontWeight: 700, color: "var(--text)" }}>
                        {p.name} {f.sold && <span className="badge neutral">SOLD</span>}
                      </div>
                      <div className="muted" style={{ fontSize: 11, fontFamily: "var(--font-sans)" }}>
                        {typeLabel(p.property_type ?? "")} · {p.market_name ?? p.address ?? "—"}
                      </div>
                    </td>
                    <td>{f.units}</td>
                    <td className={toneOf(f.occupancy, 0.9)}>{pct(f.occupancy, 0)}</td>
                    <td>{usd(f.cost_basis)}</td>
                    <td>{usd(f.value)}</td>
                    <td className={toneOf(f.gain)}>{f.gain_pct == null ? "—" : signedPct(f.gain_pct)}</td>
                    <td>{usd(f.loan_balance)}</td>
                    <td>{usd(f.equity)}</td>
                    <td>{usd(f.noi_annualized)}</td>
                    <td>{pct(f.cap_rate_on_value)}</td>
                    <td className={toneOf(f.cash_on_cash, 0.08)}>{pct(f.cash_on_cash)}</td>
                    <td className={toneOf(f.irr, 0.12)}>{pct(f.irr)}</td>
                    <td>{mult(f.equity_multiple)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <div className="col col-right">
        <Allocation title="By market" slices={data.by_market} />
        <Allocation
          title="By type"
          slices={data.by_type.map((s) => ({ ...s, label: typeLabel(s.label) }))}
        />
      </div>
    </main>
  );
}

function Allocation({
  title,
  slices,
}: {
  title: string;
  slices: { label: string; value: number; share: number }[];
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <span>Allocation · {title}</span>
        <span className="muted">by value</span>
      </div>
      <div className="panel-body">
        {slices.map((s) => (
          <div key={s.label} className="alloc-row">
            <div className="info-row" style={{ borderBottom: 0 }}>
              <span>{s.label}</span>
              <span className="num">
                {pct(s.share, 1)} <span className="muted">{usd(s.value)}</span>
              </span>
            </div>
            <div className="bar">
              <div style={{ width: `${Math.max(1, s.share * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
