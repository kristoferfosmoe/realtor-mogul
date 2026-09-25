"use client";

import { useId, useState } from "react";

export type FieldKind = "usd" | "pct" | "int" | "num";

interface Props {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  kind: FieldKind;
  /** Blank input means "not set" (null) instead of invalid. */
  optional?: boolean;
  placeholder?: string;
  title?: string;
  /** Unit shown after an int field; defaults to "yr". */
  suffix?: string;
}

const grouped = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

function display(value: number | null, kind: FieldKind): string {
  if (value == null) return "";
  if (kind === "pct") return String(Number((value * 100).toFixed(4)));
  return grouped.format(value);
}

function parse(text: string, kind: FieldKind): number | null | undefined {
  const cleaned = text.replace(/[$,%\s]/g, "");
  if (cleaned === "") return null;
  const n = Number(cleaned);
  if (!Number.isFinite(n)) return undefined;
  if (kind === "int" && !Number.isInteger(n)) return undefined;
  return kind === "pct" ? n / 100 : n;
}

/** Compact numeric input in the style of an order-ticket field. */
export function NumField({ label, value, onChange, kind, optional, placeholder, title, suffix = "yr" }: Props) {
  const id = useId();
  // While editing, the raw text is the source of truth; otherwise the value prop is.
  const [draft, setDraft] = useState<string | null>(null);
  const text = draft ?? display(value, kind);
  const parsed = parse(text, kind);
  const invalid = parsed === undefined || (parsed === null && !optional);

  return (
    <div className="field" title={title}>
      <label htmlFor={id}>{label}</label>
      <div className={`input-wrap${invalid ? " invalid" : ""}`}>
        {kind === "usd" && <span className="affix pre">$</span>}
        <input
          id={id}
          inputMode="decimal"
          value={text}
          placeholder={placeholder}
          onFocus={(e) => setDraft(e.target.value)}
          onBlur={() => setDraft(null)}
          onChange={(e) => {
            setDraft(e.target.value);
            const next = parse(e.target.value, kind);
            if (next !== undefined && (next !== null || optional)) onChange(next);
          }}
        />
        {kind === "pct" && <span className="affix post">%</span>}
        {kind === "int" && suffix && <span className="affix post">{suffix}</span>}
        {kind === "num" && suffix !== "yr" && suffix && <span className="affix post">{suffix}</span>}
      </div>
    </div>
  );
}
