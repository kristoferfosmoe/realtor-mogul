"use client";

import {
  AreaSeries,
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Analysis, Deal } from "@/lib/api";
import { usdCompact } from "@/lib/format";

const COLORS = {
  value: "#4c8dff",
  equity: "#f0b90b",
  loan: "#7d8795",
  up: "#0ecb81",
  down: "#f6465d",
};

interface Series {
  value: ISeriesApi<"Area">;
  equity: ISeriesApi<"Line">;
  loan: ISeriesApi<"Line">;
  cash: ISeriesApi<"Histogram">;
}

const START_YEAR = new Date().getFullYear();
const toTime = (year: number) => (Date.UTC(START_YEAR + year, 0, 1) / 1000) as UTCTimestamp;
const toYear = (t: Time) => new Date((t as number) * 1000).getUTCFullYear();

/** Property value, loan and equity over the hold, with annual cash flow as "volume". */
export function CashFlowChart({ deal, analysis }: { deal: Deal; analysis: Analysis }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<Series | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const c = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#7d8795",
        fontFamily: getComputedStyle(document.body).getPropertyValue("--font-mono") || "monospace",
        fontSize: 11,
        panes: { separatorColor: "#232a35", enableResize: false },
        attributionLogo: false,
      },
      grid: { vertLines: { color: "#161b22" }, horzLines: { color: "#161b22" } },
      rightPriceScale: { borderColor: "#232a35" },
      timeScale: {
        borderColor: "#232a35",
        fixLeftEdge: true,
        fixRightEdge: true,
        tickMarkFormatter: (t: Time) => String(toYear(t)),
      },
      crosshair: { mode: CrosshairMode.Magnet },
      localization: {
        priceFormatter: (p: number) => usdCompact(p),
        timeFormatter: (t: Time) => `Y${toYear(t) - START_YEAR} · ${toYear(t)}`,
      },
      handleScroll: false,
      handleScale: false,
    });
    series.current = {
      value: c.addSeries(AreaSeries, {
        lineColor: COLORS.value,
        topColor: "rgba(76, 141, 255, 0.28)",
        bottomColor: "rgba(76, 141, 255, 0.02)",
        lineWidth: 2,
        title: "Value",
      }),
      equity: c.addSeries(LineSeries, { color: COLORS.equity, lineWidth: 2, title: "Equity" }),
      loan: c.addSeries(LineSeries, {
        color: COLORS.loan,
        lineWidth: 1,
        lineStyle: 2,
        title: "Loan",
      }),
      cash: c.addSeries(HistogramSeries, { title: "Cash flow", priceLineVisible: false }, 1),
    };
    c.panes()[1]?.setHeight(90);
    chart.current = c;
    return () => {
      c.remove();
      chart.current = null;
      series.current = null;
    };
  }, []);

  useEffect(() => {
    const s = series.current;
    if (!s) return;
    const start = deal.after_repair_value ?? deal.purchase_price;
    const loan0 = analysis.metrics.loan_amount;
    s.value.setData([
      { time: toTime(0), value: start },
      ...analysis.years.map((y) => ({ time: toTime(y.year), value: y.property_value })),
    ]);
    s.equity.setData([
      { time: toTime(0), value: start - loan0 },
      ...analysis.years.map((y) => ({ time: toTime(y.year), value: y.equity })),
    ]);
    s.loan.setData([
      { time: toTime(0), value: loan0 },
      ...analysis.years.map((y) => ({ time: toTime(y.year), value: y.loan_balance })),
    ]);
    s.cash.setData(
      analysis.years.map((y) => ({
        time: toTime(y.year),
        value: y.cash_flow,
        color: y.cash_flow >= 0 ? COLORS.up : COLORS.down,
      })),
    );
    chart.current?.timeScale().fitContent();
  }, [deal, analysis]);

  return (
    <section className="panel">
      <div className="panel-head">
        <span>Equity build · {deal.hold_years} yr</span>
        <span className="chart-legend">
          <Legend color={COLORS.value} label="Property value" />
          <Legend color={COLORS.equity} label="Equity" />
          <Legend color={COLORS.loan} label="Loan balance" />
          <Legend color={COLORS.up} label="Annual cash flow" />
        </span>
      </div>
      <div ref={container} className="chart-box" />
    </section>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span>
      <span className="swatch" style={{ background: color }} />
      {label}
    </span>
  );
}
