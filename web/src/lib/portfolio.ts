import type { PropertyType } from "./api";

export const PROPERTY_TYPES: Record<PropertyType, string> = {
  single_family: "Single family",
  multi_2_4: "Small multifamily (2–4)",
  condo: "Condo",
  multifamily: "Multifamily 5+",
  commercial: "Commercial",
  land: "Land",
};

export function typeLabel(t: string): string {
  return PROPERTY_TYPES[t as PropertyType] ?? t;
}

export const VALUE_SOURCES: Record<string, string> = {
  purchase: "purchase price",
  valuation: "latest valuation",
  indexed: "indexed to market home values",
  sale: "sale price",
};

export function toneOf(v: number | null | undefined, good = 0): "up" | "down" | "flat" {
  if (v == null) return "flat";
  return v >= good ? "up" : "down";
}

export function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
