"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useWatchlist } from "@/components/WatchlistContext";
import { type Analysis, api, type Deal, type Metrics } from "@/lib/api";

import { CashFlowChart } from "./CashFlowChart";
import { type DealMeta, DealTicket } from "./DealTicket";
import { ExitPanel } from "./ExitPanel";
import { ProFormaTable } from "./ProFormaTable";
import { Quote } from "./Quote";
import { SensitivityPanel } from "./SensitivityPanel";

const BLANK_META: DealMeta = { name: "", address: "", status: "watching" };

const snapshot = (deal: Deal, meta: DealMeta) => JSON.stringify({ deal, meta });

/** Mounted per deal (keyed by id), so switching deals starts from fresh state. */
export function Analyzer({ savedId }: { savedId: number | null }) {
  const router = useRouter();
  const { refresh } = useWatchlist();

  const [deal, setDeal] = useState<Deal | null>(null);
  const [meta, setMeta] = useState<DealMeta>(BLANK_META);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [baseline, setBaseline] = useState<Metrics | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  // Load the saved deal named in the URL, or a template for a blank ticket.
  useEffect(() => {
    let cancelled = false;
    const load = savedId != null
      ? api.getDeal(savedId).then((d) => {
          const m = { name: d.name, address: d.address ?? "", status: d.status };
          return { inputs: d.inputs, meta: m, metrics: d.metrics as Metrics | null };
        })
      : api.template().then((t) => ({ inputs: t, meta: BLANK_META, metrics: null }));
    load
      .then(({ inputs, meta: m, metrics }) => {
        if (cancelled) return;
        setDeal(inputs);
        setMeta(m);
        setBaseline(metrics);
        setSaved(savedId != null ? snapshot(inputs, m) : null);
        setError(null);
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [savedId]);

  // Re-run the engine as the ticket changes, like a live quote.
  useEffect(() => {
    if (!deal) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      const t0 = performance.now();
      api
        .analyze(deal, ctrl.signal)
        .then((a) => {
          setAnalysis(a);
          setLatency(performance.now() - t0);
          setError(null);
          setBaseline((b) => b ?? a.metrics);
        })
        .catch((e: unknown) => {
          if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : String(e));
        });
    }, 150);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [deal]);

  const dirty = useMemo(
    () => deal != null && saved !== snapshot(deal, meta),
    [deal, meta, saved],
  );

  const save = useCallback(
    async (asNew: boolean) => {
      if (!deal) return;
      setSaving(true);
      const body = {
        name: meta.name.trim(),
        address: meta.address.trim() || null,
        status: meta.status,
        inputs: deal,
      };
      try {
        const result =
          savedId != null && !asNew
            ? await api.updateDeal(savedId, body)
            : await api.createDeal(body);
        setSaved(snapshot(deal, meta));
        setBaseline(result.metrics);
        await refresh();
        if (result.id !== savedId) router.replace(`/?deal=${result.id}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setSaving(false);
      }
    },
    [deal, meta, savedId, refresh, router],
  );

  if (!deal) {
    return <div className="empty">{error ? <span className="down">{error}</span> : "LOADING…"}</div>;
  }

  return (
    <>
      <main className="workspace">
        <div className="col">
          <DealTicket
            deal={deal}
            onChange={setDeal}
            meta={meta}
            onMetaChange={setMeta}
            savedId={savedId}
            saving={saving}
            dirty={dirty}
            onSave={() => void save(false)}
            onSaveAsNew={() => void save(true)}
            onNew={() => router.push("/")}
          />
        </div>
        <div className="col col-main">
          {analysis ? (
            <>
              <Quote
                name={meta.name}
                address={meta.address}
                deal={deal}
                metrics={analysis.metrics}
                baseline={baseline}
                baselineLabel={savedId != null ? "vs saved" : "vs open"}
              />
              <CashFlowChart deal={deal} analysis={analysis} />
              <ProFormaTable analysis={analysis} />
            </>
          ) : (
            <div className="panel empty">{error ? <span className="down">{error}</span> : "PRICING…"}</div>
          )}
        </div>
        <div className="col col-right">
          <SensitivityPanel deal={deal} />
          {analysis && <ExitPanel analysis={analysis} />}
        </div>
      </main>
      <footer className="statusbar num">
        {error ? (
          <span className="err">▲ {error} — showing last valid result</span>
        ) : (
          <span>
            <span className="status-dot ok" />
            LIVE · recalculated in {latency == null ? "—" : `${latency.toFixed(0)} ms`}
          </span>
        )}
        <span>{savedId == null ? "SCRATCH" : dirty ? "UNSAVED CHANGES" : "SAVED"}</span>
        <span className="disclaimer">Projections are estimates, not advice.</span>
      </footer>
    </>
  );
}
