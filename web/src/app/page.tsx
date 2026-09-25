import { Suspense } from "react";

import { AnalyzerRoute } from "@/components/analyzer/AnalyzerRoute";

export default function AnalyzerPage() {
  return (
    <Suspense fallback={<div className="empty">LOADING…</div>}>
      <AnalyzerRoute />
    </Suspense>
  );
}
