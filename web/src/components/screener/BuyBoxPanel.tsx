"use client";

import { useState } from "react";

import { NumField } from "@/components/form/NumField";
import { useMarketData } from "@/components/MarketDataContext";
import { api, type Assumptions, type BuyBox, type Criteria, type PropertyType } from "@/lib/api";
import { pct } from "@/lib/format";
import { shortName } from "@/lib/markets";
import { PROPERTY_TYPES } from "@/lib/portfolio";

type Draft = { name: string; criteria: Required<Criteria>; assumptions: Required<Assumptions> };

const toDraft = (b: BuyBox): Draft => ({
  name: b.name,
  criteria: b.criteria as Required<Criteria>,
  assumptions: b.assumptions as Required<Assumptions>,
});

/** Edit a buy box: hard filters, return targets, and underwriting assumptions. */
export function BuyBoxPanel({
  box,
  onSaved,
  onDeleted,
  currentRate,
}: {
  box: BuyBox;
  onSaved: (b: BuyBox) => void;
  onDeleted: () => void;
  currentRate: number | null;
}) {
  const { markets } = useMarketData();
  const [draft, setDraft] = useState<Draft>(() => toDraft(box));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(toDraft(box));

  const c = draft.criteria;
  const a = draft.assumptions;
  const setC = <K extends keyof Criteria>(k: K, v: Criteria[K]) =>
    setDraft((d) => ({ ...d, criteria: { ...d.criteria, [k]: v } }));
  const setA = <K extends keyof Assumptions>(k: K, v: Assumptions[K]) =>
    setDraft((d) => ({ ...d, assumptions: { ...d.assumptions, [k]: v } }));
  const toggle = <T,>(list: T[], item: T) =>
    list.includes(item) ? list.filter((x) => x !== item) : [...list, item];

  const save = async () => {
    setSaving(true);
    try {
      onSaved(await api.updateBuyBox(box.id, draft));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <span>Buy box</span>
        <span className="section-actions">
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => {
              if (window.confirm(`Delete buy box "${box.name}"?`)) void api.deleteBuyBox(box.id).then(onDeleted);
            }}
          >
            DELETE
          </button>
        </span>
      </div>
      <div className="ticket-fields" style={{ paddingTop: 10 }}>
        <input
          className="text-input"
          aria-label="Buy box name"
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
      </div>

      <div className="ticket-section">
        <div className="ticket-section-title">Targets</div>
        <div className="ticket-fields">
          <NumField label="Min levered IRR" kind="pct" value={c.min_levered_irr} onChange={(v) => setC("min_levered_irr", v ?? 0)} />
          <NumField label="Min cash on cash" kind="pct" value={c.min_cash_on_cash} onChange={(v) => setC("min_cash_on_cash", v ?? 0)} />
          <NumField label="Min DSCR" kind="num" suffix="x" value={c.min_dscr} onChange={(v) => setC("min_dscr", v ?? 0)} />
          <NumField label="Min cap rate" kind="pct" optional placeholder="any" value={c.min_cap_rate ?? null} onChange={(v) => setC("min_cap_rate", v)} />
        </div>
      </div>

      <div className="ticket-section">
        <div className="ticket-section-title">Filters</div>
        <div className="ticket-fields">
          <NumField label="Min price" kind="usd" optional placeholder="any" value={c.min_price ?? null} onChange={(v) => setC("min_price", v)} />
          <NumField label="Max price" kind="usd" optional placeholder="any" value={c.max_price ?? null} onChange={(v) => setC("max_price", v)} />
          <NumField label="Min beds" kind="int" suffix="bd" optional placeholder="any" value={c.min_beds ?? null} onChange={(v) => setC("min_beds", v)} />
          <NumField label="Max days on market" kind="int" suffix="d" optional placeholder="any" value={c.max_days_on_market ?? null} onChange={(v) => setC("max_days_on_market", v)} />
          <NumField label="Built after" kind="int" suffix="" optional placeholder="any" value={c.min_year_built ?? null} onChange={(v) => setC("min_year_built", v)} />
          <div className="chips" role="group" aria-label="Property types">
            {Object.entries(PROPERTY_TYPES).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={`chip${c.property_types.includes(k as PropertyType) ? " on" : ""}`}
                onClick={() => setC("property_types", toggle(c.property_types, k as PropertyType))}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="stat-label" style={{ marginTop: 6 }}>
            Markets {c.market_ids.length === 0 && <span className="muted">· any</span>}
          </div>
          <div className="chips chip-scroll" role="group" aria-label="Markets">
            {markets
              .filter((m) => m.geography.kind !== "country")
              .map((m) => (
                <button
                  key={m.geography.id}
                  type="button"
                  className={`chip${c.market_ids.includes(m.geography.id) ? " on" : ""}`}
                  onClick={() => setC("market_ids", toggle(c.market_ids, m.geography.id))}
                >
                  {shortName(m.geography.name)}
                </button>
              ))}
          </div>
        </div>
      </div>

      <div className="ticket-section">
        <div className="ticket-section-title">Underwriting</div>
        <div className="ticket-fields">
          <NumField label="Down payment" kind="pct" value={a.down_payment_pct} onChange={(v) => setA("down_payment_pct", v ?? 0)} />
          <NumField
            label="Interest rate"
            kind="pct"
            optional
            placeholder={currentRate ? `auto ${pct(currentRate)}` : "auto"}
            value={a.interest_rate ?? null}
            onChange={(v) => setA("interest_rate", v)}
            title="Blank = current 30Y average + the investor spread"
          />
          <NumField label="Vacancy" kind="pct" value={a.vacancy_rate} onChange={(v) => setA("vacancy_rate", v ?? 0)} />
          <NumField label="Management" kind="pct" value={a.management_pct} onChange={(v) => setA("management_pct", v ?? 0)} />
          <NumField label="Maintenance" kind="pct" value={a.maintenance_pct} onChange={(v) => setA("maintenance_pct", v ?? 0)} />
          <NumField label="CapEx reserve" kind="pct" value={a.capex_reserve_pct} onChange={(v) => setA("capex_reserve_pct", v ?? 0)} />
          <NumField label="Property tax / price" kind="pct" value={a.property_tax_rate} onChange={(v) => setA("property_tax_rate", v ?? 0)} />
          <NumField label="Insurance / price" kind="pct" value={a.insurance_rate} onChange={(v) => setA("insurance_rate", v ?? 0)} />
          <NumField label="Make-ready / price" kind="pct" value={a.rehab_pct} onChange={(v) => setA("rehab_pct", v ?? 0)} />
          <NumField label="Hold period" kind="int" value={a.hold_years} onChange={(v) => setA("hold_years", v ?? 7)} />
          <div className="segmented" role="group" aria-label="Growth assumptions">
            <button type="button" className={a.growth === "market" ? "on" : ""} onClick={() => setA("growth", "market")}>
              MARKET GROWTH
            </button>
            <button type="button" className={a.growth === "fixed" ? "on" : ""} onClick={() => setA("growth", "fixed")}>
              FIXED
            </button>
          </div>
          {a.growth === "fixed" ? (
            <>
              <NumField label="Rent growth" kind="pct" value={a.rent_growth} onChange={(v) => setA("rent_growth", v ?? 0)} />
              <NumField label="Appreciation" kind="pct" value={a.appreciation} onChange={(v) => setA("appreciation", v ?? 0)} />
            </>
          ) : (
            <NumField label="Cap market growth at" kind="pct" value={a.growth_cap} onChange={(v) => setA("growth_cap", v ?? 0)} />
          )}
        </div>
      </div>

      <div className="ticket-actions">
        {error && <div className="down">{error}</div>}
        <button type="button" className="btn btn-buy" disabled={!dirty || saving || !draft.name.trim()} onClick={() => void save()}>
          {dirty ? "SAVE & RESCREEN" : "SAVED"}
        </button>
      </div>
    </section>
  );
}
