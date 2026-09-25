"use client";

import {
  AreaSeries,
  ColorType,
  createChart,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import type { Point } from "@/lib/api";
import { usd, usdCompact } from "@/lib/format";

const RANGES = [
  { label: "1Y", years: 1 },
  { label: "3Y", years: 3 },
  { label: "5Y", years: 5 },
  { label: "10Y", years: 10 },
  { label: "MAX", years: 0 },
] as const;

const RENT = "#4c8dff";
const VALUE = "#f0b90b";

const toData = (pts: Point[]) => pts.map((p) => ({ time: p.date as Time, value: p.value }));

/** Rent (left scale) against home value (right scale), with trading-style range buttons. */
export function MarketChart({ rent, value }: { rent: Point[]; value: Point[] }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<{ rent: ISeriesApi<"Area">; value: ISeriesApi<"Line"> } | null>(null);
  const [range, setRange] = useState<number>(5);

  useEffect(() => {
    if (!container.current) return;
    const c = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#7d8795",
        fontFamily: getComputedStyle(document.body).getPropertyValue("--font-mono") || "monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { color: "#161b22" }, horzLines: { color: "#161b22" } },
      leftPriceScale: { visible: true, borderColor: "#232a35" },
      rightPriceScale: { visible: true, borderColor: "#232a35" },
      timeScale: { borderColor: "#232a35", fixLeftEdge: true, fixRightEdge: true },
      crosshair: { mode: CrosshairMode.Magnet },
      // Explicit, because navigator.language can be a tag Intl rejects (e.g. "en-US@posix").
      localization: { locale: "en-US" },
      handleScroll: false,
      handleScale: false,
    });
    series.current = {
      rent: c.addSeries(AreaSeries, {
        priceScaleId: "left",
        lineColor: RENT,
        topColor: "rgba(76, 141, 255, 0.25)",
        bottomColor: "rgba(76, 141, 255, 0.02)",
        lineWidth: 2,
        title: "Rent",
        priceFormat: { type: "custom", formatter: (p: number) => usd(p), minMove: 1 },
      }),
      value: c.addSeries(LineSeries, {
        priceScaleId: "right",
        color: VALUE,
        lineWidth: 2,
        title: "Home value",
        priceFormat: { type: "custom", formatter: (p: number) => usdCompact(p), minMove: 100 },
      }),
    };
    chart.current = c;
    return () => {
      c.remove();
      chart.current = null;
      series.current = null;
    };
  }, []);

  useEffect(() => {
    series.current?.rent.setData(toData(rent));
    series.current?.value.setData(toData(value));
  }, [rent, value]);

  useEffect(() => {
    const c = chart.current;
    const last = [...rent, ...value].reduce((m, p) => (p.date > m ? p.date : m), "");
    if (!c || !last) return;
    if (range === 0) {
      c.timeScale().fitContent();
      return;
    }
    const from = `${Number(last.slice(0, 4)) - range}${last.slice(4)}`;
    c.timeScale().setVisibleRange({ from: from as Time, to: last as Time });
  }, [range, rent, value]);

  return (
    <section className="panel">
      <div className="panel-head">
        <span className="chart-legend">
          <span>
            <span className="swatch" style={{ background: RENT }} />
            Rent index (left)
          </span>
          <span>
            <span className="swatch" style={{ background: VALUE }} />
            Home value (right)
          </span>
        </span>
        <span className="range-tabs" role="group" aria-label="Chart range">
          {RANGES.map((r) => (
            <button
              key={r.label}
              type="button"
              className={range === r.years ? "on" : ""}
              onClick={() => setRange(r.years)}
            >
              {r.label}
            </button>
          ))}
        </span>
      </div>
      <div ref={container} className="chart-box" />
    </section>
  );
}
