"use client";

import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ImageReading, NoteReading, ObservationAssist } from "./situation";
import type { AnalyticsReport } from "./analytics-view";
import type { CommandRecord } from "./command-center";
import type { RiceReport } from "./rice-view";
import { ClassBadge, classKey } from "./command-board";
import { Icon, IconName } from "./icons";

export type FieldStatus = "listed" | "planned" | "routed" | "in_progress" | "observed" | "validated" | "follow_up";

export type FieldStop = {
  slug: string;
  name: string;
  threat: string;
  reason: string;
  hazard: number | null;
  priority: number | null;
  status: FieldStatus;
  note: string;
  observedAt: string | null;
  checks: boolean[];
};

export const FIELD_CHECKS = [
  "Location matches the listed municipality",
  "Observed weather is written down, and is not called a sensor reading",
  "Crop stage is written down only when it can be seen",
  "Standing water is written down only when it can be seen",
  "A pest or disease is recorded only after it is seen in the field",
];

const STAGES: { id: FieldStatus; label: string }[] = [
  { id: "listed", label: "Listed" },
  { id: "planned", label: "Planned" },
  { id: "routed", label: "Routed" },
  { id: "in_progress", label: "In field" },
  { id: "observed", label: "Observed" },
  { id: "validated", label: "Validated" },
  { id: "follow_up", label: "Follow-up" },
];

const STATUS_LABEL: Record<FieldStatus, string> = {
  listed: "Listed",
  planned: "Planned",
  routed: "Route created",
  in_progress: "In progress",
  observed: "Observation submitted",
  validated: "Validated",
  follow_up: "Follow-up required",
};

const CLASS_COLOR: Record<string, string> = {
  low: "#3d8c4e",
  moderate: "#d89a12",
  high: "#e15a1c",
  very_high: "#c62828",
  insufficient_data: "#8d9488",
};

export function Score({ value, label, tone }: { value: number | null; label: string; tone?: string }) {
  return (
    <span className="score" aria-label={`${label} ${value ?? "not available"} of 100`}>
      <span className="score-track"><i style={{ width: `${value ?? 0}%`, background: tone || "#173226" }} /></span>
      <b>{value ?? "—"}</b>
    </span>
  );
}

export function PageHead({ icon, title, meta, children }: { icon: IconName; title: string; meta?: string; children?: ReactNode }) {
  return (
    <header className="pg-head">
      <div>
        <h2><Icon name={icon} size={22} />{title}</h2>
        {meta && <p>{meta}</p>}
      </div>
      {children && <div className="pg-actions">{children}</div>}
    </header>
  );
}

type RouteInfo = { stops?: string[]; distance_km?: number | null; note?: string } | null;

export function FieldOperations({
  command,
  stops,
  canPlan,
  route,
  active,
  onOpen,
  onAdd,
  onAdvance,
  onNote,
  onCheck,
  onSelect,
  onShowMap,
  onReadNote,
  onReviewImage,
  routeReading,
}: {
  command: CommandRecord | null;
  stops: FieldStop[];
  canPlan: boolean;
  route: RouteInfo;
  active: string | null;
  onOpen: (slug: string) => void;
  onAdd: (stop: FieldStop) => void;
  onAdvance: (slug: string, status: FieldStatus) => void;
  onNote: (slug: string, note: string) => void;
  onCheck: (slug: string, index: number) => void;
  onSelect: (slug: string) => void;
  onShowMap: () => void;
  onReadNote?: (body: string) => Promise<NoteReading>;
  onReviewImage?: (file: File) => Promise<ImageReading>;
  routeReading?: { sentence: string; evidence: string[] } | null;
}) {
  const recommended = (command?.actions || []).filter((item) => item.slug && item.place);
  const selected = stops.find((item) => item.slug === active) || stops[0] || null;
  const ordered = [...stops].sort((left, right) => statusRank(left.status) - statusRank(right.status) || left.name.localeCompare(right.name));
  const routeStops = stops.filter((item) => ["routed", "in_progress", "observed", "validated", "follow_up"].includes(item.status));
  const counts = STAGES.map((stage) => ({ ...stage, count: stops.filter((stop) => stop.status === stage.id).length }));
  const done = selected ? selected.checks.filter(Boolean).length : 0;

  return (
    <div className="pg" id="operations">
      <PageHead icon="operations" title="Field operations" meta={`${command?.scope.label || "Nueva Ecija"} · ${command?.threat.name || "Threat"} · ${command?.forecast_date || ""}`}>
        <button type="button" className="btn" disabled={stops.length === 0} onClick={onShowMap}><Icon name="map" size={16} />Show stops on map</button>
      </PageHead>

      <ol className="pipeline" aria-label="Visits by stage">
        <li data-stage="recommended"><b>{recommended.length}</b><span>Recommended</span></li>
        {counts.map((stage) => (
          <li key={stage.id} data-stage={stage.id} data-empty={stage.count === 0 ? "yes" : undefined}><b>{stage.count}</b><span>{stage.label}</span></li>
        ))}
      </ol>
      {!canPlan && <p className="pg-note"><Icon name="shield" size={14} />Read-only account. Adding places, notes, and validation is disabled.</p>}

      <div className="pg-split wide-left">
        <div className="pg-col">
          <section className="panel-card" aria-labelledby="rec-title">
            <header className="panel-head"><h3 id="rec-title">Recommended visits</h3><span className="count">{recommended.length}</span></header>
            {recommended.length === 0 ? <p className="empty-line">No recommended place for this run.</p> : (
              <div className="tbl" role="table" aria-label="Recommended visits">
                <div className="tr th" role="row">
                  <span role="columnheader">Municipality</span>
                  <span role="columnheader">Class</span>
                  <span role="columnheader" className="num">Hazard</span>
                  <span role="columnheader" className="num">Priority</span>
                  <span role="columnheader">Window</span>
                  <span role="columnheader"><span className="sr-only">Action</span></span>
                </div>
                {recommended.map((item) => {
                  const listed = stops.some((stop) => stop.slug === item.slug);
                  return (
                    <div className="tr" role="row" key={item.id}>
                      <span role="cell"><button type="button" className="cell-link" onClick={() => onOpen(item.slug || "")}>{item.place}</button><small>{item.type_label}</small></span>
                      <span role="cell"><ClassBadge label={item.risk_label} /></span>
                      <span role="cell" className="num"><Score value={item.hazard_points} label="Hazard" tone={CLASS_COLOR[classKey(item.risk_label)]} /></span>
                      <span role="cell" className="num strong">{item.priority_points ?? "—"}</span>
                      <span role="cell" className="muted">{item.window}</span>
                      <span role="cell" className="end">
                        {canPlan && (
                          <button type="button" className="btn-sm" disabled={listed} onClick={() => onAdd(stopFromAction(item))}>
                            <Icon name={listed ? "check" : "plus"} size={14} />{listed ? "Listed" : "Add"}
                          </button>
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="panel-card" aria-labelledby="list-title">
            <header className="panel-head"><h3 id="list-title">Inspection list</h3><span className="count">{stops.length}</span></header>
            {ordered.length === 0 ? <p className="empty-line">Add a recommended visit to start the list.</p> : (
              <ul className="stop-list">
                {ordered.map((stop) => (
                  <li key={stop.slug}>
                    <button type="button" aria-pressed={selected?.slug === stop.slug} onClick={() => onSelect(stop.slug)}>
                      <span className="stop-name">{stop.name}<small>{stop.threat}</small></span>
                      <span className="stage-chip" data-stage={stop.status}>{STATUS_LABEL[stop.status]}</span>
                      <span className="num muted">H {stop.hazard ?? "—"} · P {stop.priority ?? "—"}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <section className="panel-card visit" aria-labelledby="visit-title">
          {!selected ? (
            <div className="empty-state">
              <Icon name="inspect" size={28} />
              <h3 id="visit-title">No visit selected</h3>
              <p>Add a place from Recommended visits.</p>
            </div>
          ) : (
            <>
              <header className="visit-head">
                <div>
                  <h3 id="visit-title">{selected.name}</h3>
                  <p>{selected.threat}</p>
                </div>
                <button type="button" className="btn-ghost" onClick={() => onOpen(selected.slug)}><Icon name="map" size={15} />Map</button>
              </header>
              <ol className="stepper" aria-label="Visit progress">
                {STAGES.filter((stage) => stage.id !== "follow_up").map((stage) => {
                  const position = statusRank(stage.id);
                  const current = statusRank(selected.status === "follow_up" ? "validated" : selected.status);
                  return <li key={stage.id} data-state={position < current ? "done" : position === current ? "current" : "todo"}><i aria-hidden="true" /><span>{stage.label}</span></li>;
                })}
              </ol>
              <dl className="facts">
                <div><dt>Hazard</dt><dd className="num">{selected.hazard ?? "—"}<small>/100</small></dd></div>
                <div><dt>Priority</dt><dd className="num">{selected.priority ?? "—"}<small>/100</small></dd></div>
                <div><dt>Status</dt><dd><span className="stage-chip" data-stage={selected.status}>{STATUS_LABEL[selected.status]}</span></dd></div>
                <div><dt>Observed</dt><dd>{selected.observedAt || "—"}</dd></div>
              </dl>

              {routeStops.length > 0 && (
                <div className="visit-block">
                  <h4><Icon name="route" size={15} />Stop order</h4>
                  <ol className="route-chain">{routeStops.map((stop) => <li key={stop.slug}>{stop.name}</li>)}</ol>
                  {route?.distance_km ? <p className="muted small">{route.distance_km} km across shared borders</p> : null}
                </div>
              )}
              {routeReading && routeReading.evidence.length > 0 && (
                <details className="visit-more">
                  <summary>Why this route</summary>
                  <ul>{routeReading.evidence.map((line) => <li key={line}>{line}</li>)}</ul>
                </details>
              )}

              <div className="visit-block">
                <h4><Icon name="check" size={15} />Field checklist <span className="count">{done}/{FIELD_CHECKS.length}</span></h4>
                <span className="progress" aria-hidden="true"><i style={{ width: `${(done / FIELD_CHECKS.length) * 100}%` }} /></span>
                <ul className="checks">
                  {FIELD_CHECKS.map((label, index) => (
                    <li key={label}>
                      <label>
                        <input type="checkbox" checked={Boolean(selected.checks[index])} disabled={!canPlan} onChange={() => onCheck(selected.slug, index)} />
                        <span>{label}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="visit-block">
                <label className="field-label" htmlFor="visit-note">Field note</label>
                <textarea id="visit-note" value={selected.note} rows={3} disabled={!canPlan} placeholder="What was seen at the site" onChange={(event) => onNote(selected.slug, event.target.value)} />
                {onReadNote && onReviewImage && (
                  <ObservationAssist note={selected.note} placeName={selected.name} disabled={!canPlan} onRead={onReadNote} onReviewImage={onReviewImage} />
                )}
              </div>

              {canPlan && (
                <footer className="visit-actions">
                  {selected.status === "observed" && <button type="button" className="btn-ghost" onClick={() => onAdvance(selected.slug, "follow_up")}>Needs follow-up</button>}
                  {selected.status === "listed" && <button type="button" className="btn-ghost" onClick={() => onAdvance(selected.slug, "planned")}>Mark planned</button>}
                  {(selected.status === "listed" || selected.status === "planned") && <button type="button" className="btn" onClick={() => onAdvance(selected.slug, "routed")}>Create route</button>}
                  {selected.status === "routed" && <button type="button" className="btn" onClick={() => onAdvance(selected.slug, "in_progress")}>Start visit</button>}
                  {selected.status === "in_progress" && <button type="button" className="btn" disabled={!selected.note.trim()} onClick={() => onAdvance(selected.slug, "observed")}>Submit observation</button>}
                  {selected.status === "observed" && <button type="button" className="btn" onClick={() => onAdvance(selected.slug, "validated")}>Mark validated</button>}
                </footer>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function stopFromAction(item: CommandRecord["actions"][number]): FieldStop {
  return {
    slug: item.slug || "",
    name: item.place || "",
    threat: item.threat,
    reason: item.recommendation,
    hazard: item.hazard_points,
    priority: item.priority_points,
    status: "listed",
    note: "",
    observedAt: null,
    checks: FIELD_CHECKS.map(() => false),
  };
}

function statusRank(status: FieldStatus) {
  return ["listed", "planned", "routed", "in_progress", "observed", "validated", "follow_up"].indexOf(status);
}

type AlertRow = {
  id: string;
  type: string;
  severity: string;
  timestamp: string;
  location: string;
  slug: string | null;
  threat: string;
  changed: string;
  why: string;
  next: string;
};

const CLASS_RANK: Record<string, number> = { low: 0, moderate: 1, high: 2, very_high: 3 };

const ALERT_ICON: Record<string, IconName> = {
  "Material Hazard Increase": "rising",
  "Forecast Threshold Crossing": "forecast",
  "Risk Class Increased": "risk",
  "New Very High Area": "alerts",
  "Threat-Relevant Weather Change": "rain",
  "Important Data Missing": "layers",
  "Field Validation Submitted": "check",
  "Follow-up Required": "inspect",
};

const SEVERITIES = ["High", "Watch", "Data", "Info"] as const;

export function AlertsInbox({
  command,
  analytics,
  stops,
  onOpen,
  onOpenOperations,
}: {
  command: CommandRecord | null;
  analytics: AnalyticsReport | null;
  stops: FieldStop[];
  onOpen: (slug: string) => void;
  onOpenOperations: () => void;
}) {
  const rows = buildAlerts(command, analytics, stops);
  const [filter, setFilter] = useState<string>("All");
  const shown = filter === "All" ? rows : rows.filter((row) => row.severity === filter);
  return (
    <div className="pg" id="alerts">
      <PageHead icon="alerts" title="Alerts" meta={`${command?.threat.name || "Threat"} · ${command?.forecast_date || ""} · from score changes, forecasts, data gaps, and field results`} />
      <div className="seg" role="tablist" aria-label="Severity">
        {(["All", ...SEVERITIES] as string[]).map((level) => {
          const count = level === "All" ? rows.length : rows.filter((row) => row.severity === level).length;
          return (
            <button key={level} type="button" role="tab" aria-selected={filter === level} data-sev={level} onClick={() => setFilter(level)}>
              {level}<span className="count">{count}</span>
            </button>
          );
        })}
      </div>
      {shown.length === 0 ? (
        <div className="panel-card empty-state"><Icon name="check" size={28} /><h3>No alerts</h3><p>Nothing in this group for the selected threat and day.</p></div>
      ) : (
        <ul className="alerts">
          {shown.map((row) => (
            <li key={row.id} data-sev={row.severity}>
              <span className="al-ic" aria-hidden="true"><Icon name={ALERT_ICON[row.type] || "alerts"} size={18} /></span>
              <div className="al-main">
                <p className="al-title"><strong>{row.location}</strong><span className="sev" data-sev={row.severity}>{row.severity}</span></p>
                <p className="al-type">{row.type}</p>
                <p className="al-change">{row.changed}</p>
                <details>
                  <summary>Why and next step</summary>
                  <dl>
                    <dt>Why</dt><dd>{row.why}</dd>
                    <dt>Next</dt><dd>{row.next}</dd>
                  </dl>
                </details>
              </div>
              <div className="al-side">
                <time>{row.timestamp}</time>
                {row.slug && <button type="button" className="btn-sm" onClick={() => onOpen(row.slug || "")}><Icon name="map" size={14} />Open</button>}
                {(row.type === "Field Validation Submitted" || row.type === "Follow-up Required") && (
                  <button type="button" className="btn-sm" onClick={onOpenOperations}><Icon name="operations" size={14} />Visit</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function buildAlerts(command: CommandRecord | null, analytics: AnalyticsReport | null, stops: FieldStop[]): AlertRow[] {
  if (!command) return [];
  const threat = command.threat.name;
  const when = command.updated_at ? new Date(command.updated_at).toLocaleString("en-PH", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : command.forecast_date || "Time not stored";
  const rows: AlertRow[] = [];
  for (const area of command.horizon.areas) {
    const rise = area.to_points - area.from_points;
    const from = CLASS_RANK[classKey(area.from_class)] ?? -1;
    const to = CLASS_RANK[classKey(area.to_class)] ?? -1;
    if (to > from && from >= 0) {
      rows.push({
        id: `class-${area.slug}`,
        type: classKey(area.to_class) === "very_high" ? "New Very High Area" : "Risk Class Increased",
        severity: classKey(area.to_class) === "very_high" ? "High" : "Watch",
        timestamp: when,
        location: area.name,
        slug: area.slug,
        threat,
        changed: `${area.from_class} → ${area.to_class} · hazard ${area.from_points} → ${area.to_points} by +${command.horizon.hours || 72}h`,
        why: command.horizon.driver || "The forecast class is higher than the class on the selected day.",
        next: "Open the location and read the stored factors. This is a forecast class change, not a detection.",
      });
    } else if (rise >= 3) {
      rows.push({
        id: `rise-${area.slug}`,
        type: "Material Hazard Increase",
        severity: rise >= 8 ? "High" : "Watch",
        timestamp: when,
        location: area.name,
        slug: area.slug,
        threat,
        changed: `Hazard ${area.from_points} → ${area.to_points} (+${rise}) by +${command.horizon.hours || 72}h`,
        why: "The stored forecast score is at least 3 points above the selected day.",
        next: "Decide whether it belongs on the inspection list.",
      });
    }
  }
  const rain = command.changes.find((item) => item.id === "rain");
  if (rain) {
    rows.push({
      id: "weather-rain",
      type: "Threat-Relevant Weather Change",
      severity: "Watch",
      timestamp: when,
      location: command.scope.label,
      slug: null,
      threat,
      changed: `Rainfall ${rain.value} on later forecast days`,
      why: rain.detail,
      next: "Open the rainfall layer on the map.",
    });
  }
  for (const action of command.actions.filter((item) => item.type === "data_required")) {
    rows.push({
      id: action.id,
      type: "Important Data Missing",
      severity: "Data",
      timestamp: when,
      location: action.place || command.scope.label,
      slug: action.slug,
      threat,
      changed: action.recommendation,
      why: action.why.join(" ") || "A required input is missing from the stored record.",
      next: "Review the data gap before treating the score as complete.",
    });
  }
  for (const gap of command.confidence.missing) {
    rows.push({
      id: `gap-${gap}`,
      type: "Important Data Missing",
      severity: "Data",
      timestamp: when,
      location: command.scope.label,
      slug: null,
      threat,
      changed: `${gap} not loaded`,
      why: "The score leaves this input out.",
      next: "Read data coverage before comparing places.",
    });
  }
  for (const move of analytics?.transitions?.notable || []) {
    rows.push({
      id: `matrix-${move.from_label}-${move.to_label}`,
      type: "Risk Class Increased",
      severity: "Watch",
      timestamp: when,
      location: `${move.count} ${move.count === 1 ? "municipality" : "municipalities"}`,
      slug: null,
      threat,
      changed: `${move.from_label} → ${move.to_label}`,
      why: "Counted from the stored transition matrix.",
      next: "Open Analytics to see the transition matrix.",
    });
  }
  for (const stop of stops) {
    if (stop.status === "observed" || stop.status === "validated") {
      rows.push({
        id: `obs-${stop.slug}`,
        type: "Field Validation Submitted",
        severity: "Info",
        timestamp: stop.observedAt || "This session",
        location: stop.name,
        slug: stop.slug,
        threat: stop.threat,
        changed: stop.note || "Observation submitted",
        why: "An officer submitted a field note in this session.",
        next: "Compare it with the stored hazard context.",
      });
    }
    if (stop.status === "follow_up") {
      rows.push({
        id: `follow-${stop.slug}`,
        type: "Follow-up Required",
        severity: "Watch",
        timestamp: stop.observedAt || "This session",
        location: stop.name,
        slug: stop.slug,
        threat: stop.threat,
        changed: "Visit marked follow-up required",
        why: stop.note || stop.reason,
        next: "Keep the place on the inspection list.",
      });
    }
  }
  const order: Record<string, number> = { High: 0, Watch: 1, Info: 2, Data: 3 };
  return rows.sort((left, right) => (order[left.severity] ?? 9) - (order[right.severity] ?? 9));
}

const REPORTS = [
  ["provincial", "Provincial situation", "hall"],
  ["municipality", "Municipality", "field"],
  ["threat", "Threat", "risk"],
  ["inspection", "Inspection summary", "inspect"],
  ["validation", "Field validation", "check"],
] as const;

export function ReportsDesk({
  kind,
  onKind,
  command,
  analytics,
  rice,
  stops,
  onOpenMap,
  onOpenPlace,
}: {
  kind: (typeof REPORTS)[number][0];
  onKind: (kind: (typeof REPORTS)[number][0]) => void;
  command: CommandRecord | null;
  analytics: AnalyticsReport | null;
  rice: RiceReport | null;
  stops: FieldStop[];
  onOpenMap: () => void;
  onOpenPlace: (slug: string) => void;
}) {
  const title = REPORTS.find((item) => item[0] === kind)?.[1] || "Briefing";
  const focus = command?.priorities[0];
  const dist = analytics?.distribution?.rows || [];
  const total = Math.max(1, dist.reduce((sum, row) => sum + row.now, 0));
  const totalAhead = Math.max(1, dist.reduce((sum, row) => sum + (row.ahead ?? 0), 0));
  const metrics = rice?.situation.metrics || [];
  const priorities = kind === "municipality" && focus ? [focus] : (command?.priorities || []).slice(0, 8);

  return (
    <div className="pg reports" id="reports">
      <PageHead icon="reports" title="Reports" meta="Printable briefings from the stored record">
        <button type="button" className="btn-ghost" onClick={onOpenMap}><Icon name="map" size={16} />Map</button>
        <button type="button" className="btn" onClick={() => window.print()}><Icon name="reports" size={16} />Print</button>
      </PageHead>
      <div className="rep">
        <nav className="rep-nav" aria-label="Report type">
          {REPORTS.map(([id, label, icon]) => (
            <button key={id} type="button" aria-pressed={kind === id} onClick={() => onKind(id)}><Icon name={icon} size={17} />{label}</button>
          ))}
        </nav>
        <article className="doc" aria-label={title}>
          <header className="doc-head">
            <div>
              <h3>{title}</h3>
              <p>{command?.scope.label || "Nueva Ecija"} · {command?.threat.name || "Threat"} · {command?.forecast_date || "—"}</p>
            </div>
            <dl className="doc-stamp">
              <div><dt>Scores</dt><dd>{command?.updated_at ? new Date(command.updated_at).toLocaleString("en-PH", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—"}</dd></div>
              <div><dt>Weather</dt><dd>Open-Meteo model</dd></div>
            </dl>
          </header>

          <section className="doc-sec">
            <h4>Key points</h4>
            <ul className="keypoints">
              {(command?.brief.lines || []).slice(0, 6).map((line) => <li key={line}>{line}</li>)}
            </ul>
          </section>

          {metrics.length > 0 && kind !== "inspection" && kind !== "validation" && (
            <section className="doc-sec">
              <h4>Rice industry · {rice?.situation.place}</h4>
              <ul className="figs">
                {metrics.map((metric) => (
                  <li key={metric.id}><b>{metric.display.split(" ")[0]}</b><span>{metric.display.split(" ").slice(1).join(" ") || metric.label}</span><small>{metric.label} · {metric.period}</small></li>
                ))}
              </ul>
            </section>
          )}

          {dist.length > 0 && (
            <section className="doc-sec">
              <h4>Risk distribution · municipalities</h4>
              <div className="stack-rows">
                {[["Now", "now", total], ["+72h", "ahead", totalAhead]].map(([label, key, sum]) => (
                  <div className="stack-row" key={label as string}>
                    <span>{label}</span>
                    <div className="stack" role="img" aria-label={`${label}: ${dist.map((row) => `${row.label} ${key === "now" ? row.now : row.ahead ?? 0}`).join(", ")}`}>
                      {dist.map((row) => {
                        const value = key === "now" ? row.now : row.ahead ?? 0;
                        return value > 0 ? <i key={row.id} style={{ width: `${(value / (sum as number)) * 100}%`, background: CLASS_COLOR[row.id] || "#8d9488" }}>{value}</i> : null;
                      })}
                    </div>
                  </div>
                ))}
                <p className="legend-row">{dist.map((row) => <span key={row.id}><i style={{ background: CLASS_COLOR[row.id] || "#8d9488" }} />{row.label}</span>)}</p>
              </div>
            </section>
          )}

          {kind !== "validation" && priorities.length > 0 && (
            <section className="doc-sec">
              <h4>{kind === "municipality" ? `Focus · ${focus?.name}` : "Inspection priority"}</h4>
              <table className="dtable">
                <thead><tr><th>#</th><th>Municipality</th><th>Class</th><th className="num">Hazard</th><th className="num">Trend</th><th className="num">Priority</th></tr></thead>
                <tbody>
                  {priorities.map((row, index) => (
                    <tr key={row.slug}>
                      <td className="num muted">{index + 1}</td>
                      <td><button type="button" className="cell-link" onClick={() => onOpenPlace(row.slug)}>{row.name}</button></td>
                      <td><ClassBadge label={row.risk_label} /></td>
                      <td className="num">{row.hazard_points ?? "—"}</td>
                      <td className="num" data-dir={row.trend_direction || ""}>{row.trend_points == null ? "—" : `${row.trend_points > 0 ? "+" : ""}${row.trend_points}`}</td>
                      <td className="num strong">{row.priority_points ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {(kind === "provincial" || kind === "threat") && (command?.horizon.areas.length || 0) > 0 && (
            <section className="doc-sec">
              <h4>Next 72 hours</h4>
              <table className="dtable">
                <thead><tr><th>Municipality</th><th>Now</th><th>+72h</th><th className="num">Hazard</th></tr></thead>
                <tbody>
                  {command?.horizon.areas.map((area) => (
                    <tr key={area.slug}>
                      <td>{area.name}</td>
                      <td><ClassBadge label={area.from_class} /></td>
                      <td><ClassBadge label={area.to_class} /></td>
                      <td className="num">{area.from_points} → {area.to_points}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <section className="doc-sec">
            <h4>{kind === "validation" ? "Field results" : kind === "inspection" ? `Inspection list · ${stops.length}` : "Recommended actions"}</h4>
            {kind === "validation" || kind === "inspection" ? (
              stops.length === 0 ? <p className="empty-line">No visit in this session.</p> : (
                <table className="dtable">
                  <thead><tr><th>Municipality</th><th>Threat</th><th>Status</th><th>Note</th></tr></thead>
                  <tbody>{stops.map((stop) => <tr key={stop.slug}><td>{stop.name}</td><td>{stop.threat}</td><td><span className="stage-chip" data-stage={stop.status}>{STATUS_LABEL[stop.status]}</span></td><td className="muted">{stop.note || "—"}</td></tr>)}</tbody>
                </table>
              )
            ) : (
              <table className="dtable">
                <thead><tr><th>Action</th><th>Place</th><th>Window</th></tr></thead>
                <tbody>{(command?.actions || []).map((action) => <tr key={action.id}><td><span className="verb" data-type={action.type}>{action.type_label}</span></td><td>{action.place || command?.scope.label}</td><td className="muted">{action.window}</td></tr>)}</tbody>
              </table>
            )}
          </section>

          <section className="doc-sec">
            <h4>Data coverage</h4>
            <ul className="coverage">
              {(rice?.coverage || []).map((row) => (
                <li key={row.dataset} data-ok={row.status === "Available" ? "yes" : "no"}>
                  <Icon name={row.status === "Available" ? "check" : "close"} size={14} />
                  <span>{row.dataset}</span>
                  <small>{row.period || "—"}</small>
                </li>
              ))}
            </ul>
          </section>
        </article>
      </div>
    </div>
  );
}

const LINKS = [
  ["command", "Command"],
  ["map", "Map"],
  ["weather", "Weather"],
  ["rice", "Rice"],
  ["risk", "Risk"],
  ["analytics", "Analytics"],
  ["operations", "Operations"],
  ["administration", "Administration"],
  ["alerts", "Alerts"],
  ["reports", "Reports"],
] as const;

const WORD_LABELS = ["Projected class", "Class", "Stage", "Season", "Confidence", "Trend"];

type AnswerPart = { kind: "fact"; label: string; value: string } | { kind: "flag" | "note" | "source"; text: string };

function parseAnswerLine(raw: string): AnswerPart {
  const line = raw.trim().replace(/\.$/, "");
  if (/^(From|Source)\b/i.test(line)) return { kind: "source", text: line };
  if (/^No\b/.test(line)) return { kind: "flag", text: line };
  const word = WORD_LABELS.find((label) => line.startsWith(`${label} `));
  if (word) return { kind: "fact", label: word, value: line.slice(word.length + 1) };
  const trimmed = line.replace(/ in [A-Z][\w.'-]*(?: [A-Z][\w.'-]*)*$/, "");
  const match = trimmed.match(/^([A-Za-z][A-Za-z0-9% ,'/-]*?) (-?\d[\d.,]*(?:\s?(?:%|C|°C|mm|ha|h|hours|days))?(?:\s(?:to|of)\s-?\d[\d.,]*(?:\s?(?:%|C|mm|ha))?)?|\d{1,2} [A-Z][a-z]{2} \d{4})$/);
  if (match && match[1].length <= 48) return { kind: "fact", label: match[1], value: match[2] };
  return { kind: "note", text: line };
}

function ChatAnswer({ text }: { text: string }) {
  const lines = text.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const [lead, ...rest] = lines;
  const parts = rest.map(parseAnswerLine);
  const facts = parts.filter((part): part is Extract<AnswerPart, { kind: "fact" }> => part.kind === "fact");
  if (facts.length < 3) return <>{lines.map((line, index) => <p key={index}>{line}</p>)}</>;
  const flags = parts.filter((part) => part.kind === "flag");
  const notes = parts.filter((part) => part.kind === "note");
  const sources = parts.filter((part) => part.kind === "source");
  return (
    <>
      {lead && <p className="ans-lead">{lead}</p>}
      <dl className="ans-facts">
        {facts.map((fact, index) => (
          <div key={index}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
        ))}
      </dl>
      {flags.length > 0 && (
        <ul className="ans-flags">
          {flags.map((part, index) => <li key={index}>{"text" in part ? part.text : ""}</li>)}
        </ul>
      )}
      {notes.map((part, index) => <p key={index}>{"text" in part ? part.text : ""}</p>)}
      {sources.map((part, index) => <p key={index} className="ans-src">{"text" in part ? part.text : ""}</p>)}
    </>
  );
}

export function AskCropwatch({
  open,
  workspace,
  role,
  threat,
  place,
  time,
  prompts,
  chat,
  busy,
  input,
  places,
  onInput,
  onAsk,
  onClose,
  onOpenWorkspace,
  onOpenPlace,
}: {
  open: boolean;
  workspace: string;
  role: string;
  threat: string;
  place: string;
  time: string;
  prompts: { id: string; label: string; message: string }[];
  chat: { role: string; text: string }[];
  busy: boolean;
  input: string;
  places: { slug: string; name: string }[];
  onInput: (value: string) => void;
  onAsk: (message: string) => void;
  onClose: () => void;
  onOpenWorkspace: (id: (typeof LINKS)[number][0]) => void;
  onOpenPlace: (slug: string) => void;
}) {
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const latest = [...chat].reverse().find((item) => item.role === "assistant");
  const mentioned = useMemo(
    () => places.filter((item) => latest?.text.toLowerCase().includes(item.name.toLowerCase())).slice(0, 3),
    [places, latest],
  );
  const workspaceId = LINKS.find(([, label]) => label === workspace)?.[0];

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [chat.length, busy]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || input.trim().length < 2) return;
    onAsk(input);
  }

  return (
    <aside className="chat" role="dialog" aria-modal="false" aria-labelledby="chat-title">
      <header className="chat-head">
        <span className="chat-avatar" aria-hidden="true"><Icon name="spark" size={18} /></span>
        <div>
          <h2 id="chat-title">Ask CROPWATCH</h2>
        </div>
        <button type="button" className="chat-x" onClick={onClose} aria-label="Close assistant"><Icon name="close" size={18} /></button>
      </header>
      <ul className="chat-ctx" aria-label="Context sent with each question">
        <li><Icon name="risk" size={13} />{threat}</li>
        <li><Icon name="calendar" size={13} />{time}</li>
        <li><Icon name="field" size={13} />{place}</li>
        <li><Icon name="layers" size={13} />{workspace}</li>
      </ul>

      <div className="chat-log" ref={logRef} aria-live="polite">
        {chat.length === 0 && (
          <div className="chat-welcome">
            <p>Ask about hazard scores, weather, places, or what to inspect. Pick a starter:</p>
            <div className="chat-starters">
              {prompts.map((prompt) => (
                <button key={prompt.id} type="button" disabled={busy} onClick={() => onAsk(prompt.message)}>{prompt.label}<Icon name="arrow" size={14} /></button>
              ))}
            </div>
          </div>
        )}
        {chat.map((item, index) => (
          <div key={`${item.role}-${index}`} className="msg" data-role={item.role === "assistant" ? "ai" : "me"}>
            {item.role === "assistant" && <span className="msg-av" aria-hidden="true"><Icon name="spark" size={14} /></span>}
            <div className="bubble">
              <span className="sr-only">{item.role === "assistant" ? "CROPWATCH:" : "You:"}</span>
              {item.role === "assistant" ? <ChatAnswer text={item.text} /> : <p>{item.text}</p>}
            </div>
          </div>
        ))}
        {busy && (
          <div className="msg" data-role="ai">
            <span className="msg-av" aria-hidden="true"><Icon name="spark" size={14} /></span>
            <div className="bubble typing" role="status"><span /><span /><span /><span className="sr-only">Checking stored records</span></div>
          </div>
        )}
      </div>

      {latest && !busy && (
        <div className="chat-follow">
          {mentioned.map((item) => (
            <button key={item.slug} type="button" onClick={() => onOpenPlace(item.slug)}><Icon name="map" size={13} />{item.name}</button>
          ))}
          {workspaceId !== "map" && <button type="button" onClick={() => onOpenWorkspace("map")}><Icon name="map" size={13} />Map</button>}
          <button type="button" onClick={() => onOpenWorkspace("risk")}><Icon name="risk" size={13} />Risk</button>
          {chat.length > 0 && prompts.slice(0, 2).map((prompt) => (
            <button key={prompt.id} type="button" onClick={() => onAsk(prompt.message)}>{prompt.label}</button>
          ))}
        </div>
      )}

      <form className="chat-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="chat-input">Question</label>
        <textarea
          id="chat-input"
          ref={inputRef}
          value={input}
          rows={1}
          placeholder="Ask a question…"
          onChange={(event) => onInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit(event as unknown as FormEvent);
            }
          }}
        />
        <button type="submit" aria-label="Send" disabled={busy || input.trim().length < 2}><Icon name="send" size={17} /></button>
      </form>
      <p className="chat-fine">Role {role}. Enter to send, Shift+Enter for a new line.</p>
    </aside>
  );
}
