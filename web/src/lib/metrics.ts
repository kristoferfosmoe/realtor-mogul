import type { Metrics, MetricKey } from "./api";

export type MetricFormat = "pct" | "usd" | "mult";

export interface MetricDef {
  key: MetricKey;
  label: string;
  short: string;
  format: MetricFormat;
  /** Screening threshold; values at or above it read as healthy. */
  target?: number;
  hint: string;
}

export const METRICS = {
  levered_irr: {
    key: "levered_irr",
    label: "Levered IRR",
    short: "IRR",
    format: "pct",
    target: 0.12,
    hint: "Annualized return on your cash, including financing and sale",
  },
  unlevered_irr: {
    key: "unlevered_irr",
    label: "Unlevered IRR",
    short: "IRR·U",
    format: "pct",
    target: 0.08,
    hint: "Annualized return as if bought all-cash",
  },
  roic: {
    key: "roic",
    label: "ROIC",
    short: "ROIC",
    format: "pct",
    target: 0.06,
    hint: "Year-one NOI ÷ total capital (price + closing + rehab)",
  },
  cash_on_cash: {
    key: "cash_on_cash",
    label: "Cash on Cash",
    short: "CoC",
    format: "pct",
    target: 0.08,
    hint: "Year-one cash flow ÷ cash invested",
  },
  cap_rate: {
    key: "cap_rate",
    label: "Cap Rate",
    short: "CAP",
    format: "pct",
    target: 0.06,
    hint: "Year-one NOI ÷ purchase price",
  },
  dscr: {
    key: "dscr",
    label: "DSCR",
    short: "DSCR",
    format: "mult",
    target: 1.25,
    hint: "Year-one NOI ÷ debt service; lenders usually want 1.20–1.25x",
  },
  equity_multiple: {
    key: "equity_multiple",
    label: "Equity Multiple",
    short: "EM",
    format: "mult",
    target: 2,
    hint: "Total cash returned ÷ cash invested",
  },
  cash_flow_year1: {
    key: "cash_flow_year1",
    label: "Cash Flow Y1",
    short: "CF",
    format: "usd",
    target: 0,
    hint: "Year-one NOI minus debt service",
  },
  noi_year1: {
    key: "noi_year1",
    label: "NOI Y1",
    short: "NOI",
    format: "usd",
    hint: "Year-one net operating income, after reserves",
  },
  total_profit: {
    key: "total_profit",
    label: "Total Profit",
    short: "P/L",
    format: "usd",
    target: 0,
    hint: "Cash returned over the hold, minus cash invested",
  },
} satisfies Record<string, MetricDef>;

export type Tone = "up" | "down" | "flat";

export function tone(def: MetricDef, value: number | null | undefined): Tone {
  if (value == null || def.target == null) return "flat";
  return value >= def.target ? "up" : "down";
}

export type Signal = "BUY" | "WATCH" | "PASS";

/** Simple screen against the targets above; the recommendations engine replaces this. */
export function signal(m: Metrics): Signal {
  const irr = m.levered_irr ?? -1;
  const dscrOk = m.dscr == null || m.dscr >= 1.2;
  if (irr >= METRICS.levered_irr.target && dscrOk && m.cash_flow_year1 >= 0) return "BUY";
  if (irr >= 0.08 && (m.dscr == null || m.dscr >= 1)) return "WATCH";
  return "PASS";
}
