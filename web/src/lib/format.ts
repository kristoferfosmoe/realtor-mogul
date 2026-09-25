const usd0 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const DASH = "—";

export function usd(v: number | null | undefined): string {
  return v == null ? DASH : usd0.format(Math.round(v));
}

/** Accounting style for statements: negatives in parentheses. */
export function acct(v: number | null | undefined): string {
  if (v == null) return DASH;
  const s = usd0.format(Math.abs(Math.round(v))).replace("$", "");
  return v < -0.5 ? `(${s})` : s;
}

export function usdCompact(v: number | null | undefined): string {
  return v == null ? DASH : `$${compact.format(v)}`;
}

export function pct(v: number | null | undefined, digits = 2): string {
  return v == null ? DASH : `${(v * 100).toFixed(digits)}%`;
}

export function mult(v: number | null | undefined, digits = 2): string {
  return v == null ? DASH : `${v.toFixed(digits)}x`;
}

/** Signed change, e.g. +1.25 pts for rates or +$1,200 for money. */
export function delta(
  v: number | null | undefined,
  kind: "pct" | "usd" | "mult",
): string {
  if (v == null || Math.abs(v) < 1e-9) return "0.00";
  const sign = v > 0 ? "+" : "−";
  const a = Math.abs(v);
  if (kind === "pct") return `${sign}${(a * 100).toFixed(2)}`;
  if (kind === "mult") return `${sign}${a.toFixed(2)}`;
  return `${sign}${usd0.format(Math.round(a))}`;
}
