"use client";

import { useState } from "react";
import { ClassBadge, classKey } from "./command-board";
import { Icon, IconName, threatIcon } from "./icons";
import { PageHead, Score } from "./workspaces";

type Metric = { id: string; label: string; value?: number | null; unit?: string; display: string; source: string | null; period: string | null; retrieved_on: string | null };
type Profile = {
  slug: string;
  name: string;
  hazard_points: number | null;
  priority_points: number | null;
  risk_label: string | null;
  trend_arrow: string;
  trend_direction: string | null;
  trend_points: number | null;
  rice_label: string;
  rice_source?: string | null;
  crop_stage: { available: boolean; days: number | null; sentence: string };
  horizon?: { from_points: number | null; to_points: number | null; to_class?: string | null } | null;
  factors?: { id?: string; label: string; status: string }[];
  action_label: string | null;
};
type Question = { id: string; prompt: string; answer: string };

export type RiceReport = {
  boundary: string;
  period_note: string;
  barangay_note?: string;
  scope: { label: string; can_plan: boolean };
  threat: { name: string };
  situation: { place: string; scope_note: string; metrics: Metric[] };
  exposure: { label: string; sentence: string };
  profiles: Profile[];
  crop: { available?: boolean; sentence: string; rule_note: string; approaching: { name: string; days: number | null; sentence: string }[] };
  conditions: {
    weather: { available: boolean; temp_c: number | null; rain_mm: number | null; rh_pct: number | null; soil_moisture: number | null; source: string | null; date: string | null; note: string };
    satellite: { available: boolean; ndvi: number | null; evi: number | null; ndwi: number | null; lswi: number | null; flood_fraction: number | null; rice_fraction: number | null; ndvi_change: number | null; observed_on: string | null; note: string };
    water_note: string;
    drivers: string[];
    driver_note: string;
  };
  climate: {
    season_label: string;
    season_sentence: string;
    modifier_threats: string[];
    threat_sentence: string;
    enso: { sentence: string; anomaly_c?: number | null; label?: string | null; season?: string | null; source?: string | null };
  };
  risk_context: {
    available: boolean;
    name?: string;
    threat?: string;
    hazard_points?: number | null;
    priority_points?: number | null;
    risk_label?: string | null;
    trend_direction?: string | null;
    trend_points?: number | null;
    rice_label?: string;
    crop_sentence?: string;
    outlook?: string;
    favorable_factors?: string[];
    surveillance?: string;
    action_label?: string | null;
    sentence: string;
  };
  actions: { type: string; type_label: string; slug: string; name: string; hazard_points: number | null; priority_points: number | null }[];
  coverage: { dataset: string; status: string; period: string | null; source: string | null }[];
  questions: Question[];
  summary_lines: string[];
};

const CLASS_COLOR: Record<string, string> = { low: "#3d8c4e", moderate: "#d89a12", high: "#e15a1c", very_high: "#c62828", insufficient_data: "#8d9488" };
const METRIC_ICON: Record<string, IconName> = { farmers: "farmer", harvested_area: "field", production: "rice", yield: "analytics" };
const STAGES = ["Planting", "Vegetative", "Tillering", "Heading", "Maturity", "Harvest"];
const FACTOR_SHORT: Record<string, string> = {
  temperature: "Temp",
  humidity: "Humidity",
  recent_rain: "Rain 7d",
  forecast_rain: "Rain ahead",
  spread: "Spread",
  nitrogen_variety: "N / variety",
  climate: "Season",
  leaf_wetness: "Leaf wet",
  wind: "Wind",
  crop_stage: "Stage",
};

function splitDisplay(metric: Metric) {
  const [number, ...rest] = metric.display.split(" ");
  return { number, unit: rest.join(" ") || metric.unit || "" };
}

function fmt(value: number | null | undefined, digits = 1, unit = "") {
  if (value == null) return "—";
  return `${value.toLocaleString("en-PH", { maximumFractionDigits: digits, minimumFractionDigits: digits })}${unit}`;
}

export default function RiceView({
  report,
  loading,
  error,
  narration,
  onOpenPlace,
  onAddPlan,
  onRetry,
}: {
  report: RiceReport | null;
  loading: boolean;
  error: string;
  narration: string | null;
  onOpenPlace: (slug: string) => void;
  onAddPlan: (item: { slug: string; name: string }) => void;
  onRetry: () => void;
}) {
  const [showAll, setShowAll] = useState(false);
  if (!report) {
    return (
      <div className="pg" id="rice">
        <PageHead icon="rice" title="Rice" />
        {loading && <p className="empty-line">Loading the rice context.</p>}
        {error && <p className="error" role="alert">{error} <button className="btn-sm" type="button" onClick={onRetry}>Try again</button></p>}
      </div>
    );
  }
  const profiles = [...report.profiles].sort((left, right) => (right.priority_points ?? -1) - (left.priority_points ?? -1));
  const shown = showAll ? profiles : profiles.slice(0, 10);
  const factorIds = Array.from(new Set(profiles.flatMap((row) => (row.factors || []).map((factor) => factor.id || factor.label))));
  const factorLabel = (id: string) => FACTOR_SHORT[id] || profiles.flatMap((row) => row.factors || []).find((factor) => (factor.id || factor.label) === id)?.label || id;
  const weather = report.conditions.weather;
  const sat = report.conditions.satellite;
  const enso = report.climate.enso;
  const source = report.situation.metrics[0]?.source;

  return (
    <div className="pg" id="rice">
      <PageHead icon="rice" title={`Rice · ${report.situation.place}`} meta={`${report.threat.name} context · ${report.scope.label}`} />

      <section className="figs-band" aria-label="Rice industry figures">
        <ul className="figs big">
          {report.situation.metrics.map((metric) => {
            const { number, unit } = splitDisplay(metric);
            return (
              <li key={metric.id}>
                <span className="fig-label"><Icon name={METRIC_ICON[metric.id] || "rice"} size={16} />{metric.label}</span>
                <b>{number}</b>
                <span className="fig-unit">{unit}</span>
                <small>{metric.period}</small>
              </li>
            );
          })}
        </ul>
        {source && <p className="src">Source: {source}{report.situation.metrics[0]?.retrieved_on ? ` · retrieved ${report.situation.metrics[0].retrieved_on}` : ""}</p>}
      </section>

      {narration && (
        <section className="ai-note" aria-label="AI summary">
          <span className="ai-tag"><Icon name="spark" size={13} />AI Summary</span>
          <p>{narration}</p>
        </section>
      )}

      <div className="pg-split wide-left">
        <section className="panel-card" aria-labelledby="rr-title">
          <header className="panel-head">
            <h3 id="rr-title"><Icon name={threatIcon(report.threat.name)} size={17} />{report.threat.name} on rice municipalities</h3>
            <span className="count">{profiles.length}</span>
          </header>
          <div className="tbl" role="table" aria-label="Municipality rice risk">
            <div className="tr th rice-tr" role="row">
              <span role="columnheader">Municipality</span>
              <span role="columnheader">Class</span>
              <span role="columnheader" className="num">Hazard</span>
              <span role="columnheader" className="num">Trend</span>
              <span role="columnheader" className="num">Priority</span>
              <span role="columnheader" className="num">+72h</span>
            </div>
            {shown.map((row) => (
              <div className="tr rice-tr" role="row" key={row.slug}>
                <span role="cell"><button type="button" className="cell-link" onClick={() => onOpenPlace(row.slug)}>{row.name}</button></span>
                <span role="cell"><ClassBadge label={row.risk_label} /></span>
                <span role="cell" className="num"><Score value={row.hazard_points} label="Hazard" tone={CLASS_COLOR[classKey(row.risk_label)]} /></span>
                <span role="cell" className="num trend" data-dir={row.trend_direction || ""}>{row.trend_points == null ? "—" : `${row.trend_points > 0 ? "+" : ""}${row.trend_points}`}</span>
                <span role="cell" className="num strong">{row.priority_points ?? "—"}</span>
                <span role="cell" className="num muted">{row.horizon?.to_points ?? "—"}</span>
              </div>
            ))}
          </div>
          {profiles.length > 10 && (
            <button type="button" className="btn-ghost center" onClick={() => setShowAll((current) => !current)}>{showAll ? "Show top 10" : `Show all ${profiles.length}`}</button>
          )}
        </section>

        <div className="pg-col">
          <section className="panel-card" aria-labelledby="cl-title">
            <header className="panel-head"><h3 id="cl-title"><Icon name="sun" size={17} />Season and climate</h3></header>
            <dl className="facts two">
              <div><dt>Season</dt><dd>{report.climate.season_label}</dd></div>
              <div><dt>ENSO · {enso.season || "latest"}</dt><dd>{enso.label || "—"}</dd></div>
              <div><dt>Oceanic Niño Index</dt><dd className="num">{enso.anomaly_c == null ? "—" : `${enso.anomaly_c > 0 ? "+" : ""}${enso.anomaly_c.toFixed(2)} °C`}</dd></div>
              <div><dt>Modifier used by</dt><dd className="chips">{report.climate.modifier_threats.length ? report.climate.modifier_threats.map((name) => <span key={name} className="chip"><Icon name={threatIcon(name)} size={13} />{name}</span>) : "—"}</dd></div>
            </dl>
          </section>

          <section className="panel-card" aria-labelledby="cc-title">
            <header className="panel-head"><h3 id="cc-title"><Icon name="calendar" size={17} />Crop calendar</h3></header>
            <ol className="stages" data-available={report.crop.available === false ? "no" : "yes"} aria-label="Crop stages">
              {STAGES.map((stage) => <li key={stage}>{stage}</li>)}
            </ol>
            {report.crop.available === false
              ? <p className="muted small">No planting date stored · stage cannot be shown</p>
              : report.crop.approaching.map((row) => <p key={row.name} className="small"><strong>{row.name}</strong> · {row.days} days after planting</p>)}
          </section>

          <section className="panel-card" aria-labelledby="cd-title">
            <header className="panel-head"><h3 id="cd-title"><Icon name="weather" size={17} />Field conditions</h3><span className="muted small">{weather.date || ""}</span></header>
            <ul className="mini-tiles">
              <li><Icon name="temp" size={18} /><b>{weather.available ? fmt(weather.temp_c, 1, "°C") : "—"}</b><span>Temperature</span></li>
              <li><Icon name="rain" size={18} /><b>{weather.available ? fmt(weather.rain_mm, 1, " mm") : "—"}</b><span>Rainfall</span></li>
              <li><Icon name="humidity" size={18} /><b>{weather.available ? fmt(weather.rh_pct, 0, "%") : "—"}</b><span>Humidity</span></li>
              <li><Icon name="soil" size={18} /><b>{fmt(weather.soil_moisture, 2)}</b><span>Soil moisture</span></li>
            </ul>
            <ul className="mini-tiles sat" data-available={sat.available ? "yes" : "no"}>
              {([["NDVI", sat.ndvi], ["EVI", sat.evi], ["NDWI", sat.ndwi], ["LSWI", sat.lswi], ["Flood", sat.flood_fraction], ["Rice frac.", sat.rice_fraction]] as const).map(([label, value]) => (
                <li key={label}><b>{fmt(value, 2)}</b><span>{label}</span></li>
              ))}
            </ul>
            {!sat.available && <p className="muted small">Satellite indices not loaded</p>}
          </section>
        </div>
      </div>

      {factorIds.length > 0 && (
        <section className="panel-card" aria-labelledby="fm-title">
          <header className="panel-head">
            <h3 id="fm-title"><Icon name="layers" size={17} />Rule factors by municipality</h3>
            <p className="legend-row">
              {["Favorable", "Neutral", "Low", "Estimated", "Not available"].map((status) => <span key={status}><i data-status={status} />{status}</span>)}
            </p>
          </header>
          <div className="fmatrix" style={{ gridTemplateColumns: `minmax(150px, 1.4fr) repeat(${factorIds.length}, minmax(64px, 1fr))` }} role="table" aria-label="Factor status by municipality">
            <span className="fm-h" role="columnheader">Municipality</span>
            {factorIds.map((id) => <span key={id} className="fm-h" role="columnheader" title={factorLabel(id)}>{factorLabel(id)}</span>)}
            {shown.map((row) => (
              <div className="fm-row" role="row" key={row.slug}>
                <span role="rowheader" className="fm-name">{row.name}</span>
                {factorIds.map((id) => {
                  const factor = (row.factors || []).find((item) => (item.id || item.label) === id);
                  const status = factor?.status || "Not available";
                  return <span key={id} role="cell" className="fm-cell" data-status={status} title={`${row.name} · ${factor?.label || id}: ${status}`}><span className="sr-only">{status}</span></span>;
                })}
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="pg-split">
        {report.actions.length > 0 && (
          <section className="panel-card" aria-labelledby="ra-title">
            <header className="panel-head"><h3 id="ra-title"><Icon name="inspect" size={17} />Suggested visits</h3><span className="count">{report.actions.length}</span></header>
            <ul className="stop-list plain">
              {report.actions.map((action) => (
                <li key={`${action.type}-${action.slug}`}>
                  <div className="row-line">
                    <span className="verb" data-type={action.type}>{action.type_label}</span>
                    <button type="button" className="cell-link" onClick={() => onOpenPlace(action.slug)}>{action.name}</button>
                    <span className="num muted">H {action.hazard_points ?? "—"} · P {action.priority_points ?? "—"}</span>
                    {report.scope.can_plan && (
                      <button type="button" className="btn-sm" onClick={() => onAddPlan({ slug: action.slug, name: action.name })}><Icon name="plus" size={14} />Add</button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="panel-card" aria-labelledby="rq-title">
          <header className="panel-head"><h3 id="rq-title"><Icon name="assistant" size={17} />Common questions</h3></header>
          <div className="faq">
            {report.questions.map((item) => (
              <details key={item.id}>
                <summary>{item.prompt}</summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>
      </div>

      <section className="panel-card" aria-labelledby="rc-title">
        <header className="panel-head"><h3 id="rc-title"><Icon name="shield" size={17} />Data coverage</h3></header>
        <ul className="coverage">
          {report.coverage.map((row) => (
            <li key={row.dataset} data-ok={row.status === "Available" ? "yes" : "no"} title={row.source || undefined}>
              <Icon name={row.status === "Available" ? "check" : "close"} size={14} />
              <span>{row.dataset}</span>
              <small>{row.period || row.status}</small>
            </li>
          ))}
        </ul>
        <p className="src">{report.period_note}</p>
      </section>
    </div>
  );
}
