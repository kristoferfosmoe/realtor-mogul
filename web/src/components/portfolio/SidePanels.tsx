"use client";

import { useState } from "react";

import { api, type Lease, type PropertyDetail } from "@/lib/api";
import { pct, usd } from "@/lib/format";
import { todayIso } from "@/lib/portfolio";

type Props = { detail: PropertyDetail; onChange: () => void };

function useAction(onChange: () => void) {
  const [error, setError] = useState<string | null>(null);
  const run = (p: Promise<unknown>) =>
    p.then(
      () => {
        setError(null);
        onChange();
      },
      (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
    );
  return { error, run };
}

export function RentRoll({ detail, onChange }: Props) {
  const { error, run } = useAction(onChange);
  const [draft, setDraft] = useState({ unit: "", tenant: "", start: todayIso(), end: "", rent: "" });
  const p = detail.performance;
  const pid = detail.property.id;

  const endToday = (l: Lease) =>
    run(
      api.updateLease(l.id, {
        unit: l.unit,
        tenant: l.tenant,
        start_date: l.start_date,
        end_date: todayIso(),
        monthly_rent: l.monthly_rent,
        deposit: l.deposit,
      }),
    );

  return (
    <section className="panel">
      <div className="panel-head">
        <span>Rent roll</span>
        <span className="muted num">
          {p.occupied_units}/{p.units} occupied · {usd(p.scheduled_rent)}/mo
        </span>
      </div>
      <div className="table-scroll">
        <table className="grid num">
          <thead>
            <tr>
              <th>Unit</th>
              <th style={{ textAlign: "left" }}>Tenant · term</th>
              <th>Rent</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {detail.leases.map((l) => (
              <tr key={l.id} className={l.active ? "" : "dim"}>
                <td>{l.unit || "—"}</td>
                <td style={{ textAlign: "left" }}>
                  <div style={{ fontFamily: "var(--font-sans)" }}>{l.tenant || "—"}</div>
                  <div className="muted" style={{ fontSize: 10 }}>
                    {l.start_date} → {l.end_date ?? "open"}
                  </div>
                </td>
                <td className={l.active ? "up" : ""}>{usd(l.monthly_rent)}</td>
                <td>
                  {l.active && (
                    <button type="button" className="btn btn-ghost btn-sm" title="End lease today" onClick={() => void endToday(l)}>
                      END
                    </button>
                  )}
                  <button type="button" className="btn btn-ghost btn-sm" aria-label="Delete lease" onClick={() => void run(api.deleteLease(l.id))}>
                    ✕
                  </button>
                </td>
              </tr>
            ))}
            {detail.leases.length === 0 && (
              <tr>
                <td colSpan={4} className="muted" style={{ textAlign: "center" }}>
                  No leases
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="row-form" style={{ borderBottom: 0 }}>
        <input className="text-input" placeholder="Unit" aria-label="Lease unit" value={draft.unit} onChange={(e) => setDraft({ ...draft, unit: e.target.value })} />
        <input className="text-input grow" placeholder="Tenant" aria-label="Lease tenant" value={draft.tenant} onChange={(e) => setDraft({ ...draft, tenant: e.target.value })} />
        <input className="text-input num" placeholder="Rent/mo" inputMode="decimal" aria-label="Lease rent" value={draft.rent} onChange={(e) => setDraft({ ...draft, rent: e.target.value.replace(/[^0-9.]/g, "") })} />
        <input type="date" className="text-input" aria-label="Lease start" title="Lease start" value={draft.start} onChange={(e) => setDraft({ ...draft, start: e.target.value })} />
        <input type="date" className="text-input" aria-label="Lease end" title="Lease end (blank = open-ended)" value={draft.end} onChange={(e) => setDraft({ ...draft, end: e.target.value })} />
        <button
          type="button"
          className="btn"
          disabled={!Number(draft.rent) || !draft.start}
          onClick={() =>
            void run(
              api.addLease(pid, {
                unit: draft.unit,
                tenant: draft.tenant || null,
                start_date: draft.start,
                end_date: draft.end || null,
                monthly_rent: Number(draft.rent),
                deposit: 0,
              }),
            ).then(() => setDraft({ ...draft, unit: "", tenant: "", rent: "" }))
          }
        >
          ADD
        </button>
      </div>
      {error && <div className="panel-body down">{error}</div>}
    </section>
  );
}

export function LoanPanel({ detail }: { detail: PropertyDetail }) {
  const loan = detail.property.loan;
  const p = detail.performance;
  return (
    <section className="panel">
      <div className="panel-head">
        <span>Loan</span>
        {loan?.lender && <span className="muted">{loan.lender}</span>}
      </div>
      <div className="panel-body num">
        {loan ? (
          <>
            <Row label="Original amount" value={usd(loan.original_amount)} />
            <Row label="Rate · term" value={`${pct(loan.interest_rate, 3)} · ${loan.amortization_years}y`} />
            <Row label="Payment (P&I)" value={`${usd(loan.monthly_payment)}/mo`} />
            <Row label="Current balance" value={usd(p.loan_balance)} />
            <Row label="Principal paid" value={usd(loan.original_amount - p.loan_balance)} tone="up" />
            <Row label="LTV" value={pct(p.ltv, 1)} />
          </>
        ) : (
          <div className="muted">All cash — no loan.</div>
        )}
      </div>
    </section>
  );
}

export function Valuations({ detail, onChange }: Props) {
  const { error, run } = useAction(onChange);
  const [draft, setDraft] = useState({ date: todayIso(), value: "", note: "" });
  return (
    <section className="panel">
      <div className="panel-head">
        <span>Valuations</span>
        <span className="muted">appraisals, BPOs, estimates</span>
      </div>
      <div className="panel-body num">
        <Row label={`Purchase · ${detail.property.purchase_date}`} value={usd(detail.property.purchase_price)} />
        {detail.valuations.map((v) => (
          <div key={v.id} className="info-row">
            <span className="muted" style={{ fontFamily: "var(--font-sans)" }}>
              {v.date} {v.note && `· ${v.note}`}
            </span>
            <span>
              {usd(v.value)}{" "}
              <button type="button" className="btn btn-ghost btn-sm" aria-label="Delete valuation" onClick={() => void run(api.deleteValuation(v.id))}>
                ✕
              </button>
            </span>
          </div>
        ))}
      </div>
      <div className="row-form" style={{ borderBottom: 0, borderTop: "1px solid var(--border)" }}>
        <input type="date" className="text-input" aria-label="Valuation date" value={draft.date} onChange={(e) => setDraft({ ...draft, date: e.target.value })} />
        <input className="text-input num" placeholder="Value" inputMode="decimal" aria-label="Valuation amount" value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value.replace(/[^0-9.]/g, "") })} />
        <input className="text-input" placeholder="Note" aria-label="Valuation note" value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
        <button
          type="button"
          className="btn"
          disabled={!Number(draft.value)}
          onClick={() =>
            void run(
              api.addValuation(detail.property.id, {
                date: draft.date,
                value: Number(draft.value),
                note: draft.note || null,
              }),
            ).then(() => setDraft({ ...draft, value: "", note: "" }))
          }
        >
          ADD
        </button>
      </div>
      {error && <div className="panel-body down">{error}</div>}
    </section>
  );
}

export function ProFormaPanel({ detail }: { detail: PropertyDetail }) {
  const cmp = detail.pro_forma;
  if (!cmp) {
    return (
      <section className="panel">
        <div className="panel-head">
          <span>Actual vs projected</span>
        </div>
        <div className="panel-body muted">
          Link the watchlist deal you underwrote (Edit → Projection) to track how this property is
          doing against plan.
        </div>
      </section>
    );
  }
  return (
    <section className="panel">
      <div className="panel-head">
        <span>Actual vs projected · year {cmp.projection_year}</span>
        <span className="muted">{cmp.deal_name} · T12 annualized</span>
      </div>
      <div className="table-scroll">
        <table className="grid num">
          <thead>
            <tr>
              <th>Line</th>
              <th>Projected</th>
              <th>Actual</th>
              <th>Variance</th>
              <th>%</th>
            </tr>
          </thead>
          <tbody>
            {cmp.rows.map((r) => {
              const good = r.variance == null ? null : (r.variance >= 0) === r.higher_is_better;
              const cls = good == null || Math.abs(r.variance ?? 0) < 0.5 ? "" : good ? "up" : "down";
              return (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td>{usd(r.projected)}</td>
                  <td>{usd(r.actual)}</td>
                  <td className={cls}>
                    {r.variance == null ? "—" : `${r.variance >= 0 ? "+" : "−"}${usd(Math.abs(r.variance))}`}
                  </td>
                  <td className={cls}>{r.variance_pct == null ? "—" : pct(r.variance_pct, 1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="info-row">
      <span className="muted" style={{ fontFamily: "var(--font-sans)" }}>
        {label}
      </span>
      <span className={tone}>{value}</span>
    </div>
  );
}
