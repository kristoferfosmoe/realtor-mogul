"use client";

import {
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import { usdCompact } from "@/lib/format";

export interface EquityPoint {
  month: string; // ISO date
  value: number;
  loan_balance: number;
  equity: number;
  cash_flow: number;
}

const C = { value: "#4c8dff", equity: "#f0b90b", loan: "#7d8795", up: "#0ecb81", down: "#f6465d" };

/** Actual value / loan / equity over time, with monthly net cash flow as volume bars. */
export function EquityChart({ title, points }: { title: string; points: EquityPoint[] }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<{
    value: ISeriesApi<"Line">;
    equity: ISeriesApi<"Line">;
    loan: ISeriesApi<"Line">;
    cash: ISeriesApi<"Histogram">;
  } | null>(null);

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
      timeScale: { borderColor: "#232a35", fixLeftEdge: true, fixRightEdge: true },
      crosshair: { mode: CrosshairMode.Magnet },
      localization: { locale: "en-US", priceFormatter: (p: number) => usdCompact(p) },
      handleScroll: false,
      handleScale: false,
    });
    series.current = {
      value: c.addSeries(LineSeries, { color: C.value, lineWidth: 2, title: "Value" }),
      equity: c.addSeries(LineSeries, { color: C.equity, lineWidth: 2, title: "Equity" }),
      loan: c.addSeries(LineSeries, { color: C.loan, lineWidth: 1, lineStyle: 2, title: "Debt" }),
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
    const at = (p: EquityPoint) => p.month as Time;
    s.value.setData(points.map((p) => ({ time: at(p), value: p.value })));
    s.equity.setData(points.map((p) => ({ time: at(p), value: p.equity })));
    s.loan.setData(points.map((p) => ({ time: at(p), value: p.loan_balance })));
    s.cash.setData(
      points.map((p) => ({ time: at(p), value: p.cash_flow, color: p.cash_flow >= 0 ? C.up : C.down })),
    );
    chart.current?.timeScale().fitContent();
  }, [points]);

  return (
    <section className="panel">
      <div className="panel-head">
        <span>{title}</span>
        <span className="chart-legend">
          <Legend color={C.value} label="Value" />
          <Legend color={C.equity} label="Equity" />
          <Legend color={C.loan} label="Debt" />
          <Legend color={C.up} label="Monthly cash flow" />
        </span>
      </div>
      {points.length < 2 ? (
        <div className="empty">Not enough history to chart yet.</div>
      ) : null}
      <div ref={container} className="chart-box" style={points.length < 2 ? { display: "none" } : undefined} />
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
