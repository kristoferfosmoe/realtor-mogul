import type { Benchmark } from "@/lib/api";
import { usd } from "@/lib/format";

const BEDROOMS: Record<string, string> = {
  "0br": "Studio",
  "1br": "1 bed",
  "2br": "2 bed",
  "3br": "3 bed",
  "4br": "4 bed",
};

/** HUD fair market rents by bedroom and the Census median, next to Zillow's typical rent. */
export function RentBenchmarks({ benchmarks, typical }: { benchmarks: Benchmark[]; typical?: number | null }) {
  if (benchmarks.length === 0) return null;
  const fmr = benchmarks.filter((b) => b.metric === "fair_market_rent");
  const acs = benchmarks.find((b) => b.metric === "median_gross_rent");
  const fy = fmr[0] ? Number(fmr[0].date.slice(0, 4)) + 1 : null; // FY N starts Oct 1 of N-1
  const cell = (v: number) => (
    <>
      {usd(v)}
      {typical ? <span className="muted"> {((v / typical) * 100).toFixed(0)}%</span> : null}
    </>
  );
  return (
    <section className="panel">
      <div className="panel-head">
        <span>Published rents</span>
        <span className="muted">
          rent + utilities{typical ? " · % of Zillow typical" : ""}
        </span>
      </div>
      <div className="table-scroll">
        <table className="grid num">
          <thead>
            <tr>
              <th>Measure</th>
              {fmr.map((b) => (
                <th key={b.segment}>{BEDROOMS[b.segment] ?? b.segment}</th>
              ))}
              {acs && <th>All units</th>}
            </tr>
          </thead>
          <tbody>
            {fmr.length > 0 && (
              <tr>
                <td title="HUD's 40th-percentile gross rent; sets Section 8 payment standards">
                  HUD fair market rent FY{fy}
                </td>
                {fmr.map((b) => (
                  <td key={b.segment}>{cell(b.value)}</td>
                ))}
                {acs && <td />}
              </tr>
            )}
            {acs && (
              <tr>
                <td title="Median paid by all renter households, including long-term tenants">
                  Census median gross rent {acsYears(acs.date)}
                </td>
                {fmr.map((b) => (
                  <td key={b.segment} />
                ))}
                <td>{cell(acs.value)}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** ACS 5-year estimates are labeled by their last year: 2024 covers 2020–24. */
function acsYears(date: string): string {
  const end = Number(date.slice(0, 4));
  return `${end - 4}–${String(end).slice(2)}`;
}
