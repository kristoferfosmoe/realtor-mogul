import type { Indicator, MarketSummary, Point, SeriesStats } from "./api";
import { pct, usd } from "./format";

/** Ticker-style symbol: "Austin, TX" -> "AUSTIN", "Kansas City, MO" -> "KC". */
export function marketSymbol(name: string): string {
  const city = (name.split(",")[0] ?? name).split("-")[0]!;
  const words = city.toUpperCase().replace(/[^A-Z\s]/g, "").split(/\s+/).filter(Boolean);
  if (words.length > 1) return words.map((w) => w[0]).join("");
  return words[0] || "MKT";
}

export function shortName(name: string): string {
  // Zillow metro names can be long ("Miami-Fort Lauderdale-West Palm Beach, FL").
  const [city = name, state] = name.split(", ");
  const first = city.split("-")[0];
  return state ? `${first}, ${state}` : city;
}

/** Growth assumptions for the underwriting engine from a market's history. */
export function growthDefaults(m: MarketSummary): { rent_growth?: number; appreciation?: number } {
  const pick = (s: SeriesStats | null | undefined) => s?.cagr_5y ?? s?.cagr_3y ?? s?.yoy ?? undefined;
  const round = (v: number | undefined) => (v == null ? undefined : Math.round(v * 1000) / 1000);
  return { rent_growth: round(pick(m.rent)), appreciation: round(pick(m.home_value)) };
}

/** Headline number and change for an indicator, in the form a trader expects. */
export function indicatorQuote(ind: Indicator): {
  value: string;
  change: string;
  direction: number;
  note: string;
} {
  const s = ind.stats;
  if (!s) return { value: "—", change: "", direction: 0, note: "" };
  if (ind.unit === "rate") {
    const bps = s.change == null ? null : Math.round(s.change * 10_000);
    return {
      value: pct(s.latest),
      change: bps == null ? "" : `${bps > 0 ? "+" : bps < 0 ? "−" : ""}${Math.abs(bps)} bp`,
      direction: Math.sign(bps ?? 0),
      note: s.yoy_abs == null ? "" : `${signedPts(s.yoy_abs)} YoY`,
    };
  }
  if (ind.unit === "index") {
    // An index level means little; its year-over-year change is the signal.
    return {
      value: s.yoy == null ? "—" : `${pct(s.yoy, 1)} YoY`,
      change: s.change_pct == null ? "" : signedPct(s.change_pct, 2),
      direction: Math.sign(s.change_pct ?? 0),
      note: `index ${s.latest.toFixed(1)}`,
    };
  }
  return {
    value: usd(s.latest),
    change: s.yoy == null ? "" : `${signedPct(s.yoy, 1)} YoY`,
    direction: Math.sign(s.yoy ?? 0),
    note: s.change_pct == null ? "" : `${signedPct(s.change_pct, 2)} m/m`,
  };
}

export function signedPct(v: number, digits = 1): string {
  const s = `${Math.abs(v * 100).toFixed(digits)}%`;
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s;
}

function signedPts(v: number): string {
  const s = `${Math.abs(v * 100).toFixed(2)} pts`;
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s;
}

export interface YearRow {
  year: number;
  rent: number | null;
  rentYoy: number | null;
  value: number | null;
  valueYoy: number | null;
  grossYield: number | null;
}

/** Year-end (or latest-in-year) snapshot per calendar year, newest first. */
export function annualTable(rent: Point[], value: Point[]): YearRow[] {
  const lastByYear = (pts: Point[]) => {
    const m = new Map<number, number>();
    for (const p of pts) m.set(Number(p.date.slice(0, 4)), p.value);
    return m;
  };
  const r = lastByYear(rent);
  const v = lastByYear(value);
  const years = [...new Set([...r.keys(), ...v.keys()])].sort((a, b) => b - a);
  const yoy = (m: Map<number, number>, y: number) => {
    const now = m.get(y);
    const prev = m.get(y - 1);
    return now != null && prev ? now / prev - 1 : null;
  };
  return years.map((year) => {
    const rentV = r.get(year) ?? null;
    const valueV = v.get(year) ?? null;
    return {
      year,
      rent: rentV,
      rentYoy: yoy(r, year),
      value: valueV,
      valueYoy: yoy(v, year),
      grossYield: rentV != null && valueV ? (rentV * 12) / valueV : null,
    };
  });
}
