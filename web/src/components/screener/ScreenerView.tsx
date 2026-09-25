"use client";

import { useCallback, useEffect, useState } from "react";

import { api, type BuyBox, type ListingSources, type Recommendations } from "@/lib/api";
import { pct } from "@/lib/format";

import { BuyBoxPanel } from "./BuyBoxPanel";
import { ListingPanel } from "./ListingPanel";
import { ResultsTable } from "./ResultsTable";

export function ScreenerView() {
  const [boxes, setBoxes] = useState<BuyBox[] | null>(null);
  const [boxId, setBoxId] = useState<number | null>(null);
  const [recs, setRecs] = useState<Recommendations | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [sources, setSources] = useState<ListingSources | null>(null);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [version, setVersion] = useState(0);

  const fail = (e: unknown) => setMessage({ text: e instanceof Error ? e.message : String(e), error: true });

  useEffect(() => {
    api
      .buyBoxes()
      .then((b) => {
        setBoxes(b);
        setBoxId((cur) => cur ?? b[0]?.id ?? null);
      })
      .catch(fail);
    api.listingSources().then(setSources).catch(() => undefined);
  }, [version]);

  useEffect(() => {
    if (boxId == null) return;
    let cancelled = false;
    api
      .recommendations(boxId)
      .then((r) => {
        if (cancelled) return;
        setRecs(r);
        setSelected((cur) => (r.rows.some((x) => x.listing.id === cur) ? cur : (r.rows[0]?.listing.id ?? null)));
        // Viewing clears the NEW alert count (rows keep their NEW badge for this visit).
        void api.markSeen(boxId).then(() => window.dispatchEvent(new Event("screener-seen")));
      })
      .catch((e: unknown) => !cancelled && fail(e));
    return () => {
      cancelled = true;
    };
  }, [boxId, version]);

  const rescreen = useCallback(() => setVersion((v) => v + 1), []);

  const importCsv = async (text: string) => {
    try {
      const r = await api.importListings(text);
      setMessage({ text: `${r.source.toUpperCase()}: ${r.new} new, ${r.updated} updated, ${r.price_changes} price changes.` });
      rescreen();
    } catch (e) {
      fail(e);
    }
  };

  const newBox = async () => {
    const name = window.prompt("Name for the new buy box", "New buy box");
    if (!name) return;
    try {
      // A new box starts as a copy of the one on screen.
      const current = boxes?.find((x) => x.id === boxId);
      const b = await api.createBuyBox(
        current ? { name, criteria: current.criteria, assumptions: current.assumptions } : { name },
      );
      setBoxId(b.id);
      rescreen();
    } catch (e) {
      fail(e);
    }
  };

  if (!boxes) return <div className="empty">{message?.error ? <span className="down">{message.text}</span> : "LOADING…"}</div>;
  const box = boxes.find((b) => b.id === boxId) ?? null;
  const s = recs?.summary;
  const crit = box?.criteria;

  return (
    <>
      {s?.demo && (
        <div className="banner">
          <b>DEMO LISTINGS</b> — synthetic properties for trying the screener. Import a Redfin CSV
          export or configure RentCast (<code>make listings</code>) for real ones; demo listings are
          removed on the first real fetch.
        </div>
      )}
      <main className="workspace screener-grid">
        <div className="col">
          <section className="panel">
            <div className="box-tabs" role="tablist" aria-label="Buy boxes">
              {boxes.map((b) => (
                <button key={b.id} type="button" role="tab" aria-selected={b.id === boxId} className={b.id === boxId ? "on" : ""} onClick={() => setBoxId(b.id)}>
                  {b.name}
                </button>
              ))}
              <button type="button" onClick={() => void newBox()} title="New buy box">
                +
              </button>
            </div>
            <div className="panel-body">
              <div className="section-actions">
                <label className="btn btn-sm" style={{ flex: 1 }}>
                  IMPORT LISTINGS CSV
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    hidden
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void f.text().then(importCsv);
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                {sources?.active_listings ?? 0} active listings ·{" "}
                {sources?.rentcast_configured
                  ? `RentCast: ${sources.listing_areas.join("; ") || "no areas set"}`
                  : "RentCast not configured"}
              </div>
              {message && <div className={message.error ? "down" : "muted"} style={{ fontSize: 11, marginTop: 6 }}>{message.text}</div>}
            </div>
          </section>
          {box && (
            <BuyBoxPanel
              key={`${box.id}-${version}`}
              box={box}
              currentRate={s?.interest_rate ?? null}
              onSaved={(b) => {
                setBoxes((cur) => cur?.map((x) => (x.id === b.id ? b : x)) ?? null);
                rescreen();
              }}
              onDeleted={() => {
                setBoxId(null);
                rescreen();
              }}
            />
          )}
        </div>

        <div className="col col-main">
          <section className="panel">
            <div className="quote">
              <div className="quote-id">
                <div className="quote-name">{box?.name ?? "Screener"}</div>
                <div className="quote-addr">
                  Targets IRR ≥ {pct(crit?.min_levered_irr, 0)} · CoC ≥ {pct(crit?.min_cash_on_cash, 0)} · DSCR ≥{" "}
                  {crit?.min_dscr ?? "—"}x · financing at {pct(s?.interest_rate)}
                </div>
              </div>
              <div className="quote-stats">
                <Stat label="Scanned" value={s ? String(s.scanned) : "—"} />
                <Stat label="Filtered out" value={s ? String(s.filtered_out) : "—"} />
                <Stat label="Strong buy" value={s ? String(s.strong_buy) : "—"} tone="up" />
                <Stat label="Buy" value={s ? String(s.buy) : "—"} tone="up" />
                <Stat label="Watch" value={s ? String(s.watch) : "—"} tone="flat" />
                <Stat label="New matches" value={s ? String(s.new_matches) : "—"} tone={s?.new_matches ? "up" : ""} />
              </div>
            </div>
          </section>
          {recs && box ? (
            <ResultsTable
              rows={recs.rows}
              selectedId={selected}
              onSelect={setSelected}
              targets={{
                irr: crit?.min_levered_irr ?? 0.12,
                coc: crit?.min_cash_on_cash ?? 0.06,
                dscr: crit?.min_dscr ?? 1.2,
              }}
            />
          ) : (
            <div className="panel empty">SCREENING…</div>
          )}
        </div>

        <div className="col col-right">
          {selected != null && box ? (
            <ListingPanel key={`${selected}-${box.id}`} listingId={selected} buyBoxId={box.id} onChanged={rescreen} />
          ) : (
            <section className="panel empty">Select a listing to see why it scored the way it did.</section>
          )}
        </div>
      </main>
    </>
  );
}

function Stat({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className={`stat-value num ${tone}`} style={{ fontSize: 16, fontWeight: 600 }}>
        {value}
      </div>
    </div>
  );
}
