"use client";

import { useEffect, useState } from "react";

import { NumField } from "@/components/form/NumField";
import { api, type Lease, type RentRange } from "@/lib/api";
import { usd } from "@/lib/format";

const month = (iso: string) => iso.slice(0, 7);
const thisMonth = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

/** Record rent for a run of months (flat or from a lease) as one action, with a live preview. */
export function RentRangeForm({
  propertyId,
  purchaseDate,
  units,
  leases,
  presetLeaseId,
  onRecorded,
  onClose,
}: {
  propertyId: number;
  purchaseDate: string;
  units: number;
  leases: Lease[];
  presetLeaseId: number | null;
  onRecorded: (result: RentRange) => void;
  onClose: () => void;
}) {
  const lease = (id: number | null) => leases.find((l) => l.id === id) ?? null;
  const initial = lease(presetLeaseId);
  const [leaseId, setLeaseId] = useState<number | null>(initial?.id ?? null);
  const [from, setFrom] = useState(month(initial?.start_date ?? purchaseDate));
  const [to, setTo] = useState(initial?.end_date && month(initial.end_date) < thisMonth() ? month(initial.end_date) : thisMonth());
  const [amount, setAmount] = useState<number | null>(initial ? Number(initial.monthly_rent) : null);
  const [day, setDay] = useState<number | null>(1);
  const [increase, setIncrease] = useState<number | null>(0);
  // With one unit, any rent already in a month means that month is paid.
  const [skipPaid, setSkipPaid] = useState(units === 1);
  const [preview, setPreview] = useState<RentRange | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showLines, setShowLines] = useState(false);
  const [saving, setSaving] = useState(false);

  const pickLease = (id: number | null) => {
    setLeaseId(id);
    const l = lease(id);
    if (l) {
      setAmount(Number(l.monthly_rent));
      setFrom(month(l.start_date));
      setTo(l.end_date && month(l.end_date) < thisMonth() ? month(l.end_date) : thisMonth());
    }
  };

  const ready = /^\d{4}-\d{2}$/.test(from) && /^\d{4}-\d{2}$/.test(to) && (amount != null || leaseId != null);
  const body = {
    start_month: from,
    end_month: to,
    monthly_amount: amount,
    lease_id: leaseId,
    day_of_month: day ?? 1,
    annual_increase: increase ?? 0,
    category: "rent" as const,
    skip_months_with_rent: skipPaid,
  };
  const key = JSON.stringify(body);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      api
        .recordRentRange(propertyId, { ...JSON.parse(key), dry_run: true })
        .then((p) => {
          if (cancelled) return;
          setPreview(p);
          setError(null);
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          setPreview(null);
          setError(e instanceof Error ? e.message : String(e));
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [key, ready, propertyId]);

  const record = async () => {
    setSaving(true);
    try {
      onRecorded(await api.recordRentRange(propertyId, { ...body, dry_run: false }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const first = preview?.lines[0];
  const last = preview?.lines[preview.lines.length - 1];
  const shown = ready ? preview : null;

  return (
    <div className="rent-range">
      <div className="rent-range-title">
        <span>Record rent for a period</span>
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Close" onClick={onClose}>
          ✕
        </button>
      </div>
      <div className="row-form" style={{ borderBottom: 0 }}>
        <select
          className="select grow"
          aria-label="Rent source"
          value={leaseId ?? ""}
          onChange={(e) => pickLease(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Flat amount</option>
          {leases.map((l) => (
            <option key={l.id} value={l.id}>
              {["Lease", l.unit && `Unit ${l.unit}`, l.tenant].filter(Boolean).join(" · ")} ·{" "}
              {usd(l.monthly_rent)}/mo
            </option>
          ))}
        </select>
        <label className="inline-label">
          From
          <input type="month" className="text-input" aria-label="From month" placeholder="YYYY-MM" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="inline-label">
          To
          <input type="month" className="text-input" aria-label="To month" placeholder="YYYY-MM" value={to} max={thisMonth()} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      <div className="form-grid" style={{ paddingTop: 0 }}>
        <NumField label="Rent / month" kind="usd" optional={leaseId != null} placeholder="lease rent" value={amount} onChange={setAmount} />
        <NumField label="Increase each year" kind="pct" value={increase} onChange={setIncrease} title="Rent steps up every 12 months from the first month" />
        <NumField label="Day of month" kind="int" suffix="" value={day} onChange={setDay} />
        <label className="check">
          <input type="checkbox" checked={skipPaid} onChange={(e) => setSkipPaid(e.target.checked)} />
          Skip months that already have rent
        </label>
      </div>

      <div className="rent-range-preview num">
        {error ? (
          <span className="down">{error}</span>
        ) : shown && first && last ? (
          <>
            <span>
              <b>{shown.created}</b> of {shown.months} months · <b className="up">{usd(shown.total)}</b>
              {shown.skipped_month_has_rent > 0 && <span className="muted"> · {shown.skipped_month_has_rent} already have rent</span>}
              {shown.skipped_already_recorded > 0 && <span className="muted"> · {shown.skipped_already_recorded} recorded before</span>}
            </span>
            <span className="muted">
              {first.date} {usd(first.amount)} → {last.date} {usd(last.amount)}
            </span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowLines((v) => !v)}>
              {showLines ? "HIDE MONTHS" : "SHOW MONTHS"}
            </button>
          </>
        ) : (
          <span className="muted">Pick a range and an amount to preview.</span>
        )}
        <button
          type="button"
          className="btn btn-buy"
          style={{ marginLeft: "auto" }}
          disabled={!shown || shown.created === 0 || saving || Boolean(error)}
          onClick={() => void record()}
        >
          RECORD {shown?.created ?? ""} MONTHS
        </button>
      </div>

      {showLines && shown && (
        <div className="table-scroll tall">
          <table className="grid num">
            <thead>
              <tr>
                <th>Date</th>
                <th>Amount</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {shown.lines.map((ln) => (
                <tr key={ln.date} className={ln.status === "new" ? "" : "dim"}>
                  <td>{ln.date}</td>
                  <td>{usd(ln.amount)}</td>
                  <td>{ln.status === "new" ? "record" : ln.status === "month_has_rent" ? "skip · has rent" : "skip · recorded before"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
