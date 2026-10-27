"use client";

import gsap from "gsap";
import { FormEvent, useMemo, useRef, useState } from "react";
import { useMotion } from "./motion";

export type CommandAction = {
  id: string;
  type: string;
  type_label: string;
  verb: string;
  place: string | null;
  slug: string | null;
  threat: string;
  risk_class: string | null;
  risk_label: string | null;
  trend_direction: string | null;
  trend_arrow: string;
  hazard_points: number | null;
  priority_points: number | null;
  priority_note: string;
  why: string[];
  confidence: string;
  missing: string[];
  window: string;
  recommendation: string;
};

export type CommandRecord = {
  threat: { name: string; confidence: string };
  season?: string;
  forecast_date: string | null;
  updated_at: string | null;
  scope: { audience: string; label: string; can_plan: boolean; can_act: boolean };
  system_status: string;
  situation: {
    state: string;
    label: string;
    summary: string;
    indicators: { id: string; value: number | null; label: string; detail: string }[];
  };
  brief: { lines: string[] };
  today: { slug: string | null; name: string; type_label: string }[];
  upcoming: { slug: string | null; name: string; type_label: string }[];
  actions: CommandAction[];
  changes: { id: string; value: string; label: string; detail: string }[];
  horizon: {
    hours: number;
    label: string;
    areas: { slug: string; name: string; from_points: number; to_points: number; from_class: string; to_class: string }[];
    driver: string;
    forecast_up_sentence?: string;
    class_up_sentence?: string;
  };
  why_now: { summary: string; signals: { id: string; label: string; arrow: string; direction: string; detail: string }[] };
  weather: {
    current: { temp_c: number | null; rh_pct: number | null; rain_mm: number | null; wind_speed_kmh?: number | null } | null;
    impact: string;
  };
  priorities: {
    slug: string;
    name: string;
    threat: string;
    risk_label: string;
    hazard_points: number | null;
    priority_points: number | null;
    trend_arrow: string;
    trend_direction: string | null;
    trend_points: number | null;
    priority_note: string;
  }[];
  clusters: { names: string[] }[];
  map_slugs: string[];
  confidence: { label: string; scope: string; checks: { id: string; label: string; ok: boolean }[]; missing: string[] };
  status_bar: { id: string; label: string; value: string; level: string }[];
  prompts: { id: string; label: string; message: string }[];
};

export type DecisionCall = "go" | "hold" | "escalate";
export type DutyWord = "go" | "hold" | "call";
export type DutyCapacity = { teams: number; stopsPerTeam: number };
export type WatchKind = "hazard_at_least" | "trend_rising" | "forecast_rise";

export type WatchTrigger = {
  id: string;
  slug: string;
  name: string;
  kind: WatchKind;
  threshold: number | null;
};

type DecisionRecord = { call: DecisionCall; at: string };
type PlanItem = { slug: string; name: string };
type ChatItem = { role: string; text: string };
type WatchPlace = { slug: string; name: string; hazard: number | null; trend: string | null };

const DUTY_LABEL: Record<DutyWord, string> = { go: "Go", hold: "Hold", call: "Call" };
const CALLS: DecisionCall[] = ["go", "hold", "escalate"];

function greeting(now: Date) {
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function slotFor(window: string) {
  const text = window.toLowerCase();
  if (text.includes("24")) return { order: 0, label: "This morning" };
  if (text.includes("before the")) return { order: 1, label: "Before the forecast window" };
  if (text.includes("before ")) return { order: 2, label: "Before the score is used" };
  if (text.includes("review")) return { order: 3, label: "While the list is open" };
  if (text.includes("next look")) return { order: 4, label: "On the next look" };
  if (text.includes("72") || text.includes("over the next")) return { order: 5, label: "Through the next 72 hours" };
  return { order: 6, label: window || "Later today" };
}

function recommendedDuty(action: CommandAction): DutyWord {
  if (action.type === "field_validation") return "go";
  if (action.type === "monitor" || action.type === "follow_up") return "hold";
  return "call";
}

function dutyOf(action: CommandAction, call?: DecisionCall): DutyWord {
  if (call === "go") return "go";
  if (call === "hold") return "hold";
  if (call === "escalate") return "call";
  return recommendedDuty(action);
}

function callLabel(call: DecisionCall) {
  if (call === "go") return "Go";
  if (call === "hold") return "Hold";
  return "Escalate";
}

function clockTime(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit" });
}

function watchPlaces(command: CommandRecord): WatchPlace[] {
  const places = new Map<string, WatchPlace>();
  for (const row of command.priorities) {
    places.set(row.slug, { slug: row.slug, name: row.name, hazard: row.hazard_points, trend: row.trend_direction });
  }
  for (const action of command.actions) {
    if (!action.slug || !action.place || places.has(action.slug)) continue;
    places.set(action.slug, { slug: action.slug, name: action.place, hazard: action.hazard_points, trend: action.trend_direction });
  }
  for (const area of command.horizon.areas) {
    if (places.has(area.slug)) continue;
    places.set(area.slug, { slug: area.slug, name: area.name, hazard: area.to_points, trend: null });
  }
  return [...places.values()].sort((left, right) => left.name.localeCompare(right.name));
}

function readPlace(command: CommandRecord, slug: string) {
  return command.priorities.find((row) => row.slug === slug)
    || command.actions.find((row) => row.slug === slug)
    || null;
}

export function watchStatus(command: CommandRecord, watch: WatchTrigger) {
  if (watch.kind === "forecast_rise") {
    const area = command.horizon.areas.find((row) => row.slug === watch.slug);
    if (!area) return { met: false, detail: "No forecast rise of 5 points is stored for this place." };
    const rise = area.to_points - area.from_points;
    return {
      met: rise >= 5,
      detail: `Forecast hazard ${area.from_points} to ${area.to_points}.`,
    };
  }
  const place = readPlace(command, watch.slug);
  if (!place) return { met: false, detail: "This place is not in the current record." };
  if (watch.kind === "trend_rising") {
    const rising = place.trend_direction === "rising";
    return {
      met: rising,
      detail: rising ? "The stored trend is rising." : `The stored trend is ${place.trend_direction || "not saved"}.`,
    };
  }
  const threshold = watch.threshold ?? 70;
  if (place.hazard_points == null) return { met: false, detail: "No hazard score is stored for this place." };
  return {
    met: place.hazard_points >= threshold,
    detail: `Hazard is ${place.hazard_points}. The watch is ${threshold} or higher.`,
  };
}

function visitCandidates(command: CommandRecord, decisions: Record<string, DecisionRecord>) {
  return command.actions
    .filter((action) => {
      if (!action.slug || !action.place) return false;
      const call = decisions[action.id]?.call;
      if (call === "hold" || call === "escalate") return false;
      if (call === "go") return true;
      return action.type === "field_validation";
    })
    .sort((left, right) => (right.priority_points ?? -1) - (left.priority_points ?? -1) || (left.place || "").localeCompare(right.place || ""));
}

export default function CommandCenter({
  command,
  loading,
  error,
  narration,
  plan,
  mapCollection: _mapCollection,
  chat,
  chatBusy,
  decisions,
  watches,
  capacity,
  onOpenPlace,
  onOpenMap,
  onAddPlan: _onAddPlan,
  onBuildPlan: _onBuildPlan,
  onRemovePlan: _onRemovePlan,
  onAsk,
  onRetry,
  onDecide,
  onAddWatch,
  onRemoveWatch,
  onCapacity,
  hideLead = false,
}: {
  command: CommandRecord | null;
  loading: boolean;
  error: string;
  narration: { source: string; text: string } | null;
  plan: PlanItem[];
  mapCollection: unknown;
  chat: ChatItem[];
  chatBusy: boolean;
  decisions: Record<string, DecisionRecord>;
  watches: WatchTrigger[];
  capacity: DutyCapacity;
  onOpenPlace: (slug: string) => void;
  onOpenMap: () => void;
  onAddPlan: (item: PlanItem) => void;
  onBuildPlan: (items: PlanItem[]) => void;
  onRemovePlan: (slug: string) => void;
  onAsk: (message: string) => void;
  onRetry: () => void;
  onDecide: (action: CommandAction, call: DecisionCall) => void;
  onAddWatch: (watch: WatchTrigger) => void;
  onRemoveWatch: (id: string) => void;
  onCapacity: (capacity: DutyCapacity) => void;
  hideLead?: boolean;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const now = useState(() => new Date())[0];
  const motionKey = command ? `${command.threat.name}|${command.forecast_date ?? ""}|${command.actions.length}` : "";
  useMotion(rootRef, () => {
    if (!motionKey) return;
    gsap.from(".cc-lead h2, .duty-block", {
      y: 18,
      autoAlpha: 0,
      duration: 0.45,
      stagger: 0.06,
      ease: "power2.out",
      clearProps: "transform,opacity,visibility",
    });
  }, [motionKey]);

  const audience = command?.scope.audience || "Agriculture Officer";
  const assistantText = narration?.source === "assistant" ? narration.text : "";
  const places = useMemo(() => (command ? watchPlaces(command) : []), [command]);
  const [watchSlug, setWatchSlug] = useState("");
  const [watchKind, setWatchKind] = useState<WatchKind>("hazard_at_least");
  const [threshold, setThreshold] = useState(70);
  const [watchNote, setWatchNote] = useState("");
  const selectedSlug = watchSlug || places[0]?.slug || "";
  const order = useMemo(() => {
    if (!command) return [];
    const groups = new Map<string, { order: number; label: string; items: CommandAction[] }>();
    for (const action of command.actions) {
      const slot = slotFor(action.window);
      const group = groups.get(slot.label) || { ...slot, items: [] };
      group.items.push(action);
      groups.set(slot.label, group);
    }
    return [...groups.values()].sort((left, right) => left.order - right.order);
  }, [command]);
  const visits = command ? visitCandidates(command, decisions) : [];
  const slots = Math.max(1, capacity.teams) * Math.max(1, capacity.stopsPerTeam);
  const fit = visits.slice(0, slots);
  const waiting = visits.slice(slots);
  const listed = new Set(plan.map((item) => item.slug));

  function addWatch(event: FormEvent) {
    event.preventDefault();
    if (!command) return;
    const place = places.find((item) => item.slug === selectedSlug);
    if (!place) {
      setWatchNote("Choose a place from the current record.");
      return;
    }
    const nextThreshold = watchKind === "hazard_at_least" ? Math.min(100, Math.max(0, Math.round(threshold))) : null;
    const duplicate = watches.some((item) => item.slug === place.slug && item.kind === watchKind && item.threshold === nextThreshold);
    if (duplicate) {
      setWatchNote("That watch is already set.");
      return;
    }
    onAddWatch({
      id: `watch:${place.slug}:${watchKind}:${nextThreshold ?? "none"}`,
      slug: place.slug,
      name: place.name,
      kind: watchKind,
      threshold: nextThreshold,
    });
    setWatchNote("");
  }

  return (
    <div className="command" id="command" ref={rootRef}>
      {!hideLead && <header className="cc-lead">
        <p className="cc-kicker">{command?.situation.label || "Command"}</p>
        <h2>{command ? `${greeting(now)}, ${audience}` : greeting(now)}</h2>
        <p className="cc-dek">
          {!command
            ? "Loading today's order."
            : assistantText || command.situation.summary}
        </p>
        <p className="cc-meta">
          {command && !command.scope.can_act
            ? "This account can read the order. It cannot mark Go."
            : "Places, scores, and weather stay on the map. This page is the decision."}
        </p>
        {command && (
          <div className="cc-actions-row">
            <button type="button" className="secondary" onClick={onOpenMap}>Open the map</button>
            <button
              type="button"
              className="secondary"
              disabled={chatBusy}
              onClick={() => onAsk(command.prompts[0]?.message || `What should we do about ${command.threat.name}?`)}
            >
              Ask CROPWATCH
            </button>
          </div>
        )}
      </header>}

      {loading && !command && (
        <div aria-hidden="true">
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          {error} <button className="secondary" type="button" onClick={onRetry}>Try again</button>
        </p>
      )}

      {command && (
        <>
          <div className="duty-grid">
            <section className="duty-block" aria-labelledby="order-title">
              <h2 id="order-title">Order of the day</h2>
              <p className="duty-note">Each line keeps the stored window. Go sends a team. Hold waits. Call is an office step. A decision replaces the recommendation.</p>
              {order.length === 0 && <p className="duty-note">No recommendation is stored for this threat and day.</p>}
              {order.map((group) => (
                <div key={group.label}>
                  <h3>{group.label}</h3>
                  <ol className="duty-list">
                    {group.items.map((action) => {
                      const call = decisions[action.id]?.call;
                      const duty = dutyOf(action, call);
                      const title = action.place ? `${action.verb} ${action.place}` : action.verb;
                      return (
                        <li key={action.id}>
                          <span className="duty-verb" data-duty={duty}>{DUTY_LABEL[duty]}</span>
                          <div>
                            {action.slug ? (
                              <button type="button" className="cc-text-button duty-title" onClick={() => onOpenPlace(action.slug as string)}>{title}</button>
                            ) : (
                              <p className="duty-title">{title}</p>
                            )}
                            <p>{action.recommendation}</p>
                            <p className="duty-note">
                              {action.window}
                              {call ? ` · Your call: ${callLabel(call)}` : ` · Recommended ${DUTY_LABEL[recommendedDuty(action)].toLowerCase()}`}
                            </p>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              ))}
            </section>

            <section className="duty-block" aria-labelledby="capacity-title">
              <h2 id="capacity-title">Team capacity</h2>
              <p className="duty-note">Set how many stops fit today. Holds and escalations do not take a team. This number stays in the session.</p>
              <div className="duty-capacity">
                <label>
                  Teams
                  <input
                    type="number"
                    min={1}
                    max={12}
                    value={capacity.teams}
                    onChange={(event) => onCapacity({ ...capacity, teams: clamp(event.target.value, 1, 12, capacity.teams) })}
                  />
                </label>
                <label>
                  Stops each
                  <input
                    type="number"
                    min={1}
                    max={8}
                    value={capacity.stopsPerTeam}
                    onChange={(event) => onCapacity({ ...capacity, stopsPerTeam: clamp(event.target.value, 1, 8, capacity.stopsPerTeam) })}
                  />
                </label>
              </div>
              <p className="duty-slots">{slots} {slots === 1 ? "stop" : "stops"} today</p>
              {visits.length === 0 ? (
                <p className="duty-note">No field visit is on the order. Holds and calls do not use a team.</p>
              ) : (
                <>
                  <h3>Fits</h3>
                  {fit.length === 0 ? <p className="duty-note">No visit fits in the slots you set.</p> : (
                    <ul className="duty-fit">
                      {fit.map((action) => (
                        <li key={action.id}>
                          <button type="button" className="cc-text-button" onClick={() => onOpenPlace(action.slug as string)}>{action.place}</button>
                          <span>{listed.has(action.slug as string) ? "On the list" : "Open"}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <h3>Waits</h3>
                  {waiting.length === 0 ? <p className="duty-note">Every visit fits.</p> : (
                    <ul className="duty-wait">
                      {waiting.map((action) => (
                        <li key={action.id}>
                          <button type="button" className="cc-text-button" onClick={() => onOpenPlace(action.slug as string)}>{action.place}</button>
                          <span>Next day</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {command.scope.can_plan && (
                    <button
                      type="button"
                      className="secondary"
                      disabled={fit.length === 0}
                      onClick={() => {
                        for (const action of fit) {
                          if (decisions[action.id]?.call !== "go") onDecide(action, "go");
                        }
                      }}
                    >
                      Add the visits that fit
                    </button>
                  )}
                </>
              )}
            </section>
          </div>

          <section className="duty-block" aria-labelledby="log-title">
            <h2 id="log-title">Decision log</h2>
            <p className="duty-note">Go adds the place to the inspection list. Hold or Escalate removes it only if this log had marked it Go. The log stays in this session.</p>
            {command.actions.length === 0 && <p className="duty-note">No recommendation is stored for this record.</p>}
            <ul className="duty-log">
              {command.actions.map((action) => {
                const record = decisions[action.id];
                return (
                  <li key={action.id}>
                    <p className="cc-type">{action.type_label}</p>
                    <p className="duty-title">{action.place ? `${action.verb} ${action.place}` : action.verb}</p>
                    <p>{action.recommendation}</p>
                    <p className="duty-note">{action.window}{record ? ` · ${callLabel(record.call)} at ${clockTime(record.at)}` : ""}</p>
                    <div className="ops-segment" role="group" aria-label={`Decision for ${action.place || action.verb}`}>
                      {CALLS.map((call) => (
                        <button
                          key={call}
                          type="button"
                          aria-pressed={record?.call === call}
                          disabled={call === "go" && (!command.scope.can_plan || !action.slug)}
                          onClick={() => onDecide(action, call)}
                        >
                          {callLabel(call)}
                        </button>
                      ))}
                    </div>
                    {action.slug && (
                      <button type="button" className="secondary" onClick={() => onOpenPlace(action.slug as string)}>Open on the map</button>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="duty-block" aria-labelledby="watch-title">
            <h2 id="watch-title">Watch triggers</h2>
            <p className="duty-note">A watch checks the stored record for this threat and day. It does not create a new score. The map still shows the place.</p>
            <form className="watch-form" onSubmit={addWatch}>
              <label>
                Place
                <select value={selectedSlug} onChange={(event) => setWatchSlug(event.target.value)} disabled={places.length === 0}>
                  {places.length === 0 && <option value="">No place in this record</option>}
                  {places.map((place) => <option key={place.slug} value={place.slug}>{place.name}</option>)}
                </select>
              </label>
              <label>
                Condition
                <select value={watchKind} onChange={(event) => setWatchKind(event.target.value as WatchKind)}>
                  <option value="hazard_at_least">Hazard reaches</option>
                  <option value="trend_rising">Trend is rising</option>
                  <option value="forecast_rise">Forecast rises by 5</option>
                </select>
              </label>
              {watchKind === "hazard_at_least" && (
                <label>
                  Points
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={threshold}
                    onChange={(event) => setThreshold(clamp(event.target.value, 0, 100, threshold))}
                  />
                </label>
              )}
              <button type="submit" className="secondary" disabled={places.length === 0}>Set watch</button>
            </form>
            {watchNote && <p className="duty-note" role="status">{watchNote}</p>}
            {watches.length === 0 ? <p className="duty-note">No watch is set.</p> : (
              <ul className="duty-log">
                {watches.map((watch) => {
                  const status = watchStatus(command, watch);
                  return (
                    <li key={watch.id}>
                      <p className="duty-title">{watch.name}</p>
                      <p>{watchPhrase(watch)}</p>
                      <p className="duty-state" data-met={status.met ? "yes" : "no"}>{status.met ? "Met" : "Watching"}</p>
                      <p className="duty-note">{status.detail}</p>
                      <button type="button" className="secondary" onClick={() => onOpenPlace(watch.slug)}>Open on the map</button>
                      <button type="button" className="linkish" onClick={() => onRemoveWatch(watch.id)}>Remove</button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}
      {chat.length > 0 && <p className="duty-note">The latest answer is in Ask CROPWATCH.</p>}
    </div>
  );
}

function watchPhrase(watch: WatchTrigger) {
  if (watch.kind === "trend_rising") return "Watch until the stored trend is rising.";
  if (watch.kind === "forecast_rise") return "Watch until the forecast hazard rises by 5 points.";
  return `Watch until hazard reaches ${watch.threshold ?? 70}.`;
}

function clamp(value: string, min: number, max: number, fallback: number) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, Math.round(number)));
}
