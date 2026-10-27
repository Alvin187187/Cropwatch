"use client";

import type { CommandRecord } from "./command-center";
import type { SituationRecord } from "./situation";
import type { EChartsOption } from "echarts";
import Chart from "./chart";
import { shiftDate, WeekStrip } from "./command-board";
import { Icon, IconName } from "./icons";
import { PageHead } from "./workspaces";

export type WeatherDayPoint = {
  day: number;
  rainMean: number | null;
  rainHigh: number | null;
  tempMean: number | null;
  tempLow: number | null;
  tempHigh: number | null;
  rhMean: number | null;
  windHigh: number | null;
  soilMean: number | null;
};

type FeatureCollection = { features?: { properties?: Record<string, unknown> | null }[] };

function numbers(collection: FeatureCollection | null, field: string) {
  const values = (collection?.features || [])
    .map((feature) => feature.properties?.[field])
    .filter((value): value is number => typeof value === "number");
  return values;
}

function mean(values: number[]) {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function weatherPoint(day: number, collection: FeatureCollection | null): WeatherDayPoint {
  const rain = numbers(collection, "rain_mm");
  const temp = numbers(collection, "temp_c");
  const rh = numbers(collection, "rh_pct");
  const wind = numbers(collection, "wind_speed_kmh");
  const soil = numbers(collection, "soil_moisture");
  return {
    day,
    rainMean: mean(rain),
    rainHigh: rain.length ? Math.max(...rain) : null,
    tempMean: mean(temp),
    tempLow: temp.length ? Math.min(...temp) : null,
    tempHigh: temp.length ? Math.max(...temp) : null,
    rhMean: mean(rh),
    windHigh: wind.length ? Math.max(...wind) : null,
    soilMean: mean(soil),
  };
}

function figure(value: number | null, digits: number, unit: string) {
  if (value == null) return "—";
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

const AXIS = { axisLine: { lineStyle: { color: "#c9d4c8" } }, axisLabel: { color: "#4a574b", fontSize: 11 }, splitLine: { lineStyle: { color: "#eef1eb" } } };
const TIP = { backgroundColor: "#fbfcf8", borderColor: "#d7e0d4", textStyle: { color: "#1c261c", fontSize: 12 } };
const dayLabel = (day: number) => (day === 0 ? "Now" : `+${day}d`);

function round(value: number | null, digits: number) {
  return value == null ? null : Number(value.toFixed(digits));
}

const FACTOR_NAME: [RegExp, string, IconName][] = [
  [/temperature/i, "Temperature", "temp"],
  [/humidity/i, "Humidity", "humidity"],
  [/heaviest rain|last 7 days/i, "Heaviest rain, 7 d", "heavyRain"],
  [/forecast rain/i, "Rain ahead", "rain"],
  [/leaf|wet hours|90%/i, "Wet hours", "leafWet"],
  [/wind/i, "Wind", "wind"],
  [/el ni|season/i, "Season modifier", "sun"],
  [/soil/i, "Soil", "soil"],
];

function factorName(label: string): [string, IconName] {
  const hit = FACTOR_NAME.find(([pattern]) => pattern.test(label));
  return hit ? [hit[1], hit[2]] : [label, "layers"];
}

export function EvidenceMatrix({ lines, label }: { lines: string[]; label: string }) {
  const rows = new globalThis.Map<string, Record<string, string>>();
  const columns: string[] = [];
  const loose: string[] = [];
  for (const line of lines) {
    const match = /^(.+?)\s+(-?[\d.,]+\s?(?:°?C|%|mm|hours?|km\/h)?)\s+in\s+(.+?)\.?$/.exec(line.trim());
    if (!match) {
      loose.push(line);
      continue;
    }
    const [name] = factorName(match[1]);
    if (!columns.includes(name)) columns.push(name);
    const row = rows.get(match[3]) || {};
    row[name] = match[2].replace(/\s?C$/, " °C").replace(" hours", " h").replace(" hour", " h");
    rows.set(match[3], row);
  }
  if (rows.size === 0) return loose.length ? <ul className="keypoints">{loose.map((line) => <li key={line}>{line}</li>)}</ul> : null;
  return (
    <div className="ev-wrap">
      <table className="dtable ev" aria-label={label}>
        <thead>
          <tr>
            <th>Municipality</th>
            {columns.map((column) => {
              const [, icon] = factorName(column);
              return <th key={column} className="num"><span className="th-ic"><Icon name={icon} size={14} />{column}</span></th>;
            })}
          </tr>
        </thead>
        <tbody>
          {Array.from(rows.entries()).map(([place, values]) => (
            <tr key={place}>
              <td>{place}</td>
              {columns.map((column) => <td key={column} className="num">{values[column] || <span className="muted">—</span>}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {loose.length > 0 && <ul className="keypoints">{loose.map((line) => <li key={line}>{line}</li>)}</ul>}
    </div>
  );
}

export function WeatherBoard({
  command,
  layer,
  series,
  places,
  day,
  onOpenMap,
}: {
  command: CommandRecord | null;
  layer: SituationRecord | null;
  series: WeatherDayPoint[];
  places: { name: string; rain: number | null; temp: number | null; rh: number | null }[];
  day: number;
  onOpenMap: () => void;
}) {
  const ranked = [...places].filter((place) => place.rain != null).sort((left, right) => (right.rain ?? 0) - (left.rain ?? 0)).slice(0, 12);
  const days = [...series].sort((left, right) => left.day - right.day);
  const today = days.find((point) => point.day === day) || days[0];
  const total = days.reduce((sum, point) => sum + (point.rainMean ?? 0), 0);
  const wetDays = days.filter((point) => (point.rainMean ?? 0) >= 1).length;
  let streak = 0;
  let longest = 0;
  for (const point of days) {
    streak = (point.rainMean ?? 0) >= 1 ? streak + 1 : 0;
    longest = Math.max(longest, streak);
  }
  const windPeak = days.reduce<number | null>((peak, point) => (point.windHigh == null ? peak : Math.max(peak ?? 0, point.windHigh)), null);
  const forecastOption: EChartsOption = {
    grid: { left: 48, right: 48, top: 36, bottom: 28 },
    tooltip: { ...TIP, trigger: "axis" },
    legend: { top: 0, textStyle: { fontSize: 11, color: "#4a574b" } },
    xAxis: { type: "category", data: days.map((point) => dayLabel(point.day)), ...AXIS },
    yAxis: [
      { type: "value", name: "mm", ...AXIS },
      { type: "value", name: "°C", scale: true, ...AXIS, splitLine: { show: false } },
    ],
    series: [
      { name: "Rainfall, mean (mm)", type: "bar", barWidth: 22, itemStyle: { color: "#1d5f8a", borderRadius: [3, 3, 0, 0] }, data: days.map((point) => round(point.rainMean, 1)) },
      { name: "Wettest barangay (mm)", type: "scatter", symbol: "rect", symbolSize: [22, 3], itemStyle: { color: "#0e2438" }, data: days.map((point) => round(point.rainHigh, 1)) },
      { name: "Temperature, mean (°C)", type: "line", yAxisIndex: 1, smooth: false, symbolSize: 6, itemStyle: { color: "#c45c28" }, data: days.map((point) => round(point.tempMean, 1)) },
      { name: "Coolest", type: "line", yAxisIndex: 1, symbol: "none", lineStyle: { type: "dashed", color: "#d8a080", width: 1 }, data: days.map((point) => round(point.tempLow, 1)) },
      { name: "Warmest", type: "line", yAxisIndex: 1, symbol: "none", lineStyle: { type: "dashed", color: "#9f2d2d", width: 1 }, data: days.map((point) => round(point.tempHigh, 1)) },
    ],
  };
  const moistureOption: EChartsOption = {
    grid: { left: 48, right: 48, top: 36, bottom: 28 },
    tooltip: { ...TIP, trigger: "axis" },
    legend: { top: 0, textStyle: { fontSize: 11, color: "#4a574b" } },
    xAxis: { type: "category", data: days.map((point) => dayLabel(point.day)), ...AXIS },
    yAxis: [
      { type: "value", name: "%", min: 40, max: 100, ...AXIS },
      { type: "value", name: "km/h", ...AXIS, splitLine: { show: false } },
    ],
    series: [
      { name: "Humidity, mean (%)", type: "line", areaStyle: { color: "rgba(29,95,138,0.12)" }, itemStyle: { color: "#1d5f8a" }, data: days.map((point) => round(point.rhMean, 0)), markLine: { silent: true, symbol: "none", lineStyle: { color: "#8e2424", type: "dashed" }, data: [{ yAxis: 90 }], label: { formatter: "90%", fontSize: 10 } } },
      { name: "Highest wind (km/h)", type: "bar", yAxisIndex: 1, barWidth: 10, itemStyle: { color: "#6b5e52" }, data: days.map((point) => round(point.windHigh, 0)) },
    ],
  };
  const rankOption: EChartsOption = {
    grid: { left: 170, right: 50, top: 10, bottom: 20 },
    tooltip: { ...TIP, trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "value", name: "mm", ...AXIS },
    yAxis: { type: "category", data: ranked.map((place) => place.name).reverse(), ...AXIS },
    series: [{ type: "bar", barWidth: 12, itemStyle: { color: "#1d5f8a" }, label: { show: true, position: "right", fontSize: 11 }, data: ranked.map((place) => round(place.rain, 1)).reverse() }],
  };
  const current = day === 0 ? command?.weather.current : null;
  return (
    <div className="pg" id="weather">
      <PageHead icon="weather" title="Weather" meta={`${command?.scope.label || "Nueva Ecija"} · ${command?.forecast_date || ""} · Open-Meteo model fields, not live sensors`}>
        <button type="button" className="btn" onClick={onOpenMap}><Icon name="play" size={15} />Play on map</button>
      </PageHead>
      <ul className="wx-tiles" aria-label="Weather for the selected day">
        <li data-k="temp"><Icon name="temp" size={20} /><b>{figure(current?.temp_c ?? today?.tempMean ?? null, 1, "°C")}</b><span>Temperature</span></li>
        <li data-k="rain"><Icon name="rain" size={20} /><b>{figure(current?.rain_mm ?? today?.rainMean ?? null, 1, "mm")}</b><span>Rainfall{today?.rainHigh == null ? "" : ` · max ${today.rainHigh.toFixed(1)}`}</span></li>
        <li data-k="rh"><Icon name="humidity" size={20} /><b>{figure(current?.rh_pct ?? today?.rhMean ?? null, 0, "%")}</b><span>Humidity</span></li>
        <li data-k="wind"><Icon name="wind" size={20} /><b>{figure(current?.wind_speed_kmh ?? today?.windHigh ?? null, 0, "km/h")}</b><span>Wind</span></li>
        <li data-k="soil"><Icon name="soil" size={20} /><b>{figure(today?.soilMean ?? null, 2, "")}</b><span>Soil moisture</span></li>
      </ul>
      <section className="panel-card">
        <header className="panel-head">
          <h3><Icon name="forecast" size={17} />Seven-day outlook</h3>
          <dl className="inline-stats">
            <div><dt>Total rain</dt><dd>{days.length ? `${total.toFixed(1)} mm` : "—"}</dd></div>
            <div><dt>Wet days</dt><dd>{days.length ? `${wetDays}/${days.length}` : "—"}</dd></div>
            <div><dt>Longest wet run</dt><dd>{days.length ? `${longest} d` : "—"}</dd></div>
            <div><dt>Peak wind</dt><dd>{windPeak == null ? "—" : `${windPeak.toFixed(0)} km/h`}</dd></div>
          </dl>
        </header>
        <WeekStrip days={days} baseDate={shiftDate(command?.forecast_date, -day)} active={day} />
      </section>
      <section className="panel-card">
        <header className="panel-head"><h3><Icon name="rain" size={17} />Rainfall and temperature</h3></header>
        {days.length === 0 ? <p className="empty-line">Loading the stored forecast days.</p> : <Chart option={forecastOption} height={300} label="Seven-day rainfall and temperature" />}
      </section>
      <div className="pg-split even">
        <section className="panel-card">
          <header className="panel-head"><h3><Icon name="humidity" size={17} />Humidity and wind</h3><span className="muted small">Dashed line · 90% humidity</span></header>
          {days.length > 0 && <Chart option={moistureOption} height={260} label="Seven-day humidity and wind" />}
        </section>
        <section className="panel-card">
          <header className="panel-head"><h3><Icon name="heavyRain" size={17} />Wettest municipalities</h3><span className="muted small">{command?.forecast_date}</span></header>
          {ranked.length === 0 ? <p className="empty-line">Loads with the map forecast for this day.</p> : <Chart option={rankOption} height={300} label="Rainfall ranking by municipality" />}
        </section>
      </div>
      {layer?.weather && layer.weather.evidence.length > 0 && (
        <section className="panel-card" aria-labelledby="factor-title">
          <header className="panel-head">
            <h3 id="factor-title"><Icon name="risk" size={17} />Weather factors in the favorable range · {command?.threat.name}</h3>
          </header>
          <EvidenceMatrix lines={layer.weather.evidence} label={`Weather factors used by the ${command?.threat.name || "threat"} rules`} />
        </section>
      )}
    </div>
  );
}

function leadingNumber(text: string) {
  const match = /^(\d+)/.exec(text.trim());
  return match ? Number(match[1]) : null;
}

export function AdminBoard({
  layer,
  command,
  onOpenOperations,
}: {
  layer: SituationRecord | null;
  command: CommandRecord | null;
  onOpenOperations: () => void;
}) {
  const workload = (layer?.admin.workload.evidence || []).map((line) => {
    const match = /^(\d+)\.\s*(.+?),\s*(.+?)\.?$/.exec(line);
    return match ? { rank: Number(match[1]), name: match[2], reason: match[3] } : { rank: 0, name: line.replace(/\.$/, ""), reason: "" };
  });
  const overdueNames = (layer?.admin.overdue.evidence || []).map((line) => line.replace(/\.$/, ""));
  const overdueCount = leadingNumber(layer?.admin.overdue.sentence || "") ?? overdueNames.length;
  const notes = (layer?.admin.notes.evidence || []).map((line) => {
    const match = /^(.+?),\s*last note\s+(.+?)\.?$/.exec(line);
    return match ? { name: match[1], when: match[2] } : { name: line.replace(/\.$/, ""), when: "" };
  });
  const assignmentStored = !/no assignment record/i.test(layer?.admin.assignment.sentence || "");
  const completeness = /(\d+)\s+of\s+(\d+)/.exec(layer?.completeness.sentence || "");
  const scored = completeness ? Number(completeness[1]) : null;
  const totalPlaces = completeness ? Number(completeness[2]) : null;
  const checks = command?.confidence.checks || [];

  return (
    <div className="pg" id="administration">
      <PageHead icon="admin" title="Administration" meta={`${command?.scope.label || "Nueva Ecija"} · ${command?.threat.name || ""} · coverage, assignment, and data health`}>
        <button type="button" className="btn" onClick={onOpenOperations}><Icon name="operations" size={16} />Field operations</button>
      </PageHead>

      <ul className="stat-row" aria-label="Office summary">
        <li><span>On attention list</span><b>{layer ? workload.length : "—"}</b><small>municipalities</small></li>
        <li data-tone={overdueCount > 0 ? "watch" : undefined}><span>Elevated, no note in 7 days</span><b>{layer ? overdueCount : "—"}</b><small>municipalities</small></li>
        <li><span>With field notes</span><b>{layer ? notes.length : "—"}</b><small>municipalities</small></li>
        <li><span>Scored this day</span><b>{scored ?? "—"}<small>/{totalPlaces ?? "—"}</small></b><span className="progress" aria-hidden="true"><i style={{ width: `${scored && totalPlaces ? (scored / totalPlaces) * 100 : 0}%` }} /></span></li>
        <li data-tone={assignmentStored ? undefined : "watch"}><span>Assignments</span><b className="txt">{assignmentStored ? "Stored" : "Not stored"}</b><small>{assignmentStored ? "" : "officer assigns visits"}</small></li>
      </ul>

      <div className="pg-split even">
        <section className="panel-card" aria-labelledby="wl-title">
          <header className="panel-head"><h3 id="wl-title"><Icon name="target" size={17} />Today’s workload</h3><span className="count">{workload.length}</span></header>
          {workload.length === 0 ? <p className="empty-line">Nothing on the attention list.</p> : (
            <table className="dtable">
              <thead><tr><th className="num">#</th><th>Municipality</th><th>Reason</th></tr></thead>
              <tbody>
                {workload.map((row) => (
                  <tr key={`${row.rank}-${row.name}`}><td className="num muted">{row.rank || "—"}</td><td className="strong">{row.name}</td><td><span className="tag">{row.reason || "—"}</span></td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel-card" aria-labelledby="od-title">
          <header className="panel-head"><h3 id="od-title"><Icon name="alerts" size={17} />Elevated without a recent field note</h3><span className="count">{overdueCount}</span></header>
          {overdueNames.length === 0 ? <p className="empty-line">Every elevated municipality has a recent note.</p> : (
            <>
              <ul className="name-grid">{overdueNames.map((name) => <li key={name}>{name}</li>)}</ul>
              {overdueCount > overdueNames.length && <p className="muted small">+{overdueCount - overdueNames.length} more</p>}
            </>
          )}
        </section>
      </div>

      <div className="pg-split even">
        <section className="panel-card" aria-labelledby="fn-title">
          <header className="panel-head"><h3 id="fn-title"><Icon name="reports" size={17} />Field notes on record</h3><span className="count">{notes.length}</span></header>
          {notes.length === 0 ? <p className="empty-line">No field note stored.</p> : (
            <table className="dtable">
              <thead><tr><th>Municipality</th><th className="num">Last note</th></tr></thead>
              <tbody>{notes.map((row) => <tr key={row.name}><td className="strong">{row.name}</td><td className="num">{row.when || "—"}</td></tr>)}</tbody>
            </table>
          )}
        </section>

        <section className="panel-card" aria-labelledby="dh-title">
          <header className="panel-head"><h3 id="dh-title"><Icon name="shield" size={17} />Data health</h3><span className="count">{checks.filter((check) => check.ok).length}/{checks.length}</span></header>
          <ul className="coverage">
            {checks.map((check) => (
              <li key={check.id} data-ok={check.ok ? "yes" : "no"}>
                <Icon name={check.ok ? "check" : "close"} size={14} />
                <span>{check.label}</span>
                <small>{check.ok ? "Loaded" : "Missing"}</small>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
