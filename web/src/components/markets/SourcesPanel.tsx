"use client";

import { useEffect, useState } from "react";

import { api, type Sources } from "@/lib/api";

/** Freshness and health of each data source, from the ingestion run log. */
export function SourcesPanel() {
  const [data, setData] = useState<Sources | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .sources()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const latest = new Map<string, Sources["runs"][number]>();
  for (const r of data?.runs ?? []) if (!latest.has(r.source)) latest.set(r.source, r);

  return (
    <section className="panel">
      <div className="panel-head">
        <span>Data sources</span>
      </div>
      <div className="panel-body">
        {error && <div className="down">{error}</div>}
        {data && latest.size === 0 && (
          <div className="muted">
            Nothing ingested yet. Run <code>make ingest</code> (Zillow, FRED, Census, and HUD
            when <code>MOGUL_HUD_API_TOKEN</code> is set).
          </div>
        )}
        {[...latest.values()].map((r) => (
          <div key={r.source} className="source-row">
            <div className="info-row">
              <span>
                <span className={`status-dot ${r.status === "ok" ? "ok" : r.status === "error" ? "err" : ""}`} />
                <b>{r.source.toUpperCase()}</b>
              </span>
              <span className="muted num">{ago(r.started_at)}</span>
            </div>
            <div className="muted source-detail">
              {r.status === "error"
                ? <span className="down">{r.error}</span>
                : `${r.series_count} series · ${r.observation_count.toLocaleString()} points`}
            </div>
          </div>
        ))}
        {data && (
          <div className="attribution">
            {Object.entries(data.attributions)
              .filter(([k]) => latest.has(k))
              .map(([k, v]) => (
                <div key={k}>{v}</div>
              ))}
          </div>
        )}
      </div>
    </section>
  );
}

function ago(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 60 * 48) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}
