"use client";

export type IntelFactor = { id?: string | null; label: string; status: string; used: boolean };

export type IntelPlace = {
  slug: string;
  name: string;
  risk_class: string | null;
  risk_label: string | null;
  hazard_points: number | null;
  priority_points: number | null;
  trend_direction: string | null;
  trend_arrow: string;
  change_bucket: string;
  factors: IntelFactor[];
  why: string;
  action: string | null;
  exposure: string;
  confidence: string | null;
};

export type IntelCluster = {
  id: string;
  label: string;
  size: number;
  names: string[];
  slugs: string[];
  hidden_neighbors: number;
  threat: string;
  mean_hazard: number | null;
  priority_points: number | null;
  priority_note: string;
  action: string;
  sentence: string;
  scope_note: string;
};

export type MapIntel = {
  geometry_note: string;
  band_definition: string;
  rise_rule: string;
  summary: string;
  changes: {
    basis: string;
    increased: { slug: string; name: string; from_points: number | null; to_points: number | null }[];
    decreased: { slug: string; name: string }[];
    new_high: { slug: string; name: string }[];
    unchanged: number;
    unknown: number;
  };
  clusters: IntelCluster[];
  command: {
    field_validation: { count: number; slugs: string[]; sentence: string };
    rising_72: { count: number; slugs: string[]; sentence: string };
    top_band: { count: number; slugs: string[]; sentence: string };
  };
  places: IntelPlace[];
  layer_notes: Record<string, string>;
  data: { checks: { id: string; label: string; value: string }[]; interpretation: string };
  scope: { label: string; can_plan: boolean; can_act: boolean; can_recompute: boolean };
};

export type SelectedRead = {
  name: string;
  slug: string;
  municipality?: string | null;
  score_origin_note?: string;
  hazard_points: number | null;
  priority_points: number | null;
  priority_note?: string;
  risk_label: string | null;
  trend_arrow: string;
  trend_direction: string | null;
  why_line?: string;
  why_now?: {
    available: boolean;
    sentence: string;
    factors: string[];
    note: string;
  } | null;
  factor_rows?: IntelFactor[];
  action?: string | null;
  exposure?: string | null;
  confidence?: string | null;
};

export const LAYER_GROUPS = [
  { id: "risk", label: "Risk", layers: ["risk", "priority", "change"] },
  { id: "weather", label: "Weather", layers: ["temp", "rain", "humidity", "wind", "soil", "leaf"] },
  { id: "rice", label: "Rice", layers: ["rice", "rice_fraction"] },
  { id: "satellite", label: "Satellite", layers: ["canopy", "evi", "water", "lswi", "flood", "lst"] },
  { id: "terrain", label: "Terrain", layers: ["elevation"] },
] as const;

const FORECAST = ["Now", "+24h", "+48h", "+72h", "+4d", "+5d", "+6d"];

const COMMAND_FOCI = [
  ["field_validation", "Field validation"],
  ["rising_72", "Rising over 72h"],
  ["top_band", "Highest priorities"],
] as const;

export type CommandFocus = (typeof COMMAND_FOCI)[number][0];

function scorePair(hazard: number | null, priority: number | null) {
  return (
    <div className="im-pair">
      <p><span>Hazard risk</span><b>{hazard == null ? "—" : `${hazard} / 100`}</b></p>
      <p><span>Inspection priority</span><b>{priority == null ? "—" : `${priority} / 100`}</b></p>
    </div>
  );
}

export function ForecastTimeline({
  day,
  summary,
  rule,
  onDay,
}: {
  day: number;
  summary: string | null;
  rule: string | null;
  onDay: (day: number) => void;
}) {
  return (
    <div className="forecast-timeline">
      <div role="radiogroup" aria-label="Risk forecast">
        {FORECAST.map((label, index) => (
          <button key={label} type="button" aria-pressed={day === index} onClick={() => onDay(index)}>
            {label}
          </button>
        ))}
      </div>
      {(summary || rule) && (
        <details>
          <summary>Horizon</summary>
          {summary && <p className="im-summary">{summary}</p>}
          {rule && <p className="im-note">{rule}</p>}
        </details>
      )}
    </div>
  );
}

export function MapControls({
  overlay,
  overlays,
  basemap,
  basemaps,
  layers,
  opacity,
  mapMode,
  commandFocus,
  intel,
  plan,
  layerMissing,
  layerNote,
  recomputeState,
  onOverlay,
  onBasemap,
  onLayer,
  onOpacity,
  onMode,
  onFocus,
  onOpen,
  onCluster,
  onRemovePlan,
  onRecompute,
}: {
  overlay: string;
  overlays: { id: string; label: string }[];
  basemap: string;
  basemaps: { id: string; label: string }[];
  layers: Record<string, boolean>;
  opacity: number;
  mapMode: "explore" | "command";
  commandFocus: CommandFocus;
  intel: MapIntel | null;
  plan: { slug: string; name: string }[];
  layerMissing: boolean;
  layerNote: string;
  recomputeState: string;
  onOverlay: (id: string) => void;
  onBasemap: (id: string) => void;
  onLayer: (id: string) => void;
  onOpacity: (value: number) => void;
  onMode: (mode: "explore" | "command") => void;
  onFocus: (focus: CommandFocus) => void;
  onOpen: (slug: string) => void;
  onCluster: (slugs: string[]) => void;
  onRemovePlan: (slug: string) => void;
  onRecompute: () => void;
}) {
  const byId = Object.fromEntries(overlays.map((item) => [item.id, item.label]));
  const note = intel?.layer_notes[overlay];
  const shown = LAYER_GROUPS.find((group) => (group.layers as readonly string[]).includes(overlay)) || LAYER_GROUPS[0];
  return (
    <div className="gis">
      <div className="gis-groups" role="tablist" aria-label="Layer groups">
        {LAYER_GROUPS.map((group) => (
          <button
            key={group.id}
            type="button"
            role="tab"
            aria-selected={shown.id === group.id}
            onClick={() => onOverlay(group.layers[0])}
          >
            {group.label}
          </button>
        ))}
      </div>
      <div className="gis-layers" role="radiogroup" aria-label={`${shown.label} layers`}>
        {shown.layers.map((id) => (
          <button key={id} type="button" aria-pressed={overlay === id} onClick={() => onOverlay(id)}>
            {byId[id] || id}
          </button>
        ))}
      </div>
      {(note || layerMissing) && <p className="gis-note">{layerMissing ? "No stored values for this layer." : note}</p>}
      <div className="gis-layers" role="radiogroup" aria-label="Base map">
        {basemaps.map((item) => (
          <button key={item.id} type="button" aria-pressed={basemap === item.id} onClick={() => onBasemap(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      <label className="gis-opacity">
        <span>Fill</span>
        <input type="range" min={0.45} max={0.94} step={0.01} value={opacity} onChange={(event) => onOpacity(Number(event.target.value))} />
      </label>
      <div className="gis-layers">
        {([
          ["canal", "Canals"],
          ["river", "Rivers"],
          ["road", "Roads"],
        ] as const).map(([id, label]) => (
          <button key={id} type="button" aria-pressed={layers[id]} onClick={() => onLayer(id)}>{label}</button>
        ))}
      </div>
      <label className="gis-opacity">
        Highlight
        <select value={mapMode === "command" ? commandFocus : "explore"} onChange={(event) => {
          const value = event.target.value;
          if (value === "explore") onMode("explore");
          else {
            onMode("command");
            onFocus(value as CommandFocus);
          }
        }}>
          <option value="explore">All places</option>
          {COMMAND_FOCI.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
      </label>
      {mapMode === "command" && <p className="gis-note">{intel?.command[commandFocus].sentence || "Loading the attention list."}</p>}
      {plan.length > 0 && <p className="gis-note">{plan.length} on the inspection list.</p>}
      {intel?.scope.can_recompute && <button type="button" onClick={onRecompute}>Recompute</button>}
      {recomputeState && <p className="gis-note">{recomputeState}</p>}
    </div>
  );
}

function ChangeList({
  title,
  rows,
  onOpen,
}: {
  title: string;
  rows: { slug: string; name: string }[];
  onOpen: (slug: string) => void;
}) {
  if (rows.length === 0) return null;
  return (
    <div>
      <h3>{title}</h3>
      <ul>
        {rows.map((row) => (
          <li key={row.slug}><button type="button" className="linkish" onClick={() => onOpen(row.slug)}>{row.name}</button></li>
        ))}
      </ul>
    </div>
  );
}

export function LocationIntel({
  place,
  threatName,
  intel,
  compareSlug,
  planned,
  canPlan,
  canAct,
  onCompare,
  onAdd,
  onAsk,
  onForecast,
  onWhy,
  onNotes,
  onBriefing,
}: {
  place: SelectedRead | null;
  threatName: string;
  intel: MapIntel | null;
  compareSlug: string | null;
  planned: boolean;
  canPlan: boolean;
  canAct: boolean;
  onCompare: (slug: string | null) => void;
  onAdd: () => void;
  onAsk: () => void;
  onForecast: () => void;
  onWhy: () => void;
  onNotes: () => void;
  onBriefing: () => void;
}) {
  if (!place) {
    return (
      <div className="im-location">
        {intel?.geometry_note && <p className="im-note">{intel.geometry_note}</p>}
      </div>
    );
  }
  const parent = place.slug.includes("--") ? place.slug.split("--")[0] : place.slug;
  const mine = intel?.places.find((item) => item.slug === parent);
  const other = intel?.places.find((item) => item.slug === compareSlug) || null;
  const factors = place.factor_rows?.length ? place.factor_rows : mine?.factors || [];
  const skipped = factors.filter((item) => !item.used);
  const hazard = place.hazard_points ?? mine?.hazard_points ?? null;
  const priority = place.priority_points ?? mine?.priority_points ?? null;
  return (
    <div className="im-location">
      <p className="im-kicker">{threatName}</p>
      {scorePair(hazard, priority)}
      <p className="im-meta">
        {place.risk_label || "No class"}
        {place.trend_arrow ? ` ${place.trend_arrow}` : ""}
        {place.trend_direction ? ` ${place.trend_direction}` : ""}
      </p>
      <details>
        <summary>Score meaning</summary>
        <p className="im-note">Hazard is how favorable the conditions are for this threat. Inspection priority is where to spend attention. Neither number is a chance of disease.</p>
        {place.score_origin_note && <p className="im-note">{place.score_origin_note}</p>}
      </details>
      <h3 id="why-risk">Why this area is at risk</h3>
      <p>{place.why_line || mine?.why}</p>
      {factors.length > 0 && (
        <table className="im-factors">
          <caption>Risk factors from this threat&apos;s stored score</caption>
          <thead><tr><th>Factor</th><th>Status</th></tr></thead>
          <tbody>
            {factors.map((factor) => (
              <tr key={factor.id || factor.label}><td>{factor.label}</td><td>{factor.status}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {skipped.length > 0 && (
        <div>
          <h3>Not used</h3>
          <ul>{skipped.map((factor) => <li key={factor.id || factor.label}>{factor.label}</li>)}</ul>
        </div>
      )}
      {place.why_now && (
        <div>
          <h3>Why now</h3>
          <p>{place.why_now.sentence}</p>
          {place.why_now.factors.length > 0 && <p>Current favorable rule factors: {place.why_now.factors.join(", ")}.</p>}
          <p className="im-note">{place.why_now.note}</p>
        </div>
      )}
      <h3>Recommended action</h3>
      <p>{mine?.action || place.action || "No action is stored for this municipality."}</p>
      <div className="im-actions">
        {canPlan && (
          <button type="button" className="secondary" onClick={onAdd} disabled={planned}>
            {planned ? "Added" : "Add to inspection list"}
          </button>
        )}
        <button type="button" className="secondary" onClick={onForecast}>View forecast</button>
        <button type="button" className="secondary" onClick={onWhy}>View why</button>
        <button type="button" className="secondary" onClick={onBriefing}>Open briefing</button>
        <button type="button" className="secondary" onClick={onAsk}>Ask CROPWATCH</button>
        {canAct && <button type="button" className="secondary" onClick={onNotes}>Add field note</button>}
      </div>
      {canPlan && intel && intel.places.length > 1 && (
        <label className="field">
          Compare
          <select value={compareSlug || ""} onChange={(event) => onCompare(event.target.value || null)}>
            <option value="">Choose a municipality</option>
            {intel.places.filter((item) => item.slug !== parent).map((item) => (
              <option key={item.slug} value={item.slug}>{item.name}</option>
            ))}
          </select>
        </label>
      )}
      {other && mine && <CompareTable left={mine} right={other} />}
      {intel?.data && (
        <div className="im-data">
          <h3>Data status</h3>
          <ul>
            {intel.data.checks.map((item) => (
              <li key={item.id}><span>{item.label}</span><b>{item.value}</b></li>
            ))}
          </ul>
          <p className="im-note">{intel.data.interpretation}</p>
        </div>
      )}
    </div>
  );
}

function CompareTable({ left, right }: { left: IntelPlace; right: IntelPlace }) {
  const ids = new Map<string, string>();
  for (const factor of [...left.factors, ...right.factors]) {
    if (factor.id) ids.set(factor.id, factor.label);
  }
  const status = (place: IntelPlace, id: string) => place.factors.find((factor) => factor.id === id)?.status || "Not in this score";
  return (
    <table className="im-factors">
      <caption>{left.name} compared with {right.name}</caption>
      <thead>
        <tr><th></th><th>{left.name}</th><th>{right.name}</th></tr>
      </thead>
      <tbody>
        <tr><td>Hazard</td><td>{left.hazard_points ?? "—"}</td><td>{right.hazard_points ?? "—"}</td></tr>
        <tr><td>Priority</td><td>{left.priority_points ?? "—"}</td><td>{right.priority_points ?? "—"}</td></tr>
        <tr><td>Trend</td><td>{left.trend_direction || "—"}</td><td>{right.trend_direction || "—"}</td></tr>
        {[...ids.entries()].map(([id, label]) => (
          <tr key={id}><td>{label}</td><td>{status(left, id)}</td><td>{status(right, id)}</td></tr>
        ))}
        <tr><td>Rice area</td><td>{left.exposure}</td><td>{right.exposure}</td></tr>
        <tr><td>Data confidence</td><td>{left.confidence || "Not stated"}</td><td>{right.confidence || "Not stated"}</td></tr>
      </tbody>
    </table>
  );
}
