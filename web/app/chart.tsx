"use client";

import { useEffect, useRef } from "react";
import type { ECharts, EChartsOption } from "echarts";

export default function Chart({
  option,
  height = 280,
  label,
  onPick,
}: {
  option: EChartsOption;
  height?: number;
  label: string;
  onPick?: (name: string, data: unknown) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);
  const pickRef = useRef(onPick);
  pickRef.current = onPick;

  useEffect(() => {
    let disposed = false;
    let observer: ResizeObserver | null = null;
    void import("echarts").then((echarts) => {
      if (disposed || !ref.current) return;
      const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
      chartRef.current = chart;
      chart.setOption(option);
      chart.on("click", (event) => pickRef.current?.(String(event.name ?? ""), event.data));
      observer = new ResizeObserver(() => chart.resize());
      observer.observe(ref.current);
    });
    return () => {
      disposed = true;
      observer?.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={ref} className="chart" style={{ height }} role="img" aria-label={label} />;
}
