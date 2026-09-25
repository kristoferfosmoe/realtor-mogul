"use client";

import { useState } from "react";

import { useMarketData } from "@/components/MarketDataContext";
import type { Deal, DealStatus, Financing } from "@/lib/api";
import { pct } from "@/lib/format";
import { growthDefaults, shortName } from "@/lib/markets";

import { NumField } from "@/components/form/NumField";

export interface DealMeta {
  name: string;
  address: string;
  status: DealStatus;
}

interface Props {
  deal: Deal;
  onChange: (deal: Deal) => void;
  meta: DealMeta;
  onMetaChange: (meta: DealMeta) => void;
  savedId: number | null;
  saving: boolean;
  dirty: boolean;
  onSave: () => void;
  onSaveAsNew: () => void;
  onNew: () => void;
}

const DEFAULT_FINANCING: Financing = {
  down_payment_pct: 0.25,
  interest_rate: 0.07,
  amortization_years: 30,
  points_pct: 0,
};

const STATUSES: DealStatus[] = ["watching", "offer", "owned", "passed"];

/** Left-hand "order ticket": every underwriting assumption for the open deal. */
export function DealTicket(props: Props) {
  const { deal, onChange, meta, onMetaChange } = props;
  const { markets, indicators } = useMarketData();
  const [growthFrom, setGrowthFrom] = useState<string | null>(null);
  const mortgage = indicators.find((i) => i.metric === "mortgage_rate_30y")?.stats?.latest;

  const applyMarket = (id: string) => {
    const m = markets.find((x) => String(x.geography.id) === id);
    if (!m) return;
    const g = growthDefaults(m);
    onChange({
      ...deal,
      rent_growth: g.rent_growth ?? deal.rent_growth,
      appreciation: g.appreciation ?? deal.appreciation,
    });
    setGrowthFrom(shortName(m.geography.name));
  };
  const set = <K extends keyof Deal>(key: K) => (v: Deal[K]) => onChange({ ...deal, [key]: v });
  const req = <K extends keyof Deal>(key: K) => (v: number | null) =>
    onChange({ ...deal, [key]: v ?? 0 });
  const setFin = <K extends keyof Financing>(key: K) => (v: number | null) =>
    deal.financing && onChange({ ...deal, financing: { ...deal.financing, [key]: v ?? 0 } });

  return (
    <section className="panel">
      <div className="panel-head">
        <span>Deal Ticket</span>
        {props.savedId != null && <span className="badge neutral">#{props.savedId}</span>}
      </div>

      <div className="ticket-section">
        <div className="ticket-fields" style={{ paddingTop: 10 }}>
          <input
            className="text-input"
            placeholder="Deal name"
            aria-label="Deal name"
            value={meta.name}
            onChange={(e) => onMetaChange({ ...meta, name: e.target.value })}
          />
          <input
            className="text-input"
            placeholder="Address"
            aria-label="Address"
            value={meta.address}
            onChange={(e) => onMetaChange({ ...meta, address: e.target.value })}
          />
        </div>
      </div>

      <Section title="Acquisition">
        <NumField label="Purchase price" kind="usd" value={deal.purchase_price} onChange={req("purchase_price")} />
        <NumField label="Closing costs" kind="pct" value={deal.closing_costs_pct} onChange={req("closing_costs_pct")} />
        <NumField label="Rehab budget" kind="usd" value={deal.rehab_cost} onChange={req("rehab_cost")} />
        <NumField
          label="After-repair value"
          kind="usd"
          optional
          placeholder="= price"
          value={deal.after_repair_value}
          onChange={set("after_repair_value")}
        />
      </Section>

      <Section title="Income · monthly">
        <NumField label="Rent (all units)" kind="usd" value={deal.monthly_rent} onChange={req("monthly_rent")} />
        <NumField label="Other income" kind="usd" value={deal.other_income_monthly} onChange={req("other_income_monthly")} />
        <NumField label="Vacancy" kind="pct" value={deal.vacancy_rate} onChange={req("vacancy_rate")} />
      </Section>

      <Section title="Expenses">
        <NumField label="Property tax / yr" kind="usd" value={deal.property_tax_annual} onChange={req("property_tax_annual")} />
        <NumField label="Insurance / yr" kind="usd" value={deal.insurance_annual} onChange={req("insurance_annual")} />
        <NumField label="HOA / mo" kind="usd" value={deal.hoa_monthly} onChange={req("hoa_monthly")} />
        <NumField label="Utilities / mo" kind="usd" value={deal.utilities_monthly} onChange={req("utilities_monthly")} />
        <NumField label="Other / yr" kind="usd" value={deal.other_expenses_annual} onChange={req("other_expenses_annual")} />
        <NumField label="Management" kind="pct" value={deal.management_pct} onChange={req("management_pct")} title="Share of collected income" />
        <NumField label="Maintenance" kind="pct" value={deal.maintenance_pct} onChange={req("maintenance_pct")} title="Share of collected income" />
        <NumField label="CapEx reserve" kind="pct" value={deal.capex_reserve_pct} onChange={req("capex_reserve_pct")} title="Share of collected income" />
      </Section>

      <Section title="Financing">
        <div className="segmented" role="group" aria-label="Financing">
          <button
            type="button"
            className={deal.financing ? "on" : ""}
            onClick={() => onChange({ ...deal, financing: deal.financing ?? DEFAULT_FINANCING })}
          >
            MORTGAGE
          </button>
          <button
            type="button"
            className={deal.financing ? "" : "on"}
            onClick={() => onChange({ ...deal, financing: null })}
          >
            ALL CASH
          </button>
        </div>
        {deal.financing && (
          <>
            <NumField label="Down payment" kind="pct" value={deal.financing.down_payment_pct} onChange={setFin("down_payment_pct")} />
            <NumField label="Interest rate" kind="pct" value={deal.financing.interest_rate} onChange={setFin("interest_rate")} />
            {mortgage != null && Math.abs(mortgage - deal.financing.interest_rate) > 1e-6 && (
              <button type="button" className="hint-btn" onClick={() => setFin("interest_rate")(mortgage)}>
                Use current 30Y avg {pct(mortgage)}
              </button>
            )}
            <NumField label="Amortization" kind="int" value={deal.financing.amortization_years} onChange={setFin("amortization_years")} />
            <NumField label="Points" kind="pct" value={deal.financing.points_pct} onChange={setFin("points_pct")} />
          </>
        )}
      </Section>

      <Section title="Growth & Exit">
        {markets.length > 0 && (
          <select
            className="select"
            aria-label="Apply market growth"
            value=""
            onChange={(e) => applyMarket(e.target.value)}
          >
            <option value="">Apply market growth (5Y CAGR)…</option>
            {markets.map((m) => (
              <option key={m.geography.id} value={m.geography.id}>
                {shortName(m.geography.name)} · rent {pct(growthDefaults(m).rent_growth, 1)} · value{" "}
                {pct(growthDefaults(m).appreciation, 1)}
              </option>
            ))}
          </select>
        )}
        {growthFrom && <div className="hint">Growth from {growthFrom}</div>}
        <NumField label="Rent growth / yr" kind="pct" value={deal.rent_growth} onChange={req("rent_growth")} />
        <NumField label="Expense growth / yr" kind="pct" value={deal.expense_growth} onChange={req("expense_growth")} />
        <NumField label="Appreciation / yr" kind="pct" value={deal.appreciation} onChange={req("appreciation")} />
        <NumField label="Hold period" kind="int" value={deal.hold_years} onChange={req("hold_years")} />
        <NumField label="Selling costs" kind="pct" value={deal.selling_costs_pct} onChange={req("selling_costs_pct")} />
        <NumField
          label="Exit cap rate"
          kind="pct"
          optional
          placeholder="use appr."
          value={deal.exit_cap_rate}
          onChange={set("exit_cap_rate")}
          title="If set, sale price = next year's NOI ÷ exit cap rate"
        />
      </Section>

      <div className="ticket-actions">
        <div className="field">
          <label htmlFor="deal-status">Status</label>
          <select
            id="deal-status"
            className="select"
            value={meta.status}
            onChange={(e) => onMetaChange({ ...meta, status: e.target.value as DealStatus })}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="btn btn-buy"
          disabled={props.saving || !meta.name.trim() || (props.savedId != null && !props.dirty)}
          onClick={props.onSave}
        >
          {props.savedId == null ? "ADD TO WATCHLIST" : props.dirty ? "SAVE CHANGES" : "SAVED"}
        </button>
        <div className="row">
          {props.savedId != null && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={props.saving || !meta.name.trim()}
              onClick={props.onSaveAsNew}
            >
              SAVE AS NEW
            </button>
          )}
          <button type="button" className="btn btn-ghost btn-sm" onClick={props.onNew}>
            NEW DEAL
          </button>
        </div>
      </div>
    </section>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="ticket-section">
      <div className="ticket-section-title">{title}</div>
      <div className="ticket-fields">{children}</div>
    </div>
  );
}
