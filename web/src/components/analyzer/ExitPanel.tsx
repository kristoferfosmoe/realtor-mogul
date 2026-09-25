import type { Analysis } from "@/lib/api";
import { acct, usd } from "@/lib/format";

/** Sale assumptions at the end of the hold and where the money goes. */
export function ExitPanel({ analysis }: { analysis: Analysis }) {
  const { exit, metrics } = analysis;
  const operating = analysis.years.reduce((sum, y) => sum + y.cash_flow, 0);
  return (
    <section className="panel">
      <div className="panel-head">
        <span>Exit · end of year {exit.year}</span>
      </div>
      <div className="panel-body num">
        <Row label="Sale price" value={usd(exit.sale_price)} />
        <Row label="Selling costs" value={acct(-exit.selling_costs)} />
        <Row label="Loan payoff" value={acct(-exit.loan_payoff)} />
        <Row label="Net sale proceeds" value={usd(exit.net_proceeds)} strong />
        <Row label="Operating cash flow (sum)" value={acct(operating)} />
        <Row label="Cash invested" value={acct(-metrics.equity_invested)} />
        <Row
          label="Total profit"
          value={usd(metrics.total_profit)}
          tone={metrics.total_profit >= 0 ? "up" : "down"}
          strong
        />
      </div>
    </section>
  );
}

function Row(props: { label: string; value: string; tone?: string; strong?: boolean }) {
  return (
    <div className="info-row">
      <span className="muted" style={{ fontFamily: "var(--font-sans)" }}>
        {props.label}
      </span>
      <span className={props.tone} style={{ fontWeight: props.strong ? 700 : 400 }}>
        {props.value}
      </span>
    </div>
  );
}
