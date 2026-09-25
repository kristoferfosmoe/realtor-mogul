import type { Deal, Metrics } from "@/lib/api";
import { delta, mult, pct, usd } from "@/lib/format";
import { METRICS, type MetricDef, signal, tone } from "@/lib/metrics";

interface Props {
  name: string;
  address: string;
  deal: Deal;
  metrics: Metrics;
  baseline: Metrics | null;
  baselineLabel: string;
}

const KPI_ORDER: MetricDef[] = [
  METRICS.levered_irr,
  METRICS.unlevered_irr,
  METRICS.roic,
  METRICS.cash_on_cash,
  METRICS.cap_rate,
  METRICS.dscr,
  METRICS.equity_multiple,
  METRICS.cash_flow_year1,
  METRICS.noi_year1,
  METRICS.total_profit,
];

export function formatMetric(def: MetricDef, v: number | null | undefined): string {
  return def.format === "pct" ? pct(v) : def.format === "mult" ? mult(v) : usd(v);
}

/** Headline "quote": the deal's IRR presented like a last price, then KPI tiles. */
export function Quote({ name, address, deal, metrics, baseline, baselineLabel }: Props) {
  const irr = metrics.levered_irr;
  const irrDelta = diff(irr, baseline?.levered_irr);
  const sig = signal(metrics);
  const sigTone = sig === "BUY" ? "up" : sig === "PASS" ? "down" : "flat";

  return (
    <section className="panel">
      <div className="quote">
        <div className="quote-id">
          <div className="quote-name">
            {name || "Untitled deal"}{" "}
            <span className={`badge ${sigTone}`} title="Screen against target returns">
              {sig}
            </span>
          </div>
          <div className="quote-addr">{address || "No address"}</div>
        </div>
        <div>
          <div className="stat-label">Levered IRR · {deal.hold_years}-yr hold</div>
          <div className="quote-price num">
            <span className={`big ${tone(METRICS.levered_irr, irr)}`}>{pct(irr)}</span>
            <span className={`chg ${deltaTone(irrDelta)}`}>
              {delta(irrDelta, "pct")} pts
            </span>
          </div>
        </div>
        <div className="quote-stats">
          <Stat label="Price" value={usd(deal.purchase_price)} />
          <Stat label="Rent / mo" value={usd(deal.monthly_rent)} />
          <Stat label="Cash in" value={usd(metrics.equity_invested)} />
          <Stat label="Loan" value={usd(metrics.loan_amount)} />
          <Stat label="Rent / price" value={pct(metrics.rent_to_price)} />
          <Stat label="Break-even occ." value={pct(metrics.break_even_occupancy, 1)} />
        </div>
      </div>
      <div className="kpis">
        {KPI_ORDER.map((def) => {
          const v = metrics[def.key];
          const d = diff(v, baseline?.[def.key]);
          return (
            <div key={def.key} className={`kpi ${tone(def, v)}`} title={def.hint}>
              <div className="stat-label">{def.label}</div>
              <div className={`kpi-value num ${tone(def, v)}`}>{formatMetric(def, v)}</div>
              <div className={`kpi-delta num ${deltaTone(d)}`}>
                {delta(d, def.format)} <span className="muted">{baselineLabel}</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
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

function diff(a: number | null | undefined, b: number | null | undefined): number | null {
  return a == null || b == null ? null : a - b;
}

function deltaTone(d: number | null): string {
  if (d == null || Math.abs(d) < 1e-9) return "muted";
  return d > 0 ? "up" : "down";
}
