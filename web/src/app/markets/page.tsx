import { Suspense } from "react";

import { MarketsView } from "@/components/markets/MarketsView";

export default function MarketsPage() {
  return (
    <Suspense fallback={<div className="empty">LOADING…</div>}>
      <MarketsView />
    </Suspense>
  );
}
