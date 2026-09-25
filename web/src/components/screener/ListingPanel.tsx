"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { NumField } from "@/components/form/NumField";
import { api, type ListingDetail } from "@/lib/api";
import { mult, pct, usd } from "@/lib/format";
import { typeLabel } from "@/lib/portfolio";

import { SIGNAL_TONE } from "./ResultsTable";

const COMPONENT_LABELS: Record<string, string> = {
  returns: "Returns",
  cash: "Cash flow",
  market: "Market",
  risk: "Risk",
  fit: "Fit",
};

/** Why a listing scored the way it did, plus actions: override rent, analyze, open. */
export function ListingPanel({
  listingId,
  buyBoxId,
  onChanged,
}: {
  listingId: number;
  buyBoxId: number;
  onChanged: () => void;
}) {
  const router = useRouter();
  const [detail, setDetail] = useState<ListingDetail | null>(null);
  const [rent, setRent] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .listing(listingId, buyBoxId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setRent(d.listing.rent_override ?? null);
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [listingId, buyBoxId, version]);

  if (error) return <section className="panel panel-body down">{error}</section>;
  if (!detail) return <section className="panel empty">LOADING…</section>;

  const { listing: l, evaluation: ev, rent: est } = detail;
  const refresh = () => {
    setVersion((v) => v + 1);
    onChanged();
  };
  const override = (value: number | null) =>
    void api.patchListing(l.id, { rent_override: value }).then(refresh, (e: unknown) => setError(String(e)));

  const analyze = async () => {
    try {
      const { deal_id } = await api.listingToWatchlist(l.id, buyBoxId);
      router.push(`/?deal=${deal_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <span>{typeLabel(l.property_type)} · {l.source.toUpperCase()}</span>
          {ev && <span className={`badge ${SIGNAL_TONE[ev.signal]}`}>{ev.signal} {ev.score.toFixed(0)}</span>}
        </div>
        <div className="panel-body">
          <div className="quote-name" style={{ fontSize: 16, whiteSpace: "normal" }}>{l.address}</div>
          <div className="quote-addr">
            {[l.city, l.state, l.zip].filter(Boolean).join(", ")}
            {l.market_name ? ` · ${l.market_name}` : " · no metro match (national data)"}
          </div>
          <div className="quote-stats" style={{ margin: "10px 0 0", gap: "6px 18px" }}>
            <Stat label="Price" value={usd(l.price)} />
            <Stat label="Beds / baths" value={`${l.beds ?? "?"} / ${l.baths ?? "?"}`} />
            <Stat label="Sq ft" value={l.sqft ? l.sqft.toLocaleString() : "—"} />
            <Stat label="Built" value={l.year_built ? String(l.year_built) : "—"} />
            <Stat label="Units" value={`${l.units}${l.units_inferred ? " (guess)" : ""}`} />
            <Stat label="HOA" value={l.hoa_monthly ? `${usd(l.hoa_monthly)}/mo` : "—"} />
          </div>
          <div className="row" style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button type="button" className="btn btn-buy" style={{ flex: 1 }} onClick={() => void analyze()} disabled={!ev}>
              OPEN IN ANALYZER →
            </button>
            {l.url && (
              <a className="btn btn-ghost" href={l.url} target="_blank" rel="noreferrer">
                LISTING ↗
              </a>
            )}
          </div>
        </div>
      </section>

      {detail.filtered_because.length > 0 && (
        <section className="panel panel-body">
          <span className="down">Filtered out:</span> {detail.filtered_because.join(", ")}
        </section>
      )}

      {ev && est && (
        <section className="panel">
          <div className="panel-head">
            <span>Why</span>
            <span className="muted num">
              IRR {pct(ev.metrics.levered_irr)} · CoC {pct(ev.metrics.cash_on_cash)} · DSCR {mult(ev.metrics.dscr)}
            </span>
          </div>
          <div className="panel-body">
            {Object.entries(ev.components).map(([k, v]) => (
              <div key={k} className="component num">
                <span className="muted" style={{ fontFamily: "var(--font-sans)" }}>{COMPONENT_LABELS[k] ?? k}</span>
                <div className="bar"><div style={{ width: `${Math.round(v * 100)}%` }} /></div>
                <span>{Math.round(v * 100)}</span>
              </div>
            ))}
            <ul className="reasons" style={{ marginTop: 10 }}>
              {ev.reasons.map((r) => (
                <li key={r.text} className={r.tone}>
                  {r.text}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-head">
          <span>Rent</span>
          {est && <span className="muted">{est.source} · {est.confidence} confidence</span>}
        </div>
        <div className="ticket-fields" style={{ paddingTop: 10 }}>
          <NumField
            label="Your rent estimate / mo"
            kind="usd"
            optional
            placeholder={est ? String(Math.round(est.monthly)) : "rent"}
            value={rent}
            onChange={setRent}
            title="Overrides the model and the listing's stated rent"
          />
          <div className="section-actions" style={{ justifyContent: "flex-end" }}>
            {l.rent_override != null && (
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => override(null)}>
                CLEAR
              </button>
            )}
            <button type="button" className="btn btn-sm" disabled={!rent || rent === l.rent_override} onClick={() => override(rent)}>
              APPLY
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <span>Price history</span>
          <span className="muted">{l.days_on_market ?? "?"} days on market</span>
        </div>
        <div className="panel-body num">
          {detail.events.map((e, i) => (
            <div key={`${e.date}-${i}`} className="info-row">
              <span className="muted">{e.date} · {e.event.replace("_", " ")}</span>
              <span>{usd(e.price)}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className="stat-value num">{value}</div>
    </div>
  );
}
