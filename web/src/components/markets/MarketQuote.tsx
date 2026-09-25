import Link from "next/link";

import type { MarketSummary } from "@/lib/api";
import { pct, usd } from "@/lib/format";
import { growthDefaults, marketSymbol, signedPct } from "@/lib/markets";

/** Header for the selected market, styled like a stock quote. */
export function MarketQuote({ market }: { market: MarketSummary }) {
  const { rent, home_value: value } = market;
  const yoy = rent?.yoy;
  const growth = growthDefaults(market);
  return (
    <section className="panel">
      <div className="quote">
        <div className="quote-id">
          <div className="quote-name">
            {marketSymbol(market.geography.name)}{" "}
            <span className="muted" style={{ fontWeight: 500, fontSize: 14 }}>
              {market.geography.name}
            </span>
          </div>
          <div className="quote-addr">
            {market.geography.kind === "country" ? "National" : `Metro #${market.geography.size_rank ?? "—"}`}
            {rent && ` · as of ${rent.latest_date}`} · {market.sources.join(", ")}
          </div>
        </div>
        <div>
          <div className="stat-label">Typical rent / mo</div>
          <div className="quote-price num">
            <span className="big">{usd(rent?.latest)}</span>
            <span className={`chg ${yoy == null ? "muted" : yoy >= 0 ? "up" : "down"}`}>
              {yoy == null ? "—" : `${signedPct(yoy)} YoY`}
            </span>
          </div>
        </div>
        <div className="quote-stats">
          <Stat label="Rent 3Y CAGR" value={pct(rent?.cagr_3y, 1)} />
          <Stat label="Rent 5Y CAGR" value={pct(rent?.cagr_5y, 1)} />
          <Stat label="Home value" value={usd(value?.latest)} />
          <Stat
            label="Value YoY"
            value={value?.yoy == null ? "—" : signedPct(value.yoy)}
            tone={value?.yoy == null ? "" : value.yoy >= 0 ? "up" : "down"}
          />
          <Stat label="Value 5Y CAGR" value={pct(value?.cagr_5y, 1)} />
          <Stat label="Gross yield" value={pct(market.gross_yield)} />
          <Stat
            label="Price / rent"
            value={market.gross_yield ? `${(1 / market.gross_yield).toFixed(1)}x` : "—"}
          />
        </div>
        <Link
          href={`/?market=${market.geography.id}`}
          className="btn btn-buy"
          title={`New deal with rent growth ${pct(growth.rent_growth, 1)} and appreciation ${pct(growth.appreciation, 1)}`}
        >
          UNDERWRITE HERE →
        </Link>
      </div>
    </section>
  );
}

function Stat({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className={`stat-value num ${tone}`}>{value}</div>
    </div>
  );
}
