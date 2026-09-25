"use client";

import { useSearchParams } from "next/navigation";

import { Analyzer } from "./Analyzer";

export function AnalyzerRoute() {
  const param = useSearchParams().get("deal");
  const savedId = param && /^\d+$/.test(param) ? Number(param) : null;
  return <Analyzer key={savedId ?? "new"} savedId={savedId} />;
}
