"use client";

import { useSearchParams } from "next/navigation";

import { Analyzer } from "./Analyzer";

export function AnalyzerRoute() {
  const params = useSearchParams();
  const id = (name: string) => {
    const v = params.get(name);
    return v && /^\d+$/.test(v) ? Number(v) : null;
  };
  const savedId = id("deal");
  // ?market=<geography id> starts a new deal with that market's growth rates.
  const marketId = savedId == null ? id("market") : null;
  return (
    <Analyzer key={`${savedId ?? "new"}:${marketId ?? ""}`} savedId={savedId} marketId={marketId} />
  );
}
