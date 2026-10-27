"use client";

import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import Chart from "./chart";
import type { AnalyticsReport } from "./analytics-view";
import { Icon, threatIcon } from "./icons";

const RISK = { low: "#3d8c4e", moderate: "#d89a12", high: "#e15a1c", very_high: "#c62828", insufficient_data: "#8d9488" } as const;
const CLASS_ORDER = ["low", "moderate", "high", "very_high"] as const;
const CLASS_NAME: Record<string, string> = { low: "Low", moderate: "Moderate", high: "High", very_high: "Very high" };
const LABEL_RANK: Record<string, number> = { Low: 1, Moderate: 2, High: 3, "Very High": 4, "Very high": 4 };
const FACTOR_STATUS = [
  ["Favorable", "#c62828"],
  ["Neutral", "#b9c2b4"],
  ["Estimated", "#d89a12"],
  ["Not available", "#e8ece5"],
] as const;
const AXIS = { axisLine: { lineStyle: { color: "#c9d4c8" } }, axisLabel: { color: "#4a574b", fontSize: 11 }, splitLine: { lineStyle: { color: "#eef1eb" } } };
const TIP = { backgroundColor: "#fbfcf8", borderColor: "#d7e0d4", textStyle: { color: "#1c261c", fontSize: 12 } };

type Row = AnalyticsReport["ranking"][number] & { risk_class?: string | null; horizon_points?: number | null; horizon_class?: string | null };

function classRank(value: string | null | undefined) {
  const index = CLASS_ORDER.indexOf((value || "") as (typeof CLASS_ORDER)[number]);
  return index < 0 ? -1 : index;
}

export default function RiskBoard({
  report,
  threats,
  threat,
  mode,
  loading,
  error,
  canPlan,
  onThreat,
  onOpenPlace,
  onAddPlan,
  onOpenMap,
  onRetry,
}: {
  report: AnalyticsReport | null;
  threats: { id: string; name: string }[];
  threat: string;
  mode: "risk" | "patterns";
  loading: boolean;
  error: string;
  canPlan: boolean;
  onThreat: (id: string) => void;
  onOpenPlace: (slug: string) => void;
  onAddPlan: (item: { slug: string; name: string }) => void;
  onOpenMap: () => void;
  onRetry: () => void;
}) {
  const rows = (report?.ranking || []) as Row[];
  const [focus, setFocus] = useState<string[]>([]);
  const bySlugName = useMemo(() => new Map(rows.map((row) => [row.name, row.slug])), [rows]);

  const stats = useMemo(() => {
    const elevatedNow = rows.filter((row) => classRank(row.risk_class) >= 2).length;
    const elevatedAhead = rows.filter((row) => classRank(row.horizon_class) >= 2).length;
    const rising = rows.filter((row) => row.trend_direction === "rising").length;
    const escalations = rows.filter((row) => classRank(row.horizon_class) > classRank(row.risk_class) && classRank(row.risk_class) >= 0).length;
    const fastest = [...rows].filter((row) => row.trend_points != null).sort((a, b) => (b.trend_points ?? 0) - (a.trend_points ?? 0))[0];
    const top = [...rows].filter((row) => row.priority_points != null).sort((a, b) => (b.priority_points ?? 0) - (a.priority_points ?? 0))[0];
    const persistent = rows.filter((row) => classRank(row.risk_class) >= 2 && classRank(row.horizon_class) >= 2).length;
    return { elevatedNow, elevatedAhead, rising, escalations, fastest, top, persistent, total: rows.length };
  }, [rows]);

  const ranked = useMemo(() => [...rows].sort((a, b) => (b.priority_points ?? -1) - (a.priority_points ?? -1)).slice(0, 15).reverse(), [rows]);

  const rankingOption = useMemo<EChartsOption>(() => ({
    grid: { left: 150, right: 40, top: 28, bottom: 24 },
    tooltip: { ...TIP, trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { top: 0, right: 0, textStyle: { fontSize: 11, color: "#4a574b" }, data: ["Inspection priority", "Hazard"] },
    xAxis: { type: "value", max: 100, ...AXIS },
    yAxis: { type: "category", data: ranked.map((row) => row.name), ...AXIS, axisLabel: { ...AXIS.axisLabel, fontSize: 12 } },
    series: [
      {
        name: "Inspection priority",
        type: "bar",
        barWidth: 10,
        data: ranked.map((row) => ({ value: row.priority_points, itemStyle: { color: RISK[(row.risk_class || "insufficient_data") as keyof typeof RISK] || RISK.insufficient_data } })),
        label: { show: true, position: "right", fontSize: 11, color: "#1c261c" },
      },
      { name: "Hazard", type: "bar", barWidth: 4, barGap: "40%", data: ranked.map((row) => row.hazard_points), itemStyle: { color: "#173226" } },
    ],
  }), [ranked]);

  const trajectoryRows = useMemo(() => {
    const chosen = focus.length ? rows.filter((row) => focus.includes(row.slug)) : [...rows].sort((a, b) => (b.priority_points ?? -1) - (a.priority_points ?? -1)).slice(0, 6);
    return chosen;
  }, [rows, focus]);

  const trajectoryOption = useMemo<EChartsOption>(() => {
    const labels = trajectoryRows[0]?.series.map((point) => point.label) || [];
    const nowIndex = labels.indexOf("Now");
    return {
      grid: { left: 40, right: 110, top: 20, bottom: 30 },
      tooltip: { ...TIP, trigger: "axis" },
      xAxis: { type: "category", data: labels, boundaryGap: false, ...AXIS },
      yAxis: { type: "value", min: 0, max: 100, ...AXIS },
      visualMap: undefined,
      series: trajectoryRows.map((row) => ({
        name: row.name,
        type: "line",
        symbolSize: 6,
        data: row.series.map((point) => point.points),
        lineStyle: { width: 2 },
        endLabel: { show: true, formatter: "{a}", fontSize: 11, color: "#1c261c" },
        markArea: nowIndex >= 0 ? { silent: true, itemStyle: { color: "rgba(23,50,38,0.05)" }, data: [[{ xAxis: labels[nowIndex] }, { xAxis: labels[labels.length - 1] }]] } : undefined,
        markLine: { silent: true, symbol: "none", lineStyle: { color: "#c9d4c8", type: "dashed" }, data: [{ yAxis: 60 }], label: { formatter: "High band", fontSize: 10, color: "#5d6b5e" } },
      })),
    };
  }, [trajectoryRows]);

  const distributionOption = useMemo<EChartsOption>(() => {
    const rowsByClass = report?.distribution?.rows || [];
    return {
      grid: { left: 70, right: 20, top: 30, bottom: 20 },
      tooltip: { ...TIP, trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { top: 0, textStyle: { fontSize: 11, color: "#4a574b" } },
      xAxis: { type: "value", max: stats.total || undefined, ...AXIS },
      yAxis: { type: "category", data: ["+72h", "Now"], ...AXIS },
      series: CLASS_ORDER.map((id) => {
        const row = rowsByClass.find((item) => item.id === id);
        return {
          name: CLASS_NAME[id],
          type: "bar",
          stack: "class",
          barWidth: 26,
          itemStyle: { color: RISK[id] },
          label: { show: true, fontSize: 11, color: "#fff", formatter: (params: { value: unknown }) => (Number(params.value) > 0 ? String(params.value) : "") },
          data: [row?.ahead ?? 0, row?.now ?? 0],
        };
      }),
    };
  }, [report, stats.total]);

  const transitionOption = useMemo<EChartsOption>(() => {
    const matrix = report?.transitions?.matrix || {};
    const data: [number, number, number][] = [];
    CLASS_ORDER.forEach((from, y) => CLASS_ORDER.forEach((to, x) => data.push([x, y, matrix[from]?.[to] ?? 0])));
    const peak = Math.max(1, ...data.map((cell) => cell[2]));
    return {
      grid: { left: 80, right: 20, top: 30, bottom: 50 },
      tooltip: { ...TIP, formatter: (params: any) => {
        const cell = params.data as [number, number, number];
        return `${CLASS_NAME[CLASS_ORDER[cell[1]]]} now → ${CLASS_NAME[CLASS_ORDER[cell[0]]]} at +72h: ${cell[2]} municipalities`;
      } },
      xAxis: { type: "category", name: "+72h", nameLocation: "middle", nameGap: 30, data: CLASS_ORDER.map((id) => CLASS_NAME[id]), ...AXIS },
      yAxis: { type: "category", name: "Now", data: CLASS_ORDER.map((id) => CLASS_NAME[id]), ...AXIS },
      visualMap: { show: false, min: 0, max: peak, inRange: { color: ["#f4f6f1", "#e15a1c", "#8e2424"] } },
      series: [{ type: "heatmap", data, label: { show: true, fontSize: 13, color: "#1c261c" }, itemStyle: { borderColor: "#fff", borderWidth: 2 } }],
    };
  }, [report]);

  const threatMatrixOption = useMemo<EChartsOption>(() => {
    const matrix = report?.matrix || [];
    const names = matrix.map((row) => row.name).reverse();
    const ids = threats.map((item) => item.id);
    const data: [number, number, number, string][] = [];
    matrix.slice().reverse().forEach((row, y) => ids.forEach((id, x) => {
      const label = row.classes[id];
      data.push([x, y, label ? LABEL_RANK[label] ?? 0 : 0, label || "No score"]);
    }));
    return {
      grid: { left: 160, right: 20, top: 40, bottom: 10 },
      tooltip: { ...TIP, formatter: (params: any) => {
        const cell = params.data as [number, number, number, string];
        return `${names[cell[1]]} · ${threats[cell[0]]?.name}: ${cell[3]}`;
      } },
      xAxis: { type: "category", position: "top", data: threats.map((item) => item.name), ...AXIS, axisLabel: { ...AXIS.axisLabel, interval: 0 } },
      yAxis: { type: "category", data: names, ...AXIS },
      visualMap: { show: false, type: "piecewise", pieces: [
        { value: 0, color: "#eef1eb" }, { value: 1, color: RISK.low }, { value: 2, color: RISK.moderate }, { value: 3, color: RISK.high }, { value: 4, color: RISK.very_high },
      ], dimension: 2 },
      series: [{ type: "heatmap", data, itemStyle: { borderColor: "#fff", borderWidth: 2 } }],
    };
  }, [report, threats]);

  const factorOption = useMemo<EChartsOption>(() => {
    const labels = new Map<string, Record<string, number>>();
    for (const row of rows) {
      for (const factor of row.factors) {
        const bucket = labels.get(factor.label) || {};
        bucket[factor.status] = (bucket[factor.status] || 0) + 1;
        labels.set(factor.label, bucket);
      }
    }
    const names = [...labels.keys()];
    return {
      grid: { left: 230, right: 20, top: 30, bottom: 20 },
      tooltip: { ...TIP, trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { top: 0, textStyle: { fontSize: 11, color: "#4a574b" } },
      xAxis: { type: "value", max: rows.length || undefined, ...AXIS },
      yAxis: { type: "category", data: names, ...AXIS },
      series: FACTOR_STATUS.map(([status, color]) => ({
        name: status,
        type: "bar",
        stack: "f",
        barWidth: 14,
        itemStyle: { color },
        data: names.map((name) => labels.get(name)?.[status] || 0),
      })),
    };
  }, [rows]);

  const scatterOption = useMemo<EChartsOption>(() => ({
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    tooltip: { ...TIP, formatter: (params: any) => {
      const cell = params.data as { name: string; value: [number, number, number] };
      return `${cell.name}<br/>Hazard ${cell.value[0]} · Priority ${cell.value[1]} · Trend ${cell.value[2] > 0 ? "+" : ""}${cell.value[2]}`;
    } },
    xAxis: { type: "value", name: "Hazard (stored)", nameLocation: "middle", nameGap: 26, min: 0, max: 100, ...AXIS },
    yAxis: { type: "value", name: "Inspection priority", min: 0, max: 100, ...AXIS },
    series: [{
      type: "scatter",
      symbolSize: 10,
      data: rows.filter((row) => row.hazard_points != null && row.priority_points != null).map((row) => ({
        name: row.name,
        value: [row.hazard_points as number, row.priority_points as number, row.trend_points ?? 0],
        itemStyle: { color: RISK[(row.risk_class || "insufficient_data") as keyof typeof RISK] || RISK.insufficient_data },
      })),
      label: { show: true, formatter: (params: any) => {
        const cell = params.data as { name: string; value: [number, number] };
        return cell.value[1] >= 80 ? cell.name : "";
      }, position: "right", fontSize: 10, color: "#1c261c" },
    }],
  }), [rows]);

  const escalations = useMemo(() => rows
    .filter((row) => classRank(row.horizon_class) > classRank(row.risk_class) && classRank(row.risk_class) >= 0)
    .sort((a, b) => ((b.horizon_points ?? 0) - (b.hazard_points ?? 0)) - ((a.horizon_points ?? 0) - (a.hazard_points ?? 0)))
    .slice(0, 8), [rows]);

  const pick = (name: string) => {
    const slug = bySlugName.get(name);
    if (slug) onOpenPlace(slug);
  };

  return (
    <div className="rb">
      <header className="rb-head">
        <div>
          <h2>{mode === "risk" ? "Pest and disease risk" : "Analytics"}</h2>
          <p>{mode === "risk"
            ? "Where conditions are favorable to each threat model, how fast scores move, and where to look first."
            : "How the stored scores relate: priority against hazard, class movement, threat overlap, and which factors drive the model."}</p>
        </div>
        <button type="button" className="secondary" onClick={onOpenMap}>Show on map</button>
      </header>
      <div className="rb-tabs" role="tablist" aria-label="Threat">
        {threats.map((item) => (
          <button key={item.id} type="button" role="tab" aria-selected={threat === item.id} onClick={() => onThreat(item.id)}><Icon name={threatIcon(item.id)} size={18} />{item.name}</button>
        ))}
      </div>
      {loading && !report && <p className="desk-note">Loading stored scores.</p>}
      {error && <p className="error" role="alert">{error} <button type="button" className="secondary" onClick={onRetry}>Try again</button></p>}
      {report && (
        <>
          <ul className="rb-kpi" aria-label="Key statistics">
            <li data-tone="alert"><b>{stats.elevatedNow}<small>/{stats.total}</small></b><span>High or very high now</span><em>Municipalities, this forecast day</em></li>
            <li data-tone="alert"><b>{stats.elevatedAhead}<small>/{stats.total}</small></b><span>High or very high at +72h</span><em>Stored forecast run</em></li>
            <li><b>{stats.escalations}</b><span>Forecast escalations</span><em>Class goes up by +72h</em></li>
            <li><b>{stats.rising}</b><span>Rising</span><em>{report.trend_rule}</em></li>
            <li><b>{stats.persistent}</b><span>Persistently elevated</span><em>High+ now and at +72h</em></li>
            {stats.fastest && <li><button type="button" onClick={() => onOpenPlace(stats.fastest!.slug)}>{stats.fastest.name}</button><span>Fastest rise</span><em>+{stats.fastest.trend_points} hazard points</em></li>}
            {stats.top && <li><button type="button" onClick={() => onOpenPlace(stats.top!.slug)}>{stats.top.name}</button><span>Highest inspection priority</span><em>{stats.top.priority_points} / 100</em></li>}
          </ul>

          {mode === "risk" && (
            <>
              <div className="rb-grid rb-grid-wide">
                <section className="rb-panel">
                  <header><h3>Where to look first</h3><p>Top 15 by inspection priority. Bar color is the hazard class. Click a bar to open the municipality.</p></header>
                  <Chart option={rankingOption} height={430} label="Inspection priority ranking" onPick={pick} />
                </section>
                <section className="rb-panel">
                  <header><h3>Class now and at +72h</h3><p>Count of municipalities in each class.</p></header>
                  <Chart option={distributionOption} height={150} label="Risk class distribution now and at 72 hours" />
                  <header><h3>Forecast escalations</h3><p>Class goes up between now and +72h.</p></header>
                  <ol className="rb-esc">
                    {escalations.map((row) => (
                      <li key={row.slug}>
                        <button type="button" onClick={() => onOpenPlace(row.slug)}>{row.name}</button>
                        <span><i style={{ background: RISK[(row.risk_class || "insufficient_data") as keyof typeof RISK] }} />{CLASS_NAME[row.risk_class || ""] || "—"} → <i style={{ background: RISK[(row.horizon_class || "insufficient_data") as keyof typeof RISK] }} />{CLASS_NAME[row.horizon_class || ""] || "—"}</span>
                        <b>{row.hazard_points} → {row.horizon_points}</b>
                        {canPlan && <button type="button" className="rb-add" onClick={() => onAddPlan({ slug: row.slug, name: row.name })}>Add to plan</button>}
                      </li>
                    ))}
                    {escalations.length === 0 && <li className="desk-note">No class goes up inside 72 hours in this run.</li>}
                  </ol>
                </section>
              </div>
              <section className="rb-panel">
                <header>
                  <h3>How the hazard score moves</h3>
                  <p>Stored runs before today, then the stored forecast. The shaded part is forecast. Nothing between points is interpolated by CROPWATCH.</p>
                </header>
                <div className="rb-chips" role="group" aria-label="Municipalities on the chart">
                  {[...rows].sort((a, b) => (b.priority_points ?? -1) - (a.priority_points ?? -1)).slice(0, 16).map((row) => (
                    <button key={row.slug} type="button" aria-pressed={trajectoryRows.some((item) => item.slug === row.slug)} onClick={() => setFocus((current) => {
                      const base = current.length ? current : trajectoryRows.map((item) => item.slug);
                      return base.includes(row.slug) ? base.filter((slug) => slug !== row.slug) : [...base, row.slug];
                    })}>{row.name}</button>
                  ))}
                </div>
                <Chart option={trajectoryOption} height={320} label="Hazard trajectory by municipality" />
              </section>
            </>
          )}

          {mode === "patterns" && (
            <>
              <div className="rb-grid">
                <section className="rb-panel">
                  <header><h3>Priority against hazard</h3><p>Each dot is a municipality. Upper right needs attention first. Labels show priority 80 and above.</p></header>
                  <Chart option={scatterOption} height={340} label="Inspection priority against hazard" onPick={pick} />
                </section>
                <section className="rb-panel">
                  <header><h3>Class movement to +72h</h3><p>Rows are today's class, columns the +72h class. Cells right of the diagonal are escalations.</p></header>
                  <Chart option={transitionOption} height={340} label="Risk class transition matrix" />
                </section>
              </div>
              <section className="rb-panel">
                <header><h3>Which factors the model found favorable</h3><p>Count of municipalities by factor status, from the threat rule engine for this threat and day.</p></header>
                <Chart option={factorOption} height={260} label="Factor status across municipalities" />
              </section>
              <section className="rb-panel">
                <header><h3>Threat overlap by municipality</h3><p>Each cell is that threat's own class. Click a row label on the map to open it. There is no combined score.</p></header>
                <Chart option={threatMatrixOption} height={Math.max(360, (report.matrix.length || 0) * 22 + 60)} label="Municipality by threat class heatmap" onPick={pick} />
              </section>
            </>
          )}
          <p className="rb-foot">Source: CROPWATCH threat rule engine, stored scores for {report.scope.label}. {report.band_definition}</p>
        </>
      )}
    </div>
  );
}
