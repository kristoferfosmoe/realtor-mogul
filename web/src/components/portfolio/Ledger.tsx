"use client";

import { useEffect, useMemo, useState } from "react";

import { api, type Category, type Transaction, type TransactionIn } from "@/lib/api";
import { usd } from "@/lib/format";
import { todayIso } from "@/lib/portfolio";

const OUTFLOW_GROUPS = new Set(["operating_expense", "capital_expense", "debt_service"]);

/** Property ledger: add lines, import a bank CSV, recategorize, delete. */
export function Ledger({ propertyId, onChange }: { propertyId: number; onChange: () => void }) {
  const [rows, setRows] = useState<Transaction[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [draft, setDraft] = useState({ date: todayIso(), category: "rent", amount: "", description: "" });
  const [csv, setCsv] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [onlyUncategorized, setOnlyUncategorized] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    api.categories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .transactions(propertyId)
      .then((r) => !cancelled && setRows(r))
      .catch((e: unknown) => !cancelled && setMessage({ text: String(e), error: true }));
    return () => {
      cancelled = true;
    };
  }, [propertyId, version]);

  const changed = () => {
    setVersion((v) => v + 1);
    onChange();
  };
  const fail = (e: unknown) => setMessage({ text: e instanceof Error ? e.message : String(e), error: true });
  const groupOf = (id: string) => categories.find((c) => c.id === id)?.group ?? "";

  const add = async () => {
    const magnitude = Math.abs(Number(draft.amount));
    if (!magnitude) return;
    // Enter amounts as positive numbers; expenses are stored as money out.
    const amount = OUTFLOW_GROUPS.has(groupOf(draft.category)) ? -magnitude : magnitude;
    try {
      await api.addTransaction(propertyId, {
        date: draft.date,
        category: draft.category as TransactionIn["category"],
        amount,
        description: draft.description,
      });
      setDraft({ ...draft, amount: "", description: "" });
      setMessage(null);
      changed();
    } catch (e) {
      fail(e);
    }
  };

  const runImport = async (text: string) => {
    try {
      const r = await api.importTransactions(propertyId, text);
      setMessage({
        text: `Imported ${r.imported} (${r.guessed} auto-categorized, ${r.uncategorized} need a category); skipped ${r.skipped_duplicates} already imported.`,
      });
      setCsv(null);
      if (r.uncategorized) setOnlyUncategorized(true);
      changed();
    } catch (e) {
      fail(e);
    }
  };

  const shown = useMemo(
    () => (rows ?? []).filter((r) => !onlyUncategorized || r.category === "uncategorized"),
    [rows, onlyUncategorized],
  );
  const uncategorized = (rows ?? []).filter((r) => r.category === "uncategorized").length;

  return (
    <section className="panel">
      <div className="panel-head">
        <span>Ledger · {rows?.length ?? 0} lines</span>
        <span className="section-actions">
          {uncategorized > 0 && (
            <button
              type="button"
              className={`btn btn-sm ${onlyUncategorized ? "" : "btn-ghost"}`}
              onClick={() => setOnlyUncategorized((v) => !v)}
            >
              {uncategorized} UNCATEGORIZED
            </button>
          )}
          <label className="btn btn-sm btn-ghost">
            IMPORT CSV
            <input
              type="file"
              accept=".csv,text/csv"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void file.text().then(runImport);
                e.target.value = "";
              }}
            />
          </label>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => setCsv(csv == null ? "" : null)}>
            PASTE
          </button>
        </span>
      </div>

      {csv != null && (
        <div className="row-form">
          <textarea
            className="text-input grow"
            aria-label="CSV to import"
            placeholder={"Date,Description,Amount\n01/03/2025,Rent - Unit A,1850.00\n01/05/2025,MORTGAGE PMT,-1612.40"}
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
          />
          <button type="button" className="btn btn-buy" disabled={!csv.trim()} onClick={() => void runImport(csv)}>
            IMPORT
          </button>
        </div>
      )}

      <div className="row-form">
        <input
          type="date"
          className="text-input"
          aria-label="Transaction date"
          value={draft.date}
          onChange={(e) => setDraft({ ...draft, date: e.target.value })}
        />
        <select
          className="select"
          aria-label="Transaction category"
          value={draft.category}
          onChange={(e) => setDraft({ ...draft, category: e.target.value })}
        >
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
        <input
          className="text-input num"
          inputMode="decimal"
          placeholder="Amount"
          aria-label="Transaction amount"
          value={draft.amount}
          onChange={(e) => setDraft({ ...draft, amount: e.target.value.replace(/[^0-9.]/g, "") })}
        />
        <input
          className="text-input grow"
          placeholder="Description"
          aria-label="Transaction description"
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          onKeyDown={(e) => e.key === "Enter" && void add()}
        />
        <button type="button" className="btn" disabled={!Number(draft.amount)} onClick={() => void add()}>
          ADD
        </button>
      </div>

      {message && (
        <div className={`panel-body ${message.error ? "down" : "muted"}`} style={{ paddingBottom: 0 }}>
          {message.text}
        </div>
      )}

      {rows && rows.length === 0 ? (
        <div className="empty">
          No transactions yet. Add rent and expenses above, or import a CSV export from your bank or
          property manager.
        </div>
      ) : (
        <div className="table-scroll tall">
          <table className="grid num">
            <thead>
              <tr>
                <th>Date</th>
                <th style={{ textAlign: "left" }}>Description</th>
                <th style={{ textAlign: "left" }}>Category</th>
                <th>Amount</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((t) => (
                <tr key={t.id}>
                  <td>{t.date}</td>
                  <td style={{ textAlign: "left", fontFamily: "var(--font-sans)", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {t.description || <span className="muted">—</span>}
                  </td>
                  <td style={{ textAlign: "left" }}>
                    <select
                      className={`inline-select${t.category === "uncategorized" ? " flagged" : ""}`}
                      aria-label={`Category for ${t.description || t.date}`}
                      value={t.category}
                      onChange={(e) =>
                        void api
                          .patchTransaction(t.id, { category: e.target.value as TransactionIn["category"] })
                          .then(changed, fail)
                      }
                    >
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className={t.amount >= 0 ? "up" : "down"}>{usd(t.amount)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      aria-label="Delete transaction"
                      onClick={() => void api.deleteTransaction(t.id).then(changed, fail)}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
