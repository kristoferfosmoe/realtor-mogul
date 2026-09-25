import type { Analysis, YearRow } from "@/lib/api";
import { acct } from "@/lib/format";

type Line = {
  label: string;
  get: (y: YearRow) => number;
  kind?: "subtotal" | "dim";
  sign?: -1;
  toned?: boolean;
};

const LINES: Line[] = [
  { label: "Gross potential rent", get: (y) => y.gross_potential_rent },
  { label: "Vacancy", get: (y) => y.vacancy_loss, sign: -1 },
  { label: "Other income", get: (y) => y.other_income },
  { label: "Effective gross income", get: (y) => y.effective_gross_income, kind: "subtotal" },
  { label: "Fixed expenses", get: (y) => y.fixed_expenses, sign: -1 },
  { label: "Variable expenses", get: (y) => y.variable_expenses, sign: -1 },
  { label: "Net operating income", get: (y) => y.noi, kind: "subtotal" },
  { label: "Debt service", get: (y) => y.debt_service, sign: -1 },
  { label: "Cash flow", get: (y) => y.cash_flow, kind: "subtotal", toned: true },
  { label: "Loan balance", get: (y) => y.loan_balance, kind: "dim" },
  { label: "Property value", get: (y) => y.property_value, kind: "dim" },
  { label: "Equity", get: (y) => y.equity, kind: "dim" },
];

/** Year-by-year operating statement, like a financial statement on a quote page. */
export function ProFormaTable({ analysis }: { analysis: Analysis }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <span>Pro forma</span>
        <span className="muted">USD · year-end</span>
      </div>
      <div className="table-scroll">
        <table className="grid num">
          <thead>
            <tr>
              <th>Line item</th>
              {analysis.years.map((y) => (
                <th key={y.year}>Y{y.year}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {LINES.map((line) => (
              <tr key={line.label} className={line.kind ?? ""}>
                <td>{line.label}</td>
                {analysis.years.map((y) => {
                  const v = line.get(y) * (line.sign ?? 1);
                  const cls = line.toned ? (v >= 0 ? "up" : "down") : "";
                  return (
                    <td key={y.year} className={cls}>
                      {acct(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
