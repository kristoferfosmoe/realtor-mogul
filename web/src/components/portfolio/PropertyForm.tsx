"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { NumField } from "@/components/form/NumField";
import { useMarketData } from "@/components/MarketDataContext";
import { useWatchlist } from "@/components/WatchlistContext";
import { api, type LoanIn, type PropertyIn, type PropertyOut, type PropertyType } from "@/lib/api";
import { shortName } from "@/lib/markets";
import { PROPERTY_TYPES, todayIso } from "@/lib/portfolio";

type Form = Omit<PropertyIn, "loan"> & { loan: LoanIn | null };

const num = (v: number | string | null | undefined): number | null =>
  v == null || v === "" ? null : Number(v);

function initialForm(p?: PropertyOut): Form {
  if (!p) {
    return {
      name: "",
      address: "",
      property_type: "single_family",
      units: 1,
      market_id: null,
      deal_id: null,
      purchase_date: todayIso(),
      purchase_price: 0,
      closing_costs: 0,
      rehab_cost: 0,
      sale_date: null,
      sale_price: null,
      selling_costs: null,
      notes: "",
      loan: null,
    };
  }
  const loan = p.loan;
  return {
    name: p.name,
    address: p.address,
    property_type: p.property_type,
    units: p.units,
    market_id: p.market_id,
    deal_id: p.deal_id,
    purchase_date: p.purchase_date,
    purchase_price: p.purchase_price,
    closing_costs: p.closing_costs,
    rehab_cost: p.rehab_cost,
    sale_date: p.sale_date,
    sale_price: p.sale_price,
    selling_costs: p.selling_costs,
    notes: p.notes,
    loan: loan
      ? {
          lender: loan.lender,
          original_amount: loan.original_amount,
          interest_rate: loan.interest_rate,
          amortization_years: loan.amortization_years,
          start_date: loan.start_date,
        }
      : null,
  };
}

/** Create or edit an owned property, including its loan and (if sold) the sale. */
export function PropertyForm({ existing }: { existing?: PropertyOut }) {
  const router = useRouter();
  const { markets } = useMarketData();
  const { deals, refresh: refreshDeals } = useWatchlist();
  const [form, setForm] = useState<Form>(() => initialForm(existing));
  const [sold, setSold] = useState(Boolean(existing?.sale_date));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [fromDeal, setFromDeal] = useState<{ id: string; date: string }>({ id: "", date: todayIso() });

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  const setLoan = <K extends keyof LoanIn>(key: K, value: LoanIn[K]) =>
    setForm((f) => (f.loan ? { ...f, loan: { ...f.loan, [key]: value } } : f));

  const save = async () => {
    setSaving(true);
    setError(null);
    const body: PropertyIn = {
      ...form,
      address: form.address || null,
      notes: form.notes || null,
      sale_date: sold ? form.sale_date : null,
      sale_price: sold ? form.sale_price : null,
      selling_costs: sold ? form.selling_costs : null,
    };
    try {
      const saved = existing
        ? await api.updateProperty(existing.id, body)
        : await api.createProperty(body);
      router.push(`/portfolio/${saved.property.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  const convert = async () => {
    setSaving(true);
    try {
      const created = await api.createFromDeal(Number(fromDeal.id), fromDeal.date);
      await refreshDeals();
      router.push(`/portfolio/${created.property.id}/edit`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  return (
    <main className="page">
      {!existing && deals.length > 0 && (
        <section className="panel">
          <div className="panel-head">
            <span>From watchlist</span>
            <span className="muted">copies price, costs and loan; keeps the projection for comparison</span>
          </div>
          <div className="row-form">
            <select
              className="select grow"
              aria-label="Watchlist deal"
              value={fromDeal.id}
              onChange={(e) => setFromDeal({ ...fromDeal, id: e.target.value })}
            >
              <option value="">Choose a deal you bought…</option>
              {deals.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} · ${d.inputs.purchase_price.toLocaleString()}
                </option>
              ))}
            </select>
            <input
              type="date"
              className="text-input"
              aria-label="Closing date"
              value={fromDeal.date}
              onChange={(e) => setFromDeal({ ...fromDeal, date: e.target.value })}
            />
            <button
              type="button"
              className="btn btn-buy"
              disabled={!fromDeal.id || !fromDeal.date || saving}
              onClick={() => void convert()}
            >
              ADD FROM DEAL
            </button>
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-head">
          <span>{existing ? `Edit · ${existing.name}` : "New property"}</span>
        </div>
        <div className="form-grid">
          <TextField label="Name" value={form.name} onChange={(v) => set("name", v)} />
          <TextField label="Address" value={form.address ?? ""} onChange={(v) => set("address", v)} />
          <div className="field">
            <label htmlFor="ptype">Type</label>
            <select
              id="ptype"
              className="select"
              value={form.property_type ?? "single_family"}
              onChange={(e) => set("property_type", e.target.value as PropertyType)}
            >
              {Object.entries(PROPERTY_TYPES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <NumField label="Units" kind="int" suffix="" value={form.units ?? 1} onChange={(v) => set("units", v ?? 1)} />
          <div className="field">
            <label htmlFor="pmarket">Market</label>
            <select
              id="pmarket"
              className="select"
              value={form.market_id ?? ""}
              onChange={(e) => set("market_id", e.target.value ? Number(e.target.value) : null)}
              title="Used to carry the value forward with the market's home-value index"
            >
              <option value="">National index</option>
              {markets
                .filter((m) => m.geography.kind !== "country")
                .map((m) => (
                  <option key={m.geography.id} value={m.geography.id}>
                    {shortName(m.geography.name)}
                  </option>
                ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="pdeal">Projection</label>
            <select
              id="pdeal"
              className="select"
              value={form.deal_id ?? ""}
              onChange={(e) => set("deal_id", e.target.value ? Number(e.target.value) : null)}
              title="The watchlist deal this purchase was underwritten with"
            >
              <option value="">None</option>
              {deals.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
          <DateField label="Purchase date" value={form.purchase_date} onChange={(v) => set("purchase_date", v)} />
          <NumField label="Purchase price" kind="usd" value={num(form.purchase_price)} onChange={(v) => set("purchase_price", v ?? 0)} />
          <NumField label="Closing costs" kind="usd" value={num(form.closing_costs)} onChange={(v) => set("closing_costs", v ?? 0)} />
          <NumField label="Rehab / improvements" kind="usd" value={num(form.rehab_cost)} onChange={(v) => set("rehab_cost", v ?? 0)} />
        </div>

        <div className="ticket-section">
          <div className="ticket-section-title">Financing</div>
          <div className="row-form" style={{ borderBottom: 0 }}>
            <div className="segmented" style={{ maxWidth: 260 }}>
              <button
                type="button"
                className={form.loan ? "on" : ""}
                onClick={() =>
                  set(
                    "loan",
                    form.loan ?? {
                      lender: null,
                      original_amount: Math.round(Number(form.purchase_price) * 0.75),
                      interest_rate: 0.07,
                      amortization_years: 30,
                      start_date: form.purchase_date,
                    },
                  )
                }
              >
                MORTGAGE
              </button>
              <button type="button" className={form.loan ? "" : "on"} onClick={() => set("loan", null)}>
                ALL CASH
              </button>
            </div>
          </div>
          {form.loan && (
            <div className="form-grid">
              <TextField label="Lender" value={form.loan.lender ?? ""} onChange={(v) => setLoan("lender", v || null)} />
              <NumField label="Loan amount" kind="usd" value={num(form.loan.original_amount)} onChange={(v) => setLoan("original_amount", v ?? 0)} />
              <NumField label="Interest rate" kind="pct" value={form.loan.interest_rate} onChange={(v) => setLoan("interest_rate", v ?? 0)} />
              <NumField label="Amortization" kind="int" value={form.loan.amortization_years} onChange={(v) => setLoan("amortization_years", v ?? 30)} />
              <DateField label="Loan start" value={form.loan.start_date} onChange={(v) => setLoan("start_date", v)} />
            </div>
          )}
        </div>

        <div className="ticket-section">
          <div className="ticket-section-title">Disposition</div>
          <div className="row-form" style={{ borderBottom: 0 }}>
            <div className="segmented" style={{ maxWidth: 260 }}>
              <button type="button" className={sold ? "" : "on"} onClick={() => setSold(false)}>
                HOLDING
              </button>
              <button type="button" className={sold ? "on" : ""} onClick={() => setSold(true)}>
                SOLD
              </button>
            </div>
          </div>
          {sold && (
            <div className="form-grid">
              <DateField label="Sale date" value={form.sale_date ?? ""} onChange={(v) => set("sale_date", v || null)} />
              <NumField label="Sale price" kind="usd" value={num(form.sale_price)} onChange={(v) => set("sale_price", v)} />
              <NumField label="Selling costs" kind="usd" optional value={num(form.selling_costs)} onChange={(v) => set("selling_costs", v)} />
            </div>
          )}
        </div>

        <div className="ticket-section">
          <div className="ticket-fields" style={{ paddingTop: 10 }}>
            <textarea
              className="text-input"
              style={{ height: 60, fontFamily: "var(--font-sans)", fontSize: 12 }}
              placeholder="Notes"
              aria-label="Notes"
              value={form.notes ?? ""}
              onChange={(e) => set("notes", e.target.value)}
            />
          </div>
        </div>

        <div className="ticket-actions">
          {error && <div className="down">{error}</div>}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <Link href={existing ? `/portfolio/${existing.id}` : "/portfolio"} className="btn btn-ghost" style={{ flex: "0 0 auto" }}>
              CANCEL
            </Link>
            <button
              type="button"
              className="btn btn-buy"
              style={{ flex: "0 0 auto" }}
              disabled={saving || !form.name.trim() || !Number(form.purchase_price) || (sold && !form.sale_date)}
              onClick={() => void save()}
            >
              {existing ? "SAVE" : "ADD PROPERTY"}
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="field">
      <label>{label}</label>
      <input className="text-input" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="field">
      <label>{label}</label>
      <input type="date" className="text-input" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
