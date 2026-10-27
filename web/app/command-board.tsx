"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { EChartsOption } from "echarts";
import type { AnalyticsReport } from "./analytics-view";
import type { CommandAction, CommandRecord } from "./command-center";
import type { SituationRecord } from "./situation";
import type { WeatherDayPoint } from "./platform";
import Chart from "./chart";
import { Icon, IconName, threatIcon } from "./icons";

const CLASS_COLOR: Record<string, string> = {
  low: "#3d8c4e",
  moderate: "#d89a12",
  high: "#e15a1c",
  very_high: "#c62828",
  insufficient_data: "#8d9488",
};

export function classKey(label: string | null | undefined) {
  const key = (label || "").toLowerCase().replace(/\s+/g, "_");
  return key in CLASS_COLOR ? key : "insufficient_data";
}

export function ClassBadge({ label }: { label: string | null | undefined }) {
  const key = classKey(label);
  return <span className="cls" data-class={key}>{label || "No data"}</span>;
}

function wxIcon(point: WeatherDayPoint): IconName {
  const rain = point.rainMean ?? 0;
  if (rain >= 10) return "heavyRain";
  if (rain >= 1) return "rain";
  if ((point.rhMean ?? 0) >= 85) return "cloud";
  return "sun";
}

export function shiftDate(iso: string | null | undefined, days: number) {
  const match = iso ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null;
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function dayName(day: number, baseDate: string | null | undefined) {
  const iso = shiftDate(baseDate, day);
  if (!iso) return { top: day === 0 ? "Today" : `+${day}d`, sub: "" };
  const date = new Date(`${iso}T00:00:00`);
  return {
    top: day === 0 ? "Today" : date.toLocaleDateString("en-PH", { weekday: "short" }),
    sub: date.toLocaleDateString("en-PH", { month: "short", day: "numeric" }),
  };
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

const CHANGE_ICON: Record<string, IconName> = {
  "high-class": "risk",
  "hazard-rise": "rising",
  rain: "rain",
  clusters: "layers",
  notes: "reports",
};

const SHORT_LABEL: Record<string, string> = {
  priority: "Top priority band",
  rising: "Rising hazard",
  alerts: "New high class",
  actions: "Actions queued",
  "high-class": "High or very high",
  "hazard-rise": "Largest rise",
  rain: "Rainfall ahead",
  clusters: "High clusters",
  notes: "New field notes",
};

export function WeekStrip({ days, baseDate, active, onPick }: { days: WeatherDayPoint[]; baseDate: string | null | undefined; active?: number; onPick?: (day: number) => void }) {
  const sorted = [...days].sort((left, right) => left.day - right.day);
  if (sorted.length === 0) return <p className="cb-empty">Loading stored forecast days.</p>;
  return (
    <ol className="week" aria-label="Seven-day weather">
      {sorted.map((point) => (
        <li key={point.day} aria-current={active === point.day ? "true" : undefined}>
          <button type="button" onClick={() => onPick?.(point.day)} disabled={!onPick}>
            <span className="week-day">{dayName(point.day, baseDate).top}<small>{dayName(point.day, baseDate).sub}</small></span>
            <Icon name={wxIcon(point)} size={26} />
            <b>{point.tempMean == null ? "—" : `${point.tempMean.toFixed(0)}°`}</b>
            <span className="week-rain"><Icon name="humidity" size={12} />{point.rainMean == null ? "—" : `${point.rainMean.toFixed(1)} mm`}</span>
            <span className="week-bar" aria-hidden="true"><i style={{ height: `${Math.min(100, ((point.rainMean ?? 0) / 15) * 100)}%` }} /></span>
          </button>
        </li>
      ))}
    </ol>
  );
}

export function CommandBoard({
  command,
  layer,
  analytics,
  weatherDays,
  narration,
  day,
  userName,
  canPlan,
  planSlugs,
  onDay,
  onOpenMap,
  onOpenWeather,
  onOpenRisk,
  onOpenPlace,
  onAddPlan,
  onAsk,
  onPresent,
}: {
  command: CommandRecord | null;
  layer: SituationRecord | null;
  analytics: AnalyticsReport | null;
  weatherDays: WeatherDayPoint[];
  narration: { source: string; text: string } | null;
  day: number;
  userName: string;
  canPlan: boolean;
  planSlugs: string[];
  onDay: (day: number) => void;
  onOpenMap: () => void;
  onOpenWeather: () => void;
  onOpenRisk: () => void;
  onOpenPlace: (slug: string) => void;
  onAddPlan: (item: CommandAction) => void;
  onAsk: (message: string) => void;
  onPresent: () => void;
}) {
  const indicators = command?.situation.indicators || [];
  const queue = (command?.priorities || []).slice(0, 6);
  const horizon = command?.horizon.areas || [];
  const ranking = analytics?.ranking || [];
  const highNow = ranking.filter((row) => classKey(row.risk_label) === "high" || classKey(row.risk_label) === "very_high").length;
  const distribution = analytics?.distribution?.rows || [];
  const current = command?.weather.current;
  const today = weatherDays.find((point) => point.day === day);
  const horizonOption: EChartsOption = {
    grid: { left: 110, right: 40, top: 6, bottom: 22 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "#fbfcf8", borderColor: "#d7e0d4", textStyle: { color: "#1c261c", fontSize: 12 } },
    xAxis: { type: "value", max: 100, axisLabel: { color: "#5d6b5e", fontSize: 11 }, splitLine: { lineStyle: { color: "#eef1eb" } } },
    yAxis: { type: "category", data: horizon.slice(0, 6).map((area) => area.name).reverse(), axisLabel: { color: "#1c261c", fontSize: 12 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [
      { name: "Now", type: "bar", barGap: "-100%", barWidth: 14, itemStyle: { color: "#d7e0d4", borderRadius: 3 }, data: horizon.slice(0, 6).map((area) => area.from_points).reverse() },
      {
        name: "+72h",
        type: "bar",
        barWidth: 4,
        z: 3,
        itemStyle: { color: (params: { dataIndex: number }) => CLASS_COLOR[classKey(horizon.slice(0, 6).reverse()[params.dataIndex]?.to_class)] },
        label: { show: true, position: "right", fontSize: 11, color: "#1c261c", fontWeight: 600 },
        data: horizon.slice(0, 6).map((area) => area.to_points).reverse(),
      },
    ],
  };

  return (
    <div className="pg cb">
      <header className="pg-head">
        <div>
          <h2><Icon name="command" size={22} />{greeting()}, {userName}</h2>
          <p>{command?.scope.label || "Nueva Ecija"} · {command?.threat.name || "Threat"} · {command?.forecast_date || "—"}</p>
        </div>
        <div className="pg-actions">
          <span className="wx-inline" aria-label="Weather for the selected day">
            <Icon name={today ? wxIcon(today) : "cloud"} size={18} />
            <b>{(current?.temp_c ?? today?.tempMean) == null ? "—" : `${(current?.temp_c ?? today?.tempMean ?? 0).toFixed(0)}°C`}</b>
            <span><Icon name="humidity" size={14} />{(current?.rh_pct ?? today?.rhMean) == null ? "—" : `${(current?.rh_pct ?? today?.rhMean ?? 0).toFixed(0)}%`}</span>
            <span><Icon name="rain" size={14} />{(current?.rain_mm ?? today?.rainMean) == null ? "—" : `${(current?.rain_mm ?? today?.rainMean ?? 0).toFixed(1)} mm`}</span>
          </span>
          <button type="button" className="btn-ghost" onClick={onOpenMap}><Icon name="map" size={16} />Map</button>
          <button type="button" className="btn" onClick={onPresent}><Icon name="slides" size={16} />Present brief</button>
        </div>
      </header>

      <ul className="stat-row" aria-label="Situation counts">
        <li data-tone="alert">
          <span>High or very high now</span>
          <b>{analytics ? highNow : "—"}<small>/{ranking.length || "—"}</small></b>
        </li>
        {indicators.map((item) => (
          <li key={item.id} title={item.detail} data-tone={item.id === "rising" ? "watch" : undefined}>
            <span>{SHORT_LABEL[item.id] || item.label}</span>
            <b>{item.value == null ? "—" : item.value}</b>
          </li>
        ))}
        <li data-tone="watch" title={command?.horizon.class_up_sentence}>
          <span>Escalating in 72h</span>
          <b>{command ? (command.horizon as { class_up?: number }).class_up ?? horizon.length : "—"}</b>
        </li>
      </ul>

      <div className="cb-main">
        <section className="cb-card cb-queue" aria-labelledby="queue-title">
          <header className="cb-cardhead">
            <h3 id="queue-title"><Icon name="target" size={17} />Inspection priority</h3>
            <button type="button" className="cb-link" onClick={onOpenRisk}>Full ranking<Icon name="arrow" size={14} /></button>
          </header>
          <div className="qtable" role="table" aria-label="Top inspection priority">
            <div className="qrow qhead" role="row">
              <span role="columnheader">#</span>
              <span role="columnheader">Municipality</span>
              <span role="columnheader">Class</span>
              <span role="columnheader">Hazard</span>
              <span role="columnheader">Trend</span>
              <span role="columnheader">Priority</span>
              <span role="columnheader"><span className="sr-only">Action</span></span>
            </div>
            {queue.length === 0 && <p className="cb-empty">{layer?.empty || "No municipality is ranked for this run."}</p>}
            {queue.map((row, index) => {
              const action = command?.actions.find((item) => item.slug === row.slug);
              const planned = planSlugs.includes(row.slug);
              const key = classKey(row.risk_label);
              return (
                <div className="qrow" role="row" key={row.slug}>
                  <span role="cell" className="qrank">{index + 1}</span>
                  <span role="cell"><button type="button" className="qname" onClick={() => onOpenPlace(row.slug)}>{row.name}</button></span>
                  <span role="cell"><ClassBadge label={row.risk_label} /></span>
                  <span role="cell" className="qbar" aria-label={`Hazard ${row.hazard_points ?? "not available"} of 100`}>
                    <i style={{ width: `${row.hazard_points ?? 0}%`, background: CLASS_COLOR[key] }} />
                    <b>{row.hazard_points ?? "—"}</b>
                  </span>
                  <span role="cell" className="qtrend" data-dir={row.trend_direction || "steady"}>
                    <Icon name={row.trend_direction === "falling" ? "falling" : "rising"} size={14} />
                    {row.trend_points == null ? "—" : `${row.trend_points > 0 ? "+" : ""}${row.trend_points}`}
                  </span>
                  <span role="cell" className="qprio">{row.priority_points ?? "—"}</span>
                  <span role="cell">
                    {canPlan && action && (
                      <button type="button" className="cb-chip" disabled={planned} onClick={() => onAddPlan(action)}>
                        <Icon name={planned ? "check" : "plus"} size={13} />{planned ? "Planned" : action.verb}
                      </button>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="cb-foot">Hazard is the rule-engine score. Priority adds rice exposure and recency; it is not a chance of disease.</p>
        </section>

        <AiPanel
          command={command}
          layer={layer}
          narration={narration}
          canPlan={canPlan}
          planSlugs={planSlugs}
          onAddPlan={onAddPlan}
          onAsk={onAsk}
          onOpenPlace={onOpenPlace}
        />
      </div>

      <div className="cb-row">
        <section className="cb-card" aria-labelledby="wk-title">
          <header className="cb-cardhead">
            <h3 id="wk-title"><Icon name="forecast" size={17} />Seven-day weather</h3>
            <button type="button" className="cb-link" onClick={onOpenWeather}>Weather desk<Icon name="arrow" size={14} /></button>
          </header>
          <WeekStrip days={weatherDays} baseDate={shiftDate(command?.forecast_date, -day)} active={day} onPick={onDay} />
        </section>
        <section className="cb-card" aria-labelledby="hz-title">
          <header className="cb-cardhead">
            <h3 id="hz-title"><Icon name="rising" size={17} />Next 72 hours</h3>
            <span className="cb-legend"><i className="is-now" />Now<i className="is-ahead" />+72h</span>
          </header>
          {horizon.length === 0
            ? <p className="cb-empty">No municipality is projected to change class inside 72 hours.</p>
            : <Chart option={horizonOption} height={210} label="Projected hazard change over 72 hours" onPick={(name) => { const hit = horizon.find((area) => area.name === name); if (hit) onOpenPlace(hit.slug); }} />}
        </section>
      </div>

      <div className="cb-row cb-row-3">
        <section className="cb-card" aria-labelledby="th-title">
          <header className="cb-cardhead">
            <h3 id="th-title"><Icon name="risk" size={17} />Threats</h3>
          </header>
          <ul className="threat-grid">
            {(analytics?.threats || []).map((row) => {
              const dist = distribution.find((item) => item.id === row.id);
              return (
                <li key={row.id}>
                  <span className="threat-ic"><Icon name={threatIcon(row.id)} size={24} /></span>
                  <div>
                    <strong>{row.name}</strong>
                    <span>{row.high_plus} high+ · {row.rising} rising</span>
                    {row.fastest_name && <button type="button" className="cb-link" onClick={() => row.fastest_slug && onOpenPlace(row.fastest_slug)}>Fastest: {row.fastest_name}{row.fastest_points != null ? ` +${row.fastest_points}` : ""}</button>}
                  </div>
                  {dist && <b className="threat-n">{dist.now}</b>}
                </li>
              );
            })}
            {!analytics && <li className="cb-empty">Loading threat summary.</li>}
          </ul>
        </section>
        <section className="cb-card" aria-labelledby="ch-title">
          <header className="cb-cardhead">
            <h3 id="ch-title"><Icon name="layers" size={17} />What changed</h3>
          </header>
          <ul className="changes">
            {(command?.changes || []).map((item) => (
              <li key={item.id} title={item.detail}>
                <Icon name={CHANGE_ICON[item.id] || "layers"} size={18} />
                <span>{SHORT_LABEL[item.id] || item.label}{item.id === "hazard-rise" ? `, ${item.label.split(", ").pop()}` : ""}</span>
                <b data-up={item.value.startsWith("+") && item.value !== "+0" ? "yes" : undefined}>{item.value}</b>
              </li>
            ))}
          </ul>
        </section>
        <section className="cb-card" aria-labelledby="dh-title">
          <header className="cb-cardhead">
            <h3 id="dh-title"><Icon name="shield" size={17} />Data health</h3>
          </header>
          <ul className="health">
            {(command?.status_bar || []).map((item) => (
              <li key={item.id} data-level={item.level}>
                <Icon name={item.id === "weather" ? "weather" : item.id === "rice" ? "rice" : item.id === "risk" ? "risk" : "layers"} size={18} />
                <span>{item.label}</span>
                <b>{item.value}</b>
              </li>
            ))}
          </ul>
          {(command?.confidence.missing.length || 0) > 0 && (
            <p className="cb-foot">Not loaded: {command?.confidence.missing.slice(0, 3).join(", ")}</p>
          )}
        </section>
      </div>
    </div>
  );
}

export function AiPanel({
  command,
  layer,
  narration,
  canPlan,
  planSlugs,
  onAddPlan,
  onAsk,
  onOpenPlace,
}: {
  command: CommandRecord | null;
  layer: SituationRecord | null;
  narration: { source: string; text: string } | null;
  canPlan: boolean;
  planSlugs: string[];
  onAddPlan: (item: CommandAction) => void;
  onAsk: (message: string) => void;
  onOpenPlace: (slug: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const summary = narration?.source === "assistant" ? narration.text : command?.situation.summary;
  const actions = (command?.actions || []).filter((item) => item.slug).slice(0, 4);
  const emerging = (layer?.emerging || []).filter((item) => item.names.length > 0).slice(0, 2);
  const prompts = (command?.prompts || layer?.prompts || []).slice(0, 4);

  function submit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message) return;
    onAsk(message);
    setDraft("");
  }

  return (
    <aside className="ai" aria-labelledby="ai-title">
      <header className="ai-head">
        <h3 id="ai-title"><Icon name="spark" size={16} />CROPWATCH Assistant</h3>
        <span className="ai-tag">{narration?.source === "assistant" ? "AI Summary" : "From the record"}</span>
      </header>
      {summary && <p className="ai-summary">{summary}</p>}

      {emerging.length > 0 && (
        <div className="ai-block">
          <h4>AI Insight · Emerging</h4>
          <ul className="ai-emerging">
            {emerging.map((item) => (
              <li key={item.label}>
                <Icon name="rising" size={14} />
                <span>{item.label}</span>
                <div>
                  {item.names.slice(0, 4).map((name, index) => (
                    <button key={name} type="button" onClick={() => item.slugs[index] && onOpenPlace(item.slugs[index])}>{name}</button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="ai-block">
        <h4>AI Recommended · Next actions</h4>
        <ol className="ai-actions">
          {actions.map((item) => {
            const planned = item.slug ? planSlugs.includes(item.slug) : false;
            return (
              <li key={item.id}>
                <span className="ai-verb" data-type={item.type}>{item.verb}</span>
                <button type="button" className="ai-place" onClick={() => item.slug && onOpenPlace(item.slug)}>{item.place}</button>
                <span className="ai-when">{item.window}</span>
                {canPlan && (
                  <button type="button" className="ai-add" disabled={planned} aria-label={planned ? `${item.place} is in the plan` : `Add ${item.place} to the plan`} onClick={() => onAddPlan(item)}>
                    <Icon name={planned ? "check" : "plus"} size={14} />
                  </button>
                )}
              </li>
            );
          })}
          {actions.length === 0 && <li className="cb-empty">No action is recommended for this run.</li>}
        </ol>
      </div>

      <div className="ai-block">
        <h4>Ask CROPWATCH</h4>
        <div className="ai-prompts">
          {prompts.map((prompt) => (
            <button key={prompt.id} type="button" onClick={() => onAsk(prompt.message)}>{prompt.label}</button>
          ))}
        </div>
        <form className="ai-ask" onSubmit={submit}>
          <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask about scores, weather, or places" aria-label="Ask CROPWATCH" />
          <button type="submit" aria-label="Send question" disabled={!draft.trim()}><Icon name="send" size={16} /></button>
        </form>
      </div>
      <p className="ai-fine">The assistant explains stored scores. It cannot change a hazard score or confirm presence of a pest or disease.</p>
    </aside>
  );
}

export function BriefingSlides({
  open,
  command,
  layer,
  analytics,
  weatherDays,
  narration,
  day,
  onClose,
  onOpenPlace,
}: {
  day: number;
  open: boolean;
  command: CommandRecord | null;
  layer: SituationRecord | null;
  analytics: AnalyticsReport | null;
  weatherDays: WeatherDayPoint[];
  narration: { source: string; text: string } | null;
  onClose: () => void;
  onOpenPlace: (slug: string) => void;
}) {
  const [index, setIndex] = useState(0);
  const ranking = analytics?.ranking || [];
  const highNow = ranking.filter((row) => classKey(row.risk_label) === "high" || classKey(row.risk_label) === "very_high").length;
  const queue = (command?.priorities || []).slice(0, 5);
  const horizon = (command?.horizon.areas || []).slice(0, 5);
  const actions = (command?.actions || []).filter((item) => item.slug).slice(0, 5);
  const distribution = analytics?.distribution?.rows || [];

  const slides: { id: string; title: string; icon: IconName; body: JSX.Element }[] = [
    {
      id: "situation",
      title: "Situation",
      icon: "command",
      body: (
        <div className="sl-situation">
          <p className="sl-lead">{narration?.source === "assistant" ? narration.text : command?.situation.summary}</p>
          <ul className="sl-big">
            <li><b>{analytics ? highNow : "—"}</b><span>High or very high municipalities</span></li>
            {(command?.situation.indicators || []).slice(0, 3).map((item) => (
              <li key={item.id}><b>{item.value ?? "—"}</b><span>{SHORT_LABEL[item.id] || item.label}</span></li>
            ))}
          </ul>
        </div>
      ),
    },
    {
      id: "distribution",
      title: "Risk distribution",
      icon: "analytics",
      body: (
        <ul className="sl-dist">
          {distribution.map((row) => {
            const total = Math.max(1, distribution.reduce((sum, item) => sum + item.now, 0));
            return (
              <li key={row.id}>
                <span>{row.label}</span>
                <i style={{ width: `${(row.now / total) * 100}%`, background: CLASS_COLOR[row.id] || "#8d9488" }} />
                <b>{row.now}</b>
                <em>{row.ahead == null ? "no +72h run" : row.ahead > row.now ? `+${row.ahead - row.now} by +72h` : row.ahead < row.now ? `${row.ahead - row.now} by +72h` : "steady"}</em>
              </li>
            );
          })}
        </ul>
      ),
    },
    {
      id: "priority",
      title: "Inspect first",
      icon: "target",
      body: (
        <ol className="sl-list">
          {queue.map((row, rank) => (
            <li key={row.slug}>
              <b>{rank + 1}</b>
              <button type="button" onClick={() => { onOpenPlace(row.slug); onClose(); }}>{row.name}</button>
              <ClassBadge label={row.risk_label} />
              <span>Hazard {row.hazard_points ?? "—"}</span>
              <span>Priority {row.priority_points ?? "—"}</span>
            </li>
          ))}
        </ol>
      ),
    },
    {
      id: "horizon",
      title: "Next 72 hours",
      icon: "rising",
      body: (
        <ol className="sl-list">
          {horizon.map((area) => (
            <li key={area.slug}>
              <Icon name="rising" size={20} />
              <button type="button" onClick={() => { onOpenPlace(area.slug); onClose(); }}>{area.name}</button>
              <ClassBadge label={area.from_class} />
              <Icon name="arrow" size={16} />
              <ClassBadge label={area.to_class} />
              <span>{area.from_points} → {area.to_points}</span>
            </li>
          ))}
          {horizon.length === 0 && <li>No municipality is projected to change class inside 72 hours.</li>}
        </ol>
      ),
    },
    {
      id: "weather",
      title: "Weather outlook",
      icon: "weather",
      body: (
        <div>
          <WeekStrip days={weatherDays} baseDate={shiftDate(command?.forecast_date, -day)} active={day} />
          {layer?.weather?.sentence && <p className="sl-note">{layer.weather.sentence}</p>}
        </div>
      ),
    },
    {
      id: "actions",
      title: "Recommended actions",
      icon: "inspect",
      body: (
        <ol className="sl-list">
          {actions.map((item) => (
            <li key={item.id}>
              <span className="ai-verb" data-type={item.type}>{item.verb}</span>
              <strong>{item.place}</strong>
              <span>{item.window}</span>
            </li>
          ))}
          {actions.length === 0 && <li>No action is recommended for this run.</li>}
        </ol>
      ),
    },
  ];

  useEffect(() => {
    if (!open) return;
    setIndex(0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight") setIndex((current) => Math.min(slides.length - 1, current + 1));
      if (event.key === "ArrowLeft") setIndex((current) => Math.max(0, current - 1));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, slides.length]);

  if (!open) return null;
  const slide = slides[index];
  return (
    <div className="sl" role="dialog" aria-modal="true" aria-labelledby="sl-title">
      <div className="sl-frame">
        <header className="sl-head">
          <p><Icon name="rice" size={18} />CROPWATCH briefing · {command?.scope.label || "Nueva Ecija"} · {command?.threat.name} · {command?.forecast_date}</p>
          <button type="button" className="sl-close" onClick={onClose} aria-label="Close briefing"><Icon name="close" size={18} /></button>
        </header>
        <section className="sl-body" key={slide.id}>
          <h2 id="sl-title"><span className="sl-ic"><Icon name={slide.icon} size={26} /></span>{slide.title}</h2>
          {slide.body}
        </section>
        <footer className="sl-nav">
          <button type="button" onClick={() => setIndex((current) => Math.max(0, current - 1))} disabled={index === 0} aria-label="Previous slide"><Icon name="prev" size={18} /></button>
          <ol aria-label="Slides">
            {slides.map((item, position) => (
              <li key={item.id}>
                <button type="button" aria-current={position === index ? "step" : undefined} onClick={() => setIndex(position)}>{item.title}</button>
              </li>
            ))}
          </ol>
          <button type="button" onClick={() => setIndex((current) => Math.min(slides.length - 1, current + 1))} disabled={index === slides.length - 1} aria-label="Next slide"><Icon name="next" size={18} /></button>
        </footer>
      </div>
    </div>
  );
}
