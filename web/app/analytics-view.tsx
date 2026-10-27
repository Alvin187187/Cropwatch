"use client";

import { useMemo, useState } from "react";

type Factor = { id?: string | null; label: string; status: string };
type RankRow = {
  slug: string;
  name: string;
  hazard_points: number | null;
  priority_points: number | null;
  risk_label: string | null;
  trend_direction: string | null;
  trend_arrow: string;
  trend_points: number | null;
  rice: string;
  factors: Factor[];
  series: { label: string; points: number | null; kind: string }[];
};
type ThreatRow = {
  id: string;
  name: string;
  high_plus: number;
  rising: number;
  fastest_name: string | null;
  fastest_points: number | null;
  fastest_slug: string | null;
};
type Move = { slug: string; name: string; from_points: number | null; to_points: number | null; from_class?: string; to_class?: string };

export type AnalyticsReport = {
  mode: string;
  threat: { id: string; name: string } | null;
  scope: { label: string; can_plan: boolean };
  trend_rule: string;
  chart_note: string;
  band_definition: string;
  combined_note: string;
  summary_text: string;
  summary: { lines: string[] };
  threats: ThreatRow[];
  convergence: { slug: string; name: string; count: number; sentence: string; threats: { name: string; risk_label: string }[] }[];
  distribution: { rows: { id: string; label: string; now: number; ahead: number | null }[] } | null;
  transitions: { matrix: Record<string, Record<string, number>> | null; notable: { from_label: string; to_label: string; count: number }[]; excluded: number } | null;
  outlook: {
    sentence: string;
    increasing: Move[];
    decreasing: Move[];
    staying_high: { name: string }[];
    insufficient: number;
    cluster_note: string;
  } | null;
  fastest: { slug: string; name: string; points: number | null; from_points: number | null; to_points: number | null }[];
  ranking: RankRow[];
  chart: { slug: string; name: string; series: { label: string; points: number | null; kind: string }[]; note: string } | null;
  drivers: { label: string; municipalities: number }[];
  driver_note: string;
  coverage: { sentence: string; level: string; checks: { id: string; label: string; value: string }[]; interpretation: string } | null;
  gaps: { label: string; detail: string; effect: string }[];
  actions: { type: string; type_label: string; slug: string; name: string; hazard_points: number | null; priority_points: number | null }[];
  clusters: { label: string; names: string[]; sentence?: string; size?: number }[];
  matrix: { slug: string; name: string; classes: Record<string, string>; elevated: number }[];
};

const CLASS_KEYS = ["low", "moderate", "high", "very_high"] as const;

function TrendChart({ series }: { series: { label: string; points: number | null }[] }) {
  const width = 560;
  const height = 180;
  const padX = 48;
  const padY = 24;
  const usable = series.filter((point) => point.points != null);
  if (usable.length === 0) return <p className="an-note">No stored hazard scores for this line.</p>;
  const coords = series.map((point, index) => {
    const x = padX + (index * (width - padX * 2)) / Math.max(1, series.length - 1);
    const y = point.points == null ? null : padY + (1 - point.points / 100) * (height - padY * 2);
    return { ...point, x, y };
  });
  const drawn = coords.filter((point) => point.y != null);
  const path = drawn.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
  return (
    <svg className="an-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Stored hazard score from earlier runs through the 72 hour forecast">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
      {drawn.map((point) => <circle key={point.label} cx={point.x} cy={point.y || 0} r="3.5" />)}
      {coords.map((point, index) => (
        <text key={point.label} x={point.x} y={height - 4} textAnchor={index === 0 ? "start" : index === coords.length - 1 ? "end" : "middle"} fontSize="11">{point.label}</text>
      ))}
    </svg>
  );
}

export default function AnalyticsView({
  report,
  loading,
  error,
  narration,
  allThreats,
  onAllThreats,
  onOpenPlace,
  onAddPlan,
  onRetry,
  chapter = "risk",
}: {
  report: AnalyticsReport | null;
  loading: boolean;
  error: string;
  narration: string | null;
  allThreats: boolean;
  onAllThreats: (value: boolean) => void;
  onOpenPlace: (slug: string) => void;
  onAddPlan: (item: { slug: string; name: string }) => void;
  onRetry: () => void;
  chapter?: "risk" | "patterns";
}) {
  const [sort, setSort] = useState<"priority_points" | "hazard_points" | "trend_points" | "rice" | "risk_label">("priority_points");
  const [focus, setFocus] = useState<string>("");
  const [compare, setCompare] = useState("");
  const ranking = report?.ranking || [];
  const ordered = useMemo(() => {
    const rows = [...ranking];
    rows.sort((left, right) => {
      if (sort === "rice") return left.rice.localeCompare(right.rice) || left.name.localeCompare(right.name);
      if (sort === "risk_label") return String(left.risk_label).localeCompare(String(right.risk_label)) || left.name.localeCompare(right.name);
      const a = left[sort] ?? -1;
      const b = right[sort] ?? -1;
      return b - a || left.name.localeCompare(right.name);
    });
    return rows;
  }, [ranking, sort]);
  const focusRow = ordered.find((row) => row.slug === (focus || report?.chart?.slug)) || ordered[0];
  const other = ordered.find((row) => row.slug === compare);
  const threatColumns = report?.threats || [];

  return (
    <div className="analytics" id="analytics">
      <header className="an-lead">
        <p className="an-kicker">{chapter === "patterns" ? "Analytics" : "Risk"}</p>
        <h2>{chapter === "patterns" ? "Patterns across the stored record" : (report?.threat?.name || "All threats")}</h2>
        <p className="an-note">{report?.scope.label}. {report?.trend_rule}</p>
        <label className="an-all">
          <input type="checkbox" checked={allThreats} onChange={(event) => onAllThreats(event.target.checked)} />
          All threats, kept separate
        </label>
      </header>
      {loading && !report && <p className="status">Loading the analytics.</p>}
      {error && <p className="error" role="alert">{error} <button className="secondary" type="button" onClick={onRetry}>Try again</button></p>}
      {report && (
        <>
          {chapter === "risk" && <section className="risk-dash" aria-label="Risk dashboard">
            {(report.distribution?.rows || []).map((row) => {
              const peak = Math.max(1, ...(report.distribution?.rows || []).map((item) => item.now));
              return (
                <article key={row.id} data-class={row.id}>
                  <span>{row.label}</span>
                  <strong>{row.now}</strong>
                  <small>{row.ahead == null ? "+72h unavailable" : `${row.ahead} at +72h`}</small>
                  <i style={{ width: `${Math.round((row.now / peak) * 100)}%` }} />
                </article>
              );
            })}
            {report.fastest.slice(0, 4).map((row) => (
              <button key={row.slug} type="button" className="risk-rise" onClick={() => onOpenPlace(row.slug)}>
                <span>Fastest rise</span>
                <strong>{row.name}</strong>
                <b>{row.from_points ?? "—"} → {row.to_points ?? "—"}</b>
              </button>
            ))}
          </section>}
          {chapter === "risk" && <section aria-label="Situation summary">
            <h3>Current situation</h3>
            {narration && <p>{narration}</p>}
            {report.summary.lines.map((line) => <p key={line}>{line}</p>)}
            {report.mode === "all" && <p className="an-note">{report.combined_note}</p>}
          </section>}

          {chapter === "risk" && report.chart && focusRow && (
            <section aria-label="Hazard trend">
              <h3>Hazard trend</h3>
              <label>
                Municipality
                <select value={focusRow.slug} onChange={(event) => setFocus(event.target.value)}>
                  {ordered.map((row) => <option key={row.slug} value={row.slug}>{row.name}</option>)}
                </select>
              </label>
              <TrendChart series={focusRow.series} />
              <p className="an-note">{report.chart.note}</p>
              <table className="an-table">
                <caption>Stored hazard points for {focusRow.name}</caption>
                <tbody>
                  {focusRow.series.map((point) => (
                    <tr key={point.label}><th>{point.label}</th><td>{point.points == null ? "—" : point.points}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {chapter === "risk" && report.distribution && (
            <section aria-label="Risk class movement">
              <h3>Risk class changes</h3>
              <table className="an-table">
                <thead><tr><th>Class</th><th>Now</th><th>+72h</th></tr></thead>
                <tbody>
                  {report.distribution.rows.map((row) => (
                    <tr key={row.id}><td>{row.label}</td><td>{row.now}</td><td>{row.ahead == null ? "—" : row.ahead}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {chapter === "patterns" && report.transitions?.matrix && (
            <section aria-label="Risk transition matrix">
              <h3>Current to forecast class</h3>
              <table className="an-table">
                <thead>
                  <tr>
                    <th>Current</th>
                    {CLASS_KEYS.map((key) => <th key={key}>{report.distribution?.rows.find((row) => row.id === key)?.label || key}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {CLASS_KEYS.map((from) => (
                    <tr key={from}>
                      <th>{report.distribution?.rows.find((row) => row.id === from)?.label || from}</th>
                      {CLASS_KEYS.map((to) => <td key={to}>{report.transitions?.matrix?.[from]?.[to] ?? 0}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
              {report.transitions.notable.map((item) => (
                <p key={`${item.from_label}-${item.to_label}`}>{item.count} {item.from_label} → {item.to_label}</p>
              ))}
              {report.transitions.excluded > 0 && <p className="an-note">{report.transitions.excluded} municipalities are outside this matrix because a class is missing.</p>}
            </section>
          )}

          {chapter === "risk" && report.mode === "threat" && (
            <section aria-label="Municipality ranking">
              <h3>Municipality ranking</h3>
              <p className="an-note">Sorting by inspection priority does not make priority the hazard score.</p>
              <div className="an-sort" role="group" aria-label="Sort ranking">
                {([
                  ["priority_points", "Inspection priority"],
                  ["hazard_points", "Hazard"],
                  ["trend_points", "Trend"],
                  ["rice", "Rice area"],
                  ["risk_label", "Risk class"],
                ] as const).map(([id, label]) => (
                  <button key={id} type="button" className="secondary" aria-pressed={sort === id} onClick={() => setSort(id)}>{label}</button>
                ))}
              </div>
              <table className="an-table">
                <thead>
                  <tr><th>Municipality</th><th>Hazard</th><th>Inspection priority</th><th>Trend</th><th>Rice area</th></tr>
                </thead>
                <tbody>
                  {ordered.map((row) => (
                    <tr key={row.slug}>
                      <td><button type="button" className="linkish" onClick={() => onOpenPlace(row.slug)}>{row.name}</button></td>
                      <td>{row.hazard_points ?? "—"}</td>
                      <td>{row.priority_points ?? "—"}</td>
                      <td>{row.trend_arrow} {row.trend_direction || "—"}{row.trend_points != null ? ` ${row.trend_points > 0 ? "+" : ""}${row.trend_points}` : ""}</td>
                      <td>{row.rice}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {chapter === "risk" && report.fastest.length > 0 && (
            <section aria-label="Fastest-rising hazard scores">
              <h3>Fastest-rising hazard score</h3>
              <ul>
                {report.fastest.map((row) => (
                  <li key={row.slug}>
                    <button type="button" className="linkish" onClick={() => onOpenPlace(row.slug)}>{row.name}</button>
                    <span>{row.points == null ? "" : `${row.points > 0 ? "+" : ""}${row.points} points`}{row.from_points != null && row.to_points != null ? `, hazard ${row.from_points} → ${row.to_points}` : ""}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-label="Threat comparison">
            <h3>Threat comparison</h3>
            <p className="an-note">{report.combined_note}</p>
            <table className="an-table">
              <thead><tr><th>Threat</th><th>High or very high</th><th>Rising hazard</th><th>Fastest-rising hazard</th></tr></thead>
              <tbody>
                {threatColumns.map((row) => (
                  <tr key={row.id}>
                    <td>{row.name}</td>
                    <td>{row.high_plus}</td>
                    <td>{row.rising}</td>
                    <td>{row.fastest_name ? `${row.fastest_name}${row.fastest_points != null ? ` +${row.fastest_points}` : ""}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {chapter === "patterns" && report.matrix.length > 0 && (
            <section aria-label="Risk by municipality">
              <h3>Risk by municipality</h3>
              <p className="an-note">Each cell is that threat’s own class. There is no combined score.</p>
              <table className="an-table">
                <thead>
                  <tr>
                    <th>Municipality</th>
                    {threatColumns.map((threat) => <th key={threat.id}>{threat.name}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {report.matrix.map((row) => (
                    <tr key={row.slug}>
                      <td>{row.name}</td>
                      {threatColumns.map((threat) => <td key={threat.id}>{row.classes[threat.id] || "—"}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {chapter === "patterns" && report.convergence.length > 0 && (
            <section aria-label="Risk convergence">
              <h3>Risk convergence</h3>
              {report.convergence.map((row) => (
                <article key={row.slug}>
                  <h4>{row.name}</h4>
                  <ul>{row.threats.map((threat) => <li key={threat.name}>{threat.name}: {threat.risk_label}</li>)}</ul>
                  <p>{row.sentence}</p>
                </article>
              ))}
            </section>
          )}

          {chapter === "risk" && report.mode === "threat" && (
            <section aria-label="Risk drivers">
              <h3>Risk drivers</h3>
              <p className="an-note">{report.driver_note}</p>
              {report.drivers.length === 0 ? <p>No stored factor is in the favorable band for this run.</p> : (
                <ul>
                  {report.drivers.map((factor) => (
                    <li key={factor.label}>{factor.label} — favorable in {factor.municipalities} {factor.municipalities === 1 ? "municipality" : "municipalities"}</li>
                  ))}
                </ul>
              )}
              {focusRow && ordered.length > 1 && (
                <label>
                  Compare with
                  <select value={compare} onChange={(event) => setCompare(event.target.value)}>
                    <option value="">Choose a municipality</option>
                    {ordered.filter((row) => row.slug !== focusRow.slug).map((row) => <option key={row.slug} value={row.slug}>{row.name}</option>)}
                  </select>
                </label>
              )}
              {focusRow && other && <CompareTable left={focusRow} right={other} />}
            </section>
          )}

          {chapter === "risk" && report.outlook && (
            <section aria-label="72 hour outlook">
              <h3>Next 72 hours</h3>
              <p>{report.outlook.sentence}</p>
              <h4>Highest expected increases</h4>
              <ol>
                {report.outlook.increasing.slice(0, 5).map((row) => (
                  <li key={row.slug}>{row.name}: hazard {row.from_points} → {row.to_points}</li>
                ))}
              </ol>
              {report.outlook.decreasing.length > 0 && <p>{report.outlook.decreasing.length} municipalities are projected to decrease by at least 3 hazard points.</p>}
              <p>{report.outlook.staying_high.length} municipalities stay high or very high.</p>
              <p>{report.outlook.insufficient} municipalities have insufficient data on the current score.</p>
              <p className="an-note">{report.outlook.cluster_note}</p>
            </section>
          )}

          {chapter === "patterns" && report.clusters.length > 0 && (
            <section aria-label="Risk clusters">
              <h3>Risk clusters</h3>
              {report.clusters.map((cluster) => (
                <p key={cluster.label}>{cluster.label}: {(cluster.names || []).join(", ")}. {cluster.sentence}</p>
              ))}
            </section>
          )}

          {chapter === "patterns" && report.coverage && (
            <section aria-label="Data confidence">
              <h3>Data confidence</h3>
              <p>Input completeness: {report.coverage.level}</p>
              <p>{report.coverage.sentence}</p>
              <ul>
                {report.coverage.checks.map((item) => <li key={item.id}>{item.label}: {item.value}</li>)}
              </ul>
              <p className="an-note">{report.coverage.interpretation}</p>
            </section>
          )}

          {chapter === "patterns" && report.gaps.length > 0 && (
            <section aria-label="Data gaps">
              <h3>Data gaps</h3>
              {report.gaps.map((gap) => (
                <article key={gap.label}>
                  <h4>{gap.label}</h4>
                  <p>{gap.detail}</p>
                  <p className="an-note">What this affects: {gap.effect}</p>
                </article>
              ))}
            </section>
          )}

          {report.actions.length > 0 && (
            <section aria-label="Analytics to action">
              <h3>From this analysis</h3>
              <ul>
                {report.actions.map((action) => (
                  <li key={`${action.type}-${action.slug}`}>
                    <span>{action.type_label}</span>
                    <button type="button" className="linkish" onClick={() => onOpenPlace(action.slug)}>{action.name}</button>
                    <span>Hazard {action.hazard_points ?? "—"} · Inspection priority {action.priority_points ?? "—"}</span>
                    {report.scope.can_plan && (
                      <button type="button" className="secondary" onClick={() => onAddPlan({ slug: action.slug, name: action.name })}>Add to inspection list</button>
                    )}
                  </li>
                ))}
              </ul>
              {!report.scope.can_plan && <p className="an-note">This account can read the analysis. It cannot build an inspection list.</p>}
            </section>
          )}
        </>
      )}
    </div>
  );
}

function CompareTable({ left, right }: { left: RankRow; right: RankRow }) {
  const ids = new Map<string, string>();
  for (const factor of [...left.factors, ...right.factors]) {
    if (factor.id) ids.set(factor.id, factor.label);
  }
  const status = (row: RankRow, id: string) => row.factors.find((factor) => factor.id === id)?.status || "Not in this score";
  return (
    <table className="an-table">
      <caption>{left.name} compared with {right.name}</caption>
      <thead><tr><th>Factor</th><th>{left.name}</th><th>{right.name}</th></tr></thead>
      <tbody>
        <tr><th>Hazard</th><td>{left.hazard_points ?? "—"}</td><td>{right.hazard_points ?? "—"}</td></tr>
        <tr><th>Inspection priority</th><td>{left.priority_points ?? "—"}</td><td>{right.priority_points ?? "—"}</td></tr>
        {[...ids.entries()].map(([id, label]) => (
          <tr key={id}><th>{label}</th><td>{status(left, id)}</td><td>{status(right, id)}</td></tr>
        ))}
      </tbody>
    </table>
  );
}
