"use client";

import gsap from "gsap";
import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalyticsReport } from "./analytics-view";
import type { CommandRecord } from "./command-center";
import type { RiceReport } from "./rice-view";

const CLASS_COLOR: Record<string, string> = {
  Low: "#3d8c4e",
  Moderate: "#d89a12",
  High: "#e15a1c",
  "Very High": "#c62828",
  "Insufficient data": "#8d9488",
};

const FORECAST_DAY: Record<string, number> = { Now: 0, "+24h": 1, "+48h": 2, "+72h": 3 };

function MetricValue({ value }: { value: number | null }) {
  const ref = useRef<HTMLElement>(null);
  const previous = useRef(value);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (value == null) {
      node.textContent = "—";
      return;
    }
    const from = previous.current ?? value;
    previous.current = value;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      node.textContent = String(value);
      return;
    }
    const proxy = { n: from };
    const tween = gsap.to(proxy, {
      n: value,
      duration: 0.42,
      ease: "power2.out",
      onUpdate: () => { node.textContent = String(Math.round(proxy.n)); },
    });
    return () => { tween.kill(); };
  }, [value]);
  return <strong ref={ref}>{value == null ? "—" : value}</strong>;
}

const STRIP_LABEL: Record<string, string> = {
  priority: "Priority",
  rising: "Rising",
  alerts: "New high",
  actions: "Actions",
};

export function SituationStrip({
  command,
  lens,
  onLens,
  note,
}: {
  command: CommandRecord | null;
  lens: "priority" | "rising" | null;
  onLens: (lens: "priority" | "rising" | null) => void;
  note?: string | null;
}) {
  const items = command?.situation.indicators || [];
  return (
    <div className="ops-strip" aria-label="Current situation">
      {items.map((item) => {
        const selectable = item.id === "priority" || item.id === "rising";
        const pressed = lens === item.id;
        return (
          <button
            key={item.id}
            type="button"
            className="ops-metric"
            title={`${item.label}. ${item.detail}`}
            aria-pressed={selectable ? pressed : undefined}
            disabled={!selectable}
            onClick={() => {
              if (item.id !== "priority" && item.id !== "rising") return;
              onLens(pressed ? null : item.id);
            }}
          >
            <span>{STRIP_LABEL[item.id] || item.label}</span>
            <MetricValue value={item.value} />
            <i data-zero={item.value === 0 || item.value == null ? "true" : "false"} />
          </button>
        );
      })}
      <div className="ops-metric" title={command?.confidence.scope}>
        <span>Data</span>
        <strong>{command?.confidence.label || "—"}</strong>
        <i style={{ width: command?.confidence.label === "High" ? "100%" : command?.confidence.label === "Limited" ? "28%" : "62%" }} />
      </div>
      {note && <details className="ops-note"><summary>Brief</summary><p>{note}</p></details>}
    </div>
  );
}

export function PriorityQueue({
  command,
  active,
  onOpen,
  lens,
  onLens,
  note,
}: {
  command: CommandRecord | null;
  active: string | null;
  onOpen: (slug: string) => void;
  lens: "priority" | "rising" | null;
  onLens: (lens: "priority" | "rising" | null) => void;
  note?: string | null;
}) {
  const rows = (command?.priorities || []).filter((row) => lens !== "rising" || row.trend_direction === "rising");
  const watch = (command?.horizon.areas || [])
    .filter((area) => area.to_points > area.from_points && !rows.slice(0, 6).some((row) => row.slug === area.slug))
    .slice(0, 4);
  return (
    <aside className="ops-queue" aria-label="Where to pay attention">
      <header>
        <p className="ops-kicker">Command</p>
        <h2>{command?.threat.name || "Threat"}</h2>
        <p>{command?.scope.label || "Nueva Ecija"}{command?.forecast_date ? ` · ${command.forecast_date}` : ""}</p>
      </header>
      <SituationStrip command={command} lens={lens} onLens={onLens} note={note} />
      <h3>Highest priority</h3>
      <p className="ops-cols"><span></span><span>Municipality</span><span className="ops-pair"><em>Hazard</em><em>Priority</em></span></p>
      <ol>
        {rows.slice(0, 8).map((row) => (
          <li key={row.slug}>
            <button type="button" aria-current={active === row.slug ? "true" : undefined} onClick={() => onOpen(row.slug)}>
              <span className="ops-risk" style={{ background: CLASS_COLOR[row.risk_label] || "#8d9488" }} aria-hidden="true" />
              <span>
                <strong>{row.name}</strong>
                <small>{row.risk_label} · {row.trend_direction || "no trend"} {row.trend_arrow}</small>
              </span>
              <span className="ops-pair">
                <em title="Hazard score">{row.hazard_points ?? "—"}</em>
                <em title="Inspection priority">{row.priority_points ?? "—"}</em>
              </span>
            </button>
          </li>
        ))}
      </ol>
      {watch.length > 0 && (
        <>
          <h3>Watch</h3>
          <ol>
            {watch.map((area) => (
              <li key={area.slug}>
                <button type="button" onClick={() => onOpen(area.slug)}>
                  <span className="ops-risk" style={{ background: "#d89a12" }} aria-hidden="true" />
                  <span>
                    <strong>{area.name}</strong>
                    <small>{area.from_class} to {area.to_class}</small>
                  </span>
                  <span className="ops-pair"><em>{area.from_points}</em><em>{area.to_points}</em></span>
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
    </aside>
  );
}

export function Trajectory({
  name,
  series,
  day,
  onDay,
}: {
  name: string;
  series: { label: string; points: number | null; kind: string }[];
  day: number;
  onDay: (day: number) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const width = 640;
  const height = 84;
  const padX = 28;
  const padY = 12;
  const coords = series.map((point, index) => {
    const x = padX + (index * (width - padX * 2)) / Math.max(1, series.length - 1);
    const y = point.points == null ? null : padY + (1 - point.points / 100) * (height - padY - 18);
    return { ...point, x, y, index };
  });
  const drawn = coords.filter((point) => point.y != null);
  const path = drawn.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
  const active = hover == null ? coords.find((point) => FORECAST_DAY[point.label] === day) : coords[hover];
  return (
    <section className="ops-track" aria-label={`Hazard trajectory for ${name}`}>
      <header>
        <h2>{name}</h2>
        <p>Stored hazard</p>
      </header>
      {drawn.length === 0 ? <p className="ops-fine">No stored hazard series for this place.</p> : (
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${name} hazard from stored runs through the forecast.`}>
          <path d={path} pathLength="1" />
          {active?.y != null && <line className="ops-cross" x1={active.x} x2={active.x} y1={padY} y2={height - 16} />}
          {coords.map((point) => point.y == null ? null : (
            <g key={point.label}>
              <circle
                cx={point.x}
                cy={point.y}
                r={FORECAST_DAY[point.label] === day ? 4.5 : 3}
                data-kind={point.kind}
                onMouseEnter={() => setHover(point.index)}
                onMouseLeave={() => setHover(null)}
              />
              <text x={point.x} y={height - 2} textAnchor="middle">{point.label}</text>
            </g>
          ))}
        </svg>
      )}
      {active?.points != null && <b>{active.points}</b>}
    </section>
  );
}

export function AnalyticsBoard({
  report,
  allThreats,
  onAllThreats,
  onOpen,
  note,
  active,
  day,
  onDay,
}: {
  report: AnalyticsReport | null;
  allThreats: boolean;
  onAllThreats: (value: boolean) => void;
  onOpen: (slug: string) => void;
  note?: string | null;
  active?: string | null;
  day?: number;
  onDay?: (day: number) => void;
}) {
  const [sort, setSort] = useState<"elevated" | "name">("elevated");
  const matrix = useMemo(() => {
    const rows = [...(report?.matrix || [])];
    rows.sort((a, b) => sort === "name" ? a.name.localeCompare(b.name) : b.elevated - a.elevated || a.name.localeCompare(b.name));
    return rows;
  }, [report, sort]);
  const threats = report?.threats || [];
  if (!report) return <p className="ops-wait">Loading analytics.</p>;
  return (
    <div className="ops-board" id="analytics">
      <header className="ops-board-head">
        <h2>{report.threat?.name || "All threats"}</h2>
        <label title={report.trend_rule}>
          <input type="checkbox" checked={allThreats} onChange={(event) => onAllThreats(event.target.checked)} />
          Separate threats
        </label>
      </header>
      <Trajectory
        name={(active && report.ranking.find((row) => row.slug === active)?.name) || report.chart?.name || report.threat?.name || "Threat"}
        series={(active && report.ranking.find((row) => row.slug === active)?.series) || report.chart?.series || []}
        day={day || 0}
        onDay={onDay || (() => undefined)}
      />
      <section aria-label="Threat comparison">
        <h3>Threats</h3>
        <table className="ops-table">
          <thead>
            <tr>
              <th scope="col">Threat</th>
              <th scope="col">High or very high</th>
              <th scope="col">Rising</th>
              <th scope="col">Fastest rise</th>
            </tr>
          </thead>
          <tbody>
            {threats.map((row) => (
              <tr key={row.id}>
                <th scope="row">{row.name}</th>
                <td>{row.high_plus}</td>
                <td>{row.rising}</td>
                <td>
                  {row.fastest_slug ? (
                    <button type="button" className="text-link" onClick={() => onOpen(row.fastest_slug || "")}>{row.fastest_name}</button>
                  ) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {report.distribution && (
        <section aria-label="Risk distribution">
          <h3>Class now and +72h</h3>
          <div className="ops-dist">
            {report.distribution.rows.filter((row) => row.id !== "insufficient_data" || row.now || row.ahead).map((row) => (
              <div key={row.id}>
                <span style={{ background: CLASS_COLOR[row.label] || "#b7b1a6" }} />
                <b>{row.label}</b>
                <strong>{row.now}</strong>
                <small>{row.ahead == null ? "—" : row.ahead}</small>
              </div>
            ))}
          </div>
        </section>
      )}
      <section aria-label="Risk by municipality">
        <header className="ops-board-head">
          <h3>Municipalities</h3>
          <label>
            Sort
            <select value={sort} onChange={(event) => setSort(event.target.value === "name" ? "name" : "elevated")}>
              <option value="elevated">Elevated count</option>
              <option value="name">Name</option>
            </select>
          </label>
        </header>
        <table className="ops-table">
          <thead>
            <tr>
              <th scope="col">Municipality</th>
              {threats.map((threat) => <th scope="col" key={threat.id}>{threat.name}</th>)}
              <th scope="col">Elevated</th>
            </tr>
          </thead>
          <tbody>
            {matrix.map((row) => (
              <tr key={row.slug} data-active={active === row.slug ? "true" : "false"}>
                <th scope="row">
                  <button type="button" className="text-link" onClick={() => onOpen(row.slug)}>{row.name}</button>
                </th>
                {threats.map((threat) => {
                  const label = row.classes[threat.id] || "—";
                  return (
                    <td key={threat.id}>
                      <span className="ops-class"><i style={{ background: CLASS_COLOR[label] || "#8d9488" }} />{label}</span>
                    </td>
                  );
                })}
                <td>{row.elevated}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {report.convergence.length > 0 && (
        <section aria-label="Risk convergence">
          <h3>Convergence</h3>
          <ul className="ops-conv">
            {report.convergence.slice(0, 8).map((row) => (
              <li key={row.slug}>
                <button type="button" onClick={() => onOpen(row.slug)}>{row.name}</button>
                <span>
                  {row.threats.map((threat) => (
                    <i key={threat.name} title={`${threat.name}: ${threat.risk_label}`} style={{ background: CLASS_COLOR[threat.risk_label] || "#b7b1a6" }} />
                  ))}
                </span>
              </li>
            ))}
          </ul>
          <p className="ops-fine" title="Several threat models can be elevated together. That does not mean those pests or diseases are present.">Overlap is not presence.</p>
        </section>
      )}
      {report.outlook && (
        <section aria-label="72 hour outlook">
          <h3>Next 72 hours</h3>
          <ol className="ops-slope">
            {report.outlook.increasing.slice(0, 6).map((row) => {
              const from = row.from_points || 0;
              const to = row.to_points || 0;
              return (
                <li key={row.slug}>
                  <button type="button" onClick={() => onOpen(row.slug)}>{row.name}</button>
                  <svg viewBox="0 0 80 24" aria-hidden="true">
                    <line x1="4" y1={22 - from * 0.2} x2="76" y2={22 - to * 0.2} />
                    <circle cx="4" cy={22 - from * 0.2} r="2" />
                    <circle cx="76" cy={22 - to * 0.2} r="2" />
                  </svg>
                  <b>{from}→{to}</b>
                </li>
              );
            })}
          </ol>
        </section>
      )}
      {report.drivers.length > 0 && (
        <section aria-label="Drivers">
          <h3>Favorable factors</h3>
          <ul className="ops-drivers">
            {report.drivers.map((factor) => (
              <li key={factor.label}>
                <span>{factor.label}</span>
                <i style={{ width: `${Math.min(100, factor.municipalities * 3)}%` }} />
                <b>{factor.municipalities}</b>
              </li>
            ))}
          </ul>
          <p className="ops-fine" title={report.driver_note}>From stored rule statuses. Not read from the chart.</p>
        </section>
      )}
      <details>
        <summary>Counts and method</summary>
        {note && <p>{note}</p>}
        {report.summary.lines.map((line) => <p key={line}>{line}</p>)}
        <p>{report.chart_note}</p>
      </details>
    </div>
  );
}

export function InspectionBoard({
  command,
  plan,
  canPlan,
  onOpen,
  onAdd,
  onRemove,
}: {
  command: CommandRecord | null;
  plan: { slug: string; name: string }[];
  canPlan: boolean;
  onOpen: (slug: string) => void;
  onAdd: (item: { slug: string; name: string }) => void;
  onRemove: (slug: string) => void;
}) {
  const actions = (command?.actions || []).filter((item) => item.slug);
  return (
    <div className="ops-board" id="inspections">
      <header className="ops-board-head">
        <h2>Inspections</h2>
        <p>{command?.scope.label}. {actions.length} recommended.</p>
      </header>
      <ol className="inspect-list">
        {actions.map((item) => {
          const listed = item.slug ? plan.some((row) => row.slug === item.slug) : false;
          return (
            <li key={item.id}>
              <div>
                <strong>{item.place || "Province"}</strong>
                <span>{item.threat}</span>
                <span className="inspect-score">{item.hazard_points ?? "—"} / {item.priority_points ?? "—"}</span>
                <span className="ops-class">
                  <i style={{ background: CLASS_COLOR[item.risk_label || ""] || "#8d9488" }} />
                  {item.risk_label || "No class"} · {item.trend_direction || "no trend"}
                </span>
                <span>{item.type_label}</span>
              </div>
              <p>{item.recommendation}</p>
              <div className="inspect-actions">
                {item.slug && <button type="button" className="inspect-go" onClick={() => onOpen(item.slug || "")}>Inspect</button>}
                {canPlan && item.slug && (
                  <button
                    type="button"
                    className="text-link"
                    disabled={listed}
                    onClick={() => onAdd({ slug: item.slug || "", name: item.place || item.slug || "" })}
                  >
                    {listed ? "Added" : "Add"}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <section aria-label="Inspection list">
        <h3>This session</h3>
        {plan.length === 0 ? <p className="ops-fine">No places added yet.</p> : (
          <ul>
            {plan.map((item, index) => (
              <li key={item.slug}>
                <span>{index + 1}. {item.name}</span>
                <button type="button" className="linkish" onClick={() => onOpen(item.slug)}>Map</button>
                <button type="button" className="linkish" onClick={() => onRemove(item.slug)}>Remove</button>
              </li>
            ))}
          </ul>
        )}
        {!canPlan && <p className="ops-fine">This account cannot build an inspection list.</p>}
      </section>
    </div>
  );
}

export function DataBoard({ report, note }: { report: RiceReport | null; note?: string | null }) {
  if (!report) return <p className="ops-wait">Loading data coverage.</p>;
  return (
    <div className="ops-board" id="data">
      <header className="ops-board-head">
        <h2>Data coverage</h2>
        <p>{report.situation.scope_note}</p>
      </header>
      <table className="ops-table">
        <thead>
          <tr>
            <th scope="col">Dataset</th>
            <th scope="col">Status</th>
            <th scope="col">Latest available</th>
            <th scope="col">Source</th>
          </tr>
        </thead>
        <tbody>
          {report.coverage.map((row) => (
            <tr key={row.dataset}>
              <th scope="row">{row.dataset}</th>
              <td><span className="data-status" data-status={row.status}>{row.status}</span></td>
              <td>{row.period || "—"}</td>
              <td>{row.source || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Provincial figures</h3>
      <table className="ops-table">
        <thead><tr><th scope="col">Statistic</th><th scope="col">Value</th><th scope="col">Period</th><th scope="col">Source</th></tr></thead>
        <tbody>
          {report.situation.metrics.map((metric) => (
            <tr key={metric.id}><th scope="row">{metric.label}</th><td>{metric.display}</td><td>{metric.period}</td><td>{metric.source}</td></tr>
          ))}
        </tbody>
      </table>
      <details>
        <summary>Limits</summary>
        <p>{report.boundary}</p>
        <p>{report.period_note}</p>
        <p>{report.exposure.sentence}</p>
        <p>{report.crop.sentence}</p>
        <p>{report.climate.enso.sentence} {report.climate.threat_sentence}</p>
        <p>{report.barangay_note} {report.conditions.satellite.note}</p>
        {note && <p>{note}</p>}
      </details>
    </div>
  );
}
