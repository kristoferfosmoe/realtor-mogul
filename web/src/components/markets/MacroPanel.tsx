import { Sparkline } from "@/components/Sparkline";
import type { Indicator } from "@/lib/api";
import { indicatorQuote } from "@/lib/markets";

// Rising is bad news for an investor buying with debt, or for occupancy.
const RISING_IS_BAD = new Set(["mortgage_rate_30y", "rental_vacancy"]);

export function MacroPanel({ indicators }: { indicators: Indicator[] }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <span>US Macro</span>
        <span className="muted">24 mo</span>
      </div>
      {indicators.length === 0 ? (
        <div className="panel-body muted">No national data yet.</div>
      ) : (
        <ul className="macro">
          {indicators.map((ind) => {
            const q = indicatorQuote(ind);
            const bad = RISING_IS_BAD.has(ind.metric);
            const tone = q.direction === 0 ? "muted" : (q.direction > 0) !== bad ? "up" : "down";
            return (
              <li key={ind.metric} className="macro-row">
                <div>
                  <div className="macro-label">
                    {ind.label} {ind.demo && <span className="badge flat">DEMO</span>}
                  </div>
                  <div className="muted macro-note num" title={ind.stats ? `As of ${ind.stats.latest_date}` : undefined}>
                    {q.note}
                  </div>
                </div>
                <Sparkline values={ind.spark.map((p) => p.value)} invert={bad} />
                <div className="macro-quote num">
                  <div>{q.value}</div>
                  <div className={tone}>{q.change}</div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
