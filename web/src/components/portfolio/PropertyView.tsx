"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { EquityChart } from "@/components/EquityChart";
import { api, type PropertyDetail } from "@/lib/api";
import { mult, pct, usd } from "@/lib/format";
import { signedPct } from "@/lib/markets";
import { toneOf, typeLabel, VALUE_SOURCES } from "@/lib/portfolio";

import { Kpi } from "./Kpi";
import { Ledger } from "./Ledger";
import { LoanPanel, ProFormaPanel, RentRoll, Valuations } from "./SidePanels";

export function PropertyView({ id }: { id: number }) {
  const router = useRouter();
  const [detail, setDetail] = useState<PropertyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    api
      .property(id)
      .then((d) => {
        setDetail(d);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    api
      .property(id)
      .then((d) => !cancelled && setDetail(d))
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error && !detail) return <div className="empty down">{error}</div>;
  if (!detail) return <div className="empty">LOADING…</div>;

  const { property: prop, performance: f } = detail;
  const remove = async () => {
    if (!window.confirm(`Delete "${prop.name}" and its ledger, leases and valuations?`)) return;
    await api.deleteProperty(prop.id);
    router.push("/portfolio");
  };
  const t12Short = f.t12.months < 11.5;

  return (
    <main className="workspace portfolio-grid">
      <div className="col col-main">
        <section className="panel">
          <div className="quote">
            <div className="quote-id">
              <div className="quote-name">
                {prop.name} {f.sold && <span className="badge neutral">SOLD</span>}
              </div>
              <div className="quote-addr">
                {typeLabel(prop.property_type ?? "")} · {prop.units} unit{prop.units === 1 ? "" : "s"}
                {prop.market_name && ` · ${prop.market_name}`}
                {prop.address && ` · ${prop.address}`}
              </div>
            </div>
            <div>
              <div className="stat-label" title={`Based on ${VALUE_SOURCES[f.value_source] ?? f.value_source}`}>
                {f.sold ? "Sold for" : "Est. value"} · {VALUE_SOURCES[f.value_source] ?? f.value_source}
              </div>
              <div className="quote-price num">
                <span className="big">{usd(f.value)}</span>
                <span className={`chg ${toneOf(f.gain)}`}>
                  {f.gain >= 0 ? "+" : "−"}
                  {usd(Math.abs(f.gain))} ({f.gain_pct == null ? "—" : signedPct(f.gain_pct)})
                </span>
              </div>
            </div>
            <div className="quote-stats">
              <Stat label="Cost basis" value={usd(f.cost_basis)} />
              <Stat label="Cash in" value={usd(f.equity_invested)} />
              <Stat label="Debt" value={usd(f.loan_balance)} />
              <Stat label="Equity" value={usd(f.equity)} />
              <Stat label="Held" value={`${(f.months_held / 12).toFixed(1)} yr`} />
            </div>
            <div className="section-actions">
              <Link href={`/portfolio/${prop.id}/edit`} className="btn btn-sm">
                EDIT
              </Link>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => void remove()}>
                DELETE
              </button>
            </div>
          </div>
          <div className="kpis">
            <Kpi label="NOI · T12 ann." value={usd(f.noi_annualized)} tone={toneOf(f.noi_annualized)} />
            <Kpi
              label="Cash flow · T12 ann."
              value={usd(f.cash_flow_annualized)}
              sub={f.cash_flow_annualized == null ? undefined : `${usd(f.cash_flow_annualized / 12)}/mo`}
              tone={toneOf(f.cash_flow_annualized)}
            />
            <Kpi label="Cap rate (value)" value={pct(f.cap_rate_on_value)} tone={toneOf(f.cap_rate_on_value, 0.06)} />
            <Kpi label="Cap rate (cost)" value={pct(f.cap_rate_on_cost)} tone={toneOf(f.cap_rate_on_cost, 0.06)} />
            <Kpi label="Cash on cash" value={pct(f.cash_on_cash)} tone={toneOf(f.cash_on_cash, 0.08)} />
            <Kpi
              label="IRR since purchase"
              value={pct(f.irr)}
              tone={toneOf(f.irr, 0.12)}
              sub={f.irr == null ? "needs 6+ months" : f.sold ? "realized" : "mark-to-market"}
              title="Includes a hypothetical sale today at the estimated value, less 6% selling costs"
            />
            <Kpi label="Equity multiple" value={mult(f.equity_multiple)} tone={toneOf(f.equity_multiple, 1)} />
            <Kpi label="Total return" value={usd(f.total_return)} tone={toneOf(f.total_return)} />
            <Kpi label="Distributions" value={usd(f.distributions)} sub="net cash since purchase" />
            <Kpi
              label="Occupancy"
              value={pct(f.occupancy, 0)}
              sub={`${f.occupied_units}/${f.units} · ${usd(f.scheduled_rent)}/mo`}
              tone={toneOf(f.occupancy, 0.9)}
            />
          </div>
          {(f.debt_service_imputed || f.uncategorized_count > 0 || t12Short) && (
            <div className="warn-strip">
              {f.debt_service_imputed && (
                <span>▲ No mortgage payments in the ledger — using the loan schedule for debt service.</span>
              )}
              {f.uncategorized_count > 0 && (
                <span>
                  ▲ {f.uncategorized_count} uncategorized ledger line
                  {f.uncategorized_count === 1 ? " is" : "s are"} excluded from NOI.
                </span>
              )}
              {t12Short && <span>▲ Only {f.t12.months.toFixed(1)} months of history; annualized figures are extrapolated.</span>}
            </div>
          )}
        </section>

        <EquityChart title="Value, debt & equity" points={detail.monthly} />
        <ProFormaPanel detail={detail} />
        <Ledger propertyId={prop.id} onChange={reload} />
      </div>

      <div className="col col-right">
        <RentRoll detail={detail} onChange={reload} />
        <LoanPanel detail={detail} />
        <Valuations detail={detail} onChange={reload} />
        {prop.notes && (
          <section className="panel">
            <div className="panel-head">
              <span>Notes</span>
            </div>
            <div className="panel-body" style={{ whiteSpace: "pre-wrap" }}>
              {prop.notes}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className="stat-value num">{value}</div>
    </div>
  );
}
