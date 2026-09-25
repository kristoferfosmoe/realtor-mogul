"use client";

import { useEffect, useMemo, useState } from "react";

import { api, type Deal, type SensitivityGrid } from "@/lib/api";
import { pct, usdCompact } from "@/lib/format";
import { METRICS, type MetricDef } from "@/lib/metrics";

import { formatMetric } from "./Quote";

interface Axis {
  field: string;
  label: string;
  values: number[];
  base: number;
  money: boolean;
}

interface Preset {
  id: string;
  label: string;
  needsLoan?: boolean;
  axes: (deal: Deal) => { x: Axis; y: Axis };
}

const STEPS = [-2, -1, 0, 1, 2];

function scaled(field: string, label: string, base: number, step = 0.05): Axis {
  return { field, label, base, money: true, values: STEPS.map((s) => base * (1 + s * step)) };
}

function shifted(
  field: string,
  label: string,
  base: number,
  step: number,
  [lo, hi]: [number, number],
): Axis {
  const values = [
    ...new Set(STEPS.map((s) => Math.min(hi, Math.max(lo, round(base + s * step))))),
  ];
  return { field, label, base: round(base), money: false, values };
}

const round = (v: number) => Math.round(v * 1e6) / 1e6;

const PRESETS: Preset[] = [
  {
    id: "price-rent",
    label: "Price × Rent",
    axes: (d) => ({
      x: scaled("monthly_rent", "Rent / mo", d.monthly_rent),
      y: scaled("purchase_price", "Price", d.purchase_price),
    }),
  },
  {
    id: "rate-down",
    label: "Rate × Down payment",
    needsLoan: true,
    axes: (d) => ({
      x: shifted("financing.down_payment_pct", "Down", d.financing!.down_payment_pct, 0.05, [0, 1]),
      y: shifted("financing.interest_rate", "Rate", d.financing!.interest_rate, 0.005, [0, 0.5]),
    }),
  },
  {
    id: "growth",
    label: "Rent growth × Appreciation",
    axes: (d) => ({
      x: shifted("appreciation", "Appr.", d.appreciation, 0.01, [-0.5, 0.5]),
      y: shifted("rent_growth", "Rent g.", d.rent_growth, 0.01, [-0.5, 0.5]),
    }),
  },
  {
    id: "vacancy-exit",
    label: "Vacancy × Hold period",
    axes: (d) => ({
      x: {
        field: "hold_years",
        label: "Hold",
        base: d.hold_years,
        money: false,
        values: [...new Set([3, 5, 7, 10, 15, d.hold_years])].sort((a, b) => a - b),
      },
      y: shifted("vacancy_rate", "Vacancy", d.vacancy_rate, 0.025, [0, 1]),
    }),
  },
];

/** The chosen preset, falling back to the first when it needs a loan the deal lacks. */
function pickPreset(id: string, deal: Deal): Preset {
  const usable = PRESETS.filter((p) => !p.needsLoan || deal.financing);
  return usable.find((p) => p.id === id) ?? usable[0]!;
}

const METRIC_CHOICES: MetricDef[] = [
  METRICS.levered_irr,
  METRICS.cash_on_cash,
  METRICS.roic,
  METRICS.dscr,
  METRICS.equity_multiple,
  METRICS.unlevered_irr,
];

/** Two-way sensitivity table, colored like a market heatmap around the target return. */
export function SensitivityPanel({ deal }: { deal: Deal }) {
  const [presetId, setPresetId] = useState(PRESETS[0]!.id);
  const [metricKey, setMetricKey] = useState<string>(METRICS.levered_irr.key);
  const [grid, setGrid] = useState<SensitivityGrid | null>(null);
  const [error, setError] = useState<string | null>(null);

  const presets = PRESETS.filter((p) => !p.needsLoan || deal.financing);
  const preset = pickPreset(presetId, deal);
  const metric = METRIC_CHOICES.find((m) => m.key === metricKey) ?? METRICS.levered_irr;
  const axes = useMemo(() => pickPreset(presetId, deal).axes(deal), [presetId, deal]);

  useEffect(() => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      api
        .sensitivity(
          {
            deal,
            x_field: axes.x.field,
            x_values: axes.x.values,
            y_field: axes.y.field,
            y_values: axes.y.values,
            metric: metric.key,
          },
          ctrl.signal,
        )
        .then((g) => {
          setGrid(g);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : String(e));
        });
    }, 350);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [deal, axes, metric.key]);

  const label = (axis: Axis, v: number) =>
    axis.money ? usdCompact(v) : axis.field === "hold_years" ? `${v}y` : pct(v, 1);

  // The fetched grid can lag a preset switch; only draw it once it matches.
  const current =
    grid && grid.x_field === axes.x.field && grid.y_field === axes.y.field && grid.metric === metric.key
      ? grid
      : null;

  return (
    <section className="panel">
      <div className="panel-head">
        <span>Sensitivity</span>
        <span className="muted">{metric.label}</span>
      </div>
      <div className="heat-controls">
        <select
          className="select"
          aria-label="Sensitivity inputs"
          value={preset.id}
          onChange={(e) => setPresetId(e.target.value)}
        >
          {presets.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        <select
          className="select"
          aria-label="Sensitivity metric"
          value={metric.key}
          onChange={(e) => setMetricKey(e.target.value)}
        >
          {METRIC_CHOICES.map((m) => (
            <option key={m.key} value={m.key}>
              {m.label}
            </option>
          ))}
        </select>
      </div>
      {error ? (
        <div className="panel-body down">{error}</div>
      ) : (
        <table className="heat num">
          <thead>
            <tr>
              <th className="axis">
                {axes.y.label} ↓ {axes.x.label} →
              </th>
              {axes.x.values.map((x) => (
                <th key={x}>{label(axes.x, x)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {axes.y.values.map((y, r) => (
              <tr key={y}>
                <th>{label(axes.y, y)}</th>
                {axes.x.values.map((x, c) => {
                  const v = current?.values[r]?.[c] ?? null;
                  const isBase = isClose(x, axes.x.base) && isClose(y, axes.y.base);
                  return (
                    <td
                      key={x}
                      className={isBase ? "base" : ""}
                      style={{ background: heat(metric, v) }}
                    >
                      {current ? formatMetric(metric, v).replace(/\.(\d)\d%$/, ".$1%") : "·"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

const isClose = (a: number, b: number) => Math.abs(a - b) <= Math.abs(b) * 1e-9 + 1e-9;

/** Green above the metric's target, red below; saturation grows with the distance. */
function heat(metric: MetricDef, v: number | null): string {
  if (v == null) return "var(--panel-2)";
  const target = metric.target ?? 0;
  const scale = metric.format === "pct" ? 0.08 : metric.format === "mult" ? 0.75 : 5_000;
  const t = Math.min(1, Math.abs(v - target) / scale);
  const alpha = (0.1 + 0.55 * t).toFixed(3);
  return v >= target ? `rgba(14, 203, 129, ${alpha})` : `rgba(246, 70, 93, ${alpha})`;
}
