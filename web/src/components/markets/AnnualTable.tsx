import type { Point } from "@/lib/api";
import { pct, usd } from "@/lib/format";
import { annualTable, signedPct } from "@/lib/markets";

export function AnnualTable({ rent, value }: { rent: Point[]; value: Point[] }) {
  const rows = annualTable(rent, value);
  const tone = (v: number | null) => (v == null ? "" : v >= 0 ? "up" : "down");
  return (
    <section className="panel">
      <div className="panel-head">
        <span>History by year</span>
        <span className="muted">year-end or latest</span>
      </div>
      <div className="table-scroll">
        <table className="grid num">
          <thead>
            <tr>
              <th>Year</th>
              <th>Rent</th>
              <th>Rent YoY</th>
              <th>Home value</th>
              <th>Value YoY</th>
              <th>Gross yield</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.year}>
                <td>{r.year}</td>
                <td>{usd(r.rent)}</td>
                <td className={tone(r.rentYoy)}>{r.rentYoy == null ? "—" : signedPct(r.rentYoy)}</td>
                <td>{usd(r.value)}</td>
                <td className={tone(r.valueYoy)}>{r.valueYoy == null ? "—" : signedPct(r.valueYoy)}</td>
                <td>{pct(r.grossYield)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
