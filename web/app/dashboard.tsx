"use client";

import maplibregl, { Map } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import gsap from "gsap";
import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import type { AnalyticsReport } from "./analytics-view";
import RiskBoard from "./risk-board";
import { RiceReport } from "./rice-view";
import CommandCenter, { CommandAction, CommandRecord, DecisionCall, DutyCapacity, WatchKind, WatchTrigger } from "./command-center";
import RiceView from "./rice-view";
import { fileToBase64, ObservationAssist, SituationRecord } from "./situation";
import { AdminBoard, WeatherBoard, WeatherDayPoint, weatherPoint } from "./platform";
import { BriefingSlides, CommandBoard } from "./command-board";
import { Icon } from "./icons";
import { AlertsInbox, AskCropwatch, FieldOperations, FieldStop, ReportsDesk } from "./workspaces";
import { CommandFocus, MapControls, MapIntel, SelectedRead } from "./intelligence";
import { Mark } from "./mark";
import { useMotion } from "./motion";

type User = { username: string; role: string; municipality_slug: string | null; display_name: string };
type Threat = { id: string; name: string; summary: string; confidence?: string; season_role?: string };
type PriorityRow = {
  rank: number;
  slug: string;
  name: string;
  risk_class: string;
  risk_label: string;
  score?: number | null;
  exposure_ha: number | null;
  exposure_source?: string | null;
  trend_arrow?: string;
  trend_direction?: string | null;
  trend_sentence?: string | null;
  priority_points?: number | null;
  priority_reasons?: string[];
};
type Briefing = {
  forecast_date: string | null;
  ricelytics: { metric: string; period: string; value: number; unit: string }[];
  high_or_above: number;
  risk_counts: Record<string, number>;
  exposure: { available: boolean; note: string; source: string | null };
  change_note: string;
  world_bank: { indicator: string; year: number; value: number } | null;
  world_bank_note: string;
  pagasa_note: string;
  enso: { season: string; anomaly_c: number; label: string };
  fastest_rising?: { name: string; sentence: string; from_score: number; to_score: number; days: number } | null;
};
type Place = {
  name: string;
  slug: string;
  municipality?: string | null;
  barangay_note: string;
  score: {
    risk_class: string;
    score: number | null;
    explanation: string;
    confidence?: string | null;
    confidence_note?: string | null;
    assumption_note?: string | null;
    season_role?: string | null;
    factors_used: { id?: string; label: string; partial: number; assumed?: boolean }[];
    factors_skipped: { label: string }[];
    exposure_ha: number | null;
    exposure_source: string | null;
  } | null;
  forecast: {
    day_offset: number;
    forecast_date: string;
    temp_c: number;
    temp_min_c?: number | null;
    rh_pct: number;
    hours_rh90?: number | null;
    rain_mm: number;
    wind_speed_kmh?: number | null;
  }[];
  terrain: { elevation_m: number; slope_index: number | null; source: string } | null;
  notes: { body: string; display_name: string }[];
  score_origin?: string;
  score_origin_note?: string;
  factor_rows?: { id?: string | null; label: string; status: string; used: boolean }[];
  why_line?: string;
  why_now?: { available: boolean; sentence: string; factors: string[]; note: string } | null;
  insight?: {
    trend: { available: boolean; arrow: string; direction: string | null; sentence: string };
    drivers: { label: string; points: number; assumed?: boolean }[];
    driver_sentence: string;
    anomaly: { available: boolean; sentence: string };
    hotspot: { sentence: string; neighbor_risk: number | null };
    exposure_sentence: string;
    context_notes: string[];
    priority: { points: number | null; sentence: string; reasons: string[]; limits?: string[] };
    action: string;
  };
};

const COLORS: Record<string, string> = {
  low: "#3d8c4e",
  moderate: "#d89a12",
  high: "#e15a1c",
  very_high: "#c62828",
  insufficient_data: "#8d9488",
};

const RISK_ORDER = ["low", "moderate", "high", "very_high", "insufficient_data"] as const;
const LEGEND_NAMES: Record<string, string> = {
  low: "Low risk",
  moderate: "Moderate risk",
  high: "High risk",
  very_high: "Very high",
  insufficient_data: "No data",
};

const ACCOUNTS = [
  { username: "provincial", password: "nueva-ecija", label: "Provincial agriculture office" },
  { username: "munoz", password: "science-city", label: "Science City of Muñoz" },
  { username: "guest", password: "read-only", label: "Read-only guest" },
];

const LINE_LAYERS = [
  { id: "canal", label: "Canals" },
  { id: "river", label: "Rivers" },
  { id: "road", label: "Roads" },
] as const;

const BASEMAPS = [
  {
    id: "light",
    label: "Light",
    tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
    labels: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"],
    attribution: "Esri, HERE, Garmin, © OpenStreetMap contributors",
  },
  {
    id: "dark",
    label: "Dark",
    tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
    labels: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"],
    attribution: "Esri, HERE, Garmin, © OpenStreetMap contributors",
  },
  {
    id: "satellite",
    label: "Satellite",
    tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
    labels: ["https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"],
    attribution: "Esri, Maxar, Earthstar Geographics",
  },
] as const;

type OverlayStop = readonly [number, string];
type OverlaySpec = {
  id: string;
  label: string;
  field: string;
  unit: string;
  digits: number;
  empty: string;
  stops: readonly OverlayStop[];
};

const OVERLAYS: readonly OverlaySpec[] = [
  { id: "risk", label: "Hazard", field: "risk_class", unit: "", digits: 2, empty: "", stops: [] },
  { id: "priority", label: "Priority", field: "priority_points", unit: "", digits: 0, empty: "Inspection priority is missing for this place.", stops: [[0, "#efe6d6"], [40, "#c4b48a"], [70, "#c45c28"], [85, "#8e2424"]] },
  { id: "change", label: "Change", field: "change_bucket", unit: "", digits: 0, empty: "No saved score is available to compare.", stops: [] },
  { id: "temp", label: "Temperature", field: "temp_c", unit: "°C", digits: 1, empty: "Temperature is missing for this place.", stops: [[22, "#2c5f7c"], [26, "#d8c7a1"], [30, "#d4652f"], [34, "#9f2d2d"]] },
  { id: "rain", label: "Rainfall", field: "rain_mm", unit: "mm", digits: 1, empty: "Rainfall is missing for this place.", stops: [[0, "#e7f0f6"], [2, "#7eb0d4"], [6, "#1d5f8a"], [15, "#0e2438"]] },
  { id: "humidity", label: "Humidity", field: "rh_pct", unit: "%", digits: 0, empty: "Humidity is missing for this place.", stops: [[60, "#efe6d6"], [75, "#7aa0b8"], [90, "#1d5f8a"], [100, "#16324f"]] },
  { id: "wind", label: "Wind", field: "wind_speed_kmh", unit: "km/h", digits: 0, empty: "Wind is missing for this place.", stops: [[0, "#f4efe6"], [12, "#c4b8a8"], [25, "#6b5e52"], [40, "#2a2622"]] },
  { id: "soil", label: "Soil moisture", field: "soil_moisture", unit: "", digits: 2, empty: "Soil moisture is missing for this place.", stops: [[0.1, "#efe6d6"], [0.25, "#8fb4c9"], [0.4, "#1d5f8a"], [0.5, "#16324f"]] },
  { id: "leaf", label: "Leaf wetness", field: "hours_rh90", unit: "h", digits: 0, empty: "Leaf wetness is missing for this place.", stops: [[0, "#efe6d6"], [3, "#8fb4c9"], [6, "#1d5f8a"], [12, "#16324f"]] },
  { id: "elevation", label: "Elevation", field: "elevation_m", unit: "m", digits: 0, empty: "Elevation is missing for this place.", stops: [[0, "#e7f0d8"], [80, "#c4b48a"], [250, "#8a6a45"], [600, "#3d342c"]] },
  { id: "canopy", label: "NDVI", field: "ndvi", unit: "", digits: 2, empty: "NDVI is empty until a Sentinel-2 file is loaded.", stops: [[0.1, "#c4a574"], [0.35, "#a3b18a"], [0.6, "#2d6a4f"], [0.85, "#1b4332"]] },
  { id: "evi", label: "EVI", field: "evi", unit: "", digits: 2, empty: "EVI is empty until a Sentinel-2 file is loaded.", stops: [[0.1, "#c4a574"], [0.3, "#a3b18a"], [0.5, "#2d6a4f"], [0.7, "#1b4332"]] },
  { id: "water", label: "NDWI", field: "ndwi", unit: "", digits: 2, empty: "NDWI is empty until a Sentinel-2 file is loaded.", stops: [[-0.3, "#c4a574"], [0, "#d6d0c4"], [0.2, "#7aa0b8"], [0.5, "#1d5f8a"]] },
  { id: "lswi", label: "LSWI", field: "lswi", unit: "", digits: 2, empty: "LSWI is empty until a Sentinel-2 file is loaded.", stops: [[-0.2, "#c4a574"], [0, "#d6d0c4"], [0.2, "#7aa0b8"], [0.4, "#1d5f8a"]] },
  { id: "flood", label: "Flood fraction", field: "flood_fraction", unit: "", digits: 2, empty: "Flood fraction is empty until a Sentinel-1 file is loaded.", stops: [[0, "#f4efe6"], [0.1, "#8fb4c9"], [0.3, "#1d5f8a"], [0.6, "#16324f"]] },
  { id: "lst", label: "Surface temperature", field: "lst_c", unit: "°C", digits: 0, empty: "Land surface temperature is empty until a satellite file is loaded.", stops: [[20, "#2c5f7c"], [28, "#d8c7a1"], [34, "#d4652f"], [40, "#9f2d2d"]] },
  { id: "rice", label: "Rice area", field: "exposure_ha", unit: "ha", digits: 0, empty: "Rice hectares are empty until a rice-area file is loaded.", stops: [[0, "#f4efe6"], [200, "#c5d5c8"], [1000, "#2d6a4f"], [4000, "#1b4332"]] },
  { id: "rice_fraction", label: "Rice fraction", field: "rice_fraction", unit: "", digits: 2, empty: "Rice fraction is empty until a satellite rice layer is loaded.", stops: [[0, "#f4efe6"], [0.2, "#c5d5c8"], [0.5, "#2d6a4f"], [0.8, "#1b4332"]] },
];

const RISK_COLOR = ["match", ["get", "risk_class"], "low", COLORS.low, "moderate", COLORS.moderate, "high", COLORS.high, "very_high", COLORS.very_high, COLORS.insufficient_data] as maplibregl.ExpressionSpecification;

function overlayById(id: string) {
  return OVERLAYS.find((item) => item.id === id) || OVERLAYS[0];
}

const CHANGE_COLOR = ["match", ["get", "change_bucket"], "increased", "#9f2d2d", "decreased", "#2d6a4f", "new_high", "#d4652f", "unchanged", "#d6d0c4", COLORS.insufficient_data] as maplibregl.ExpressionSpecification;

function paintFor(id: string): maplibregl.ExpressionSpecification {
  const spec = overlayById(id);
  if (spec.id === "risk") return RISK_COLOR;
  if (spec.id === "change") return CHANGE_COLOR;
  const pairs = spec.stops.flatMap(([value, color]) => [value, color]);
  return [
    "case",
    ["==", ["typeof", ["get", spec.field]], "number"],
    ["interpolate", ["linear"], ["get", spec.field], ...pairs],
    COLORS.insufficient_data,
  ] as unknown as maplibregl.ExpressionSpecification;
}

function fillOpacity(opacity: number, basemap: string, focusSlugs: string[]): maplibregl.ExpressionSpecification {
  const roof = basemap === "satellite" ? Math.min(0.88, opacity) : Math.min(0.94, opacity);
  const base = ["interpolate", ["linear"], ["zoom"], 7, roof * 0.7, 10, roof * 0.86, 13, roof] as maplibregl.ExpressionSpecification;
  if (focusSlugs.length === 0) return base;
  return ["case", ["in", ["get", "parent_slug"], ["literal", focusSlugs]], base, ["*", base, 0.22]] as unknown as maplibregl.ExpressionSpecification;
}

function boundaryPaint(basemap: string) {
  if (basemap === "dark") return { color: "#f4f7f1", opacity: 0.82 };
  if (basemap === "satellite") return { color: "#f7f4ea", opacity: 0.92 };
  return { color: "#1c3318", opacity: 0.78 };
}

function hoverCard(properties: Record<string, unknown>, overlayId: string) {
  const name = escapeHtml(String(properties.name || "Place"));
  const kind = properties.municipality ? "Barangay" : "Municipality";
  const parent = properties.municipality ? escapeHtml(String(properties.municipality)) : "";
  const risk = escapeHtml(String(properties.risk_class || "insufficient_data"));
  const label = escapeHtml(String(properties.risk_label || riskLabel(String(properties.risk_class || ""))));
  const hazard = typeof properties.hazard_points === "number" ? String(properties.hazard_points) : "—";
  const priority = typeof properties.priority_points === "number" ? String(properties.priority_points) : "—";
  const reading = escapeHtml(formatOverlay(overlayId, properties));
  return `<div class="place-pop-card" data-risk="${risk}"><p>${kind}${parent ? ` · ${parent}` : ""}</p><strong>${name}</strong><div><span><b>${hazard}</b><small>Hazard</small></span><span><b>${priority}</b><small>Priority</small></span></div><em>${label}</em><small>${reading}</small></div>`;
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[character] || character));
}

function formatOverlay(id: string, properties: Record<string, unknown>) {
  const spec = overlayById(id);
  if (spec.id === "risk") {
    const label = String(properties.risk_label || riskLabel(String(properties.risk_class || "")));
    const score = typeof properties.hazard_points === "number" ? ` ${properties.hazard_points}/100` : "";
    return `${label}${score}`;
  }
  if (spec.id === "priority") {
    return typeof properties.priority_points === "number" ? `Inspection priority ${properties.priority_points}/100` : spec.empty;
  }
  if (spec.id === "change") {
    const bucket = String(properties.change_bucket || "unknown").replace("_", " ");
    return `Risk ${bucket}`;
  }
  const value = properties[spec.field];
  if (typeof value !== "number") return spec.empty;
  const change = spec.id === "canopy" && typeof properties.ndvi_change === "number" ? `, change ${properties.ndvi_change.toFixed(2)}` : "";
  return `${spec.label} ${value.toFixed(spec.digits)}${spec.unit ? ` ${spec.unit}` : ""}${change}`;
}

const WEATHER_LAYERS = ["rain", "temp", "humidity", "wind", "soil", "leaf"] as const;
const MAP_CHAPTERS: { id: MapChapter; label: string; layers: readonly string[] }[] = [
  { id: "risk", label: "Risk", layers: ["risk", "priority", "change"] },
  { id: "weather", label: "Weather", layers: ["temp", "rain", "humidity", "wind", "soil", "leaf"] },
  { id: "rice", label: "Rice", layers: ["rice", "rice_fraction"] },
  { id: "satellite", label: "Satellite", layers: ["canopy", "evi", "water", "lswi", "flood", "lst"] },
  { id: "operations", label: "Operations", layers: ["priority"] },
];

function readingSummary(collection: maplibregl.GeoJSONSourceSpecification["data"] | null, overlayId: string) {
  const spec = overlayById(overlayId);
  if (!WEATHER_LAYERS.includes(spec.id as (typeof WEATHER_LAYERS)[number])) return "";
  if (!collection || typeof collection !== "object" || !("features" in collection) || !Array.isArray(collection.features)) return "";
  const values = collection.features
    .map((feature) => feature.properties?.[spec.field])
    .filter((value): value is number => typeof value === "number");
  if (values.length === 0) return spec.empty;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const high = Math.max(...values);
  const unit = spec.unit ? ` ${spec.unit}` : "";
  return `Mean ${mean.toFixed(spec.digits)}${unit} · highest ${high.toFixed(spec.digits)}${unit}`;
}

const DETAIL_TABS = [
  { id: "place", label: "Place" },
  { id: "forecast", label: "Forecast" },
  { id: "notes", label: "Notes" },
  { id: "briefing", label: "Briefing" },
] as const;

const CHAT_PROMPTS = [
  "Which municipalities should we inspect first this week?",
  "Why is the top municipality in this class?",
  "Which factors were missing?",
  "What changes on forecast day 3?",
];

type DetailTab = (typeof DETAIL_TABS)[number]["id"];
type Pane = "command" | "map" | "weather" | "rice" | "risk" | "analytics" | "operations" | "administration" | "alerts" | "reports";
type MapChapter = "risk" | "weather" | "rice" | "satellite" | "operations";
type ReportKind = "provincial" | "municipality" | "threat" | "inspection" | "validation";
type PlanItem = { slug: string; name: string };
type DecisionRecord = { call: DecisionCall; at: string };

const WATCH_KINDS = new Set<WatchKind>(["hazard_at_least", "trend_rising", "forecast_rise"]);
const DECISION_CALLS = new Set<DecisionCall>(["go", "hold", "escalate"]);

function clampCount(value: unknown, fallback: number, min: number, max: number) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, Math.round(number)));
}

function readDuty(): { decisions: Record<string, DecisionRecord>; watches: WatchTrigger[]; capacity: DutyCapacity } {
  const empty = { decisions: {} as Record<string, DecisionRecord>, watches: [] as WatchTrigger[], capacity: { teams: 2, stopsPerTeam: 3 } };
  if (typeof window === "undefined") return empty;
  try {
    const parsed = JSON.parse(sessionStorage.getItem("cropwatch-duty") || "");
    const decisions: Record<string, DecisionRecord> = {};
    if (parsed?.decisions && typeof parsed.decisions === "object") {
      for (const [id, row] of Object.entries(parsed.decisions as Record<string, { call?: string; at?: string }>)) {
        if (row && DECISION_CALLS.has(row.call as DecisionCall) && typeof row.at === "string") decisions[id] = { call: row.call as DecisionCall, at: row.at };
      }
    }
    const watches = Array.isArray(parsed?.watches)
      ? parsed.watches.filter((item: WatchTrigger) => item && typeof item.id === "string" && typeof item.slug === "string" && typeof item.name === "string" && WATCH_KINDS.has(item.kind))
      : [];
    return {
      decisions,
      watches,
      capacity: {
        teams: clampCount(parsed?.capacity?.teams, 2, 1, 12),
        stopsPerTeam: clampCount(parsed?.capacity?.stopsPerTeam, 3, 1, 8),
      },
    };
  } catch {
    return empty;
  }
}

function formatPeriod(value?: string | null, offset = 0) {
  const match = value ? /^(\d{4})-(\d{2})-(\d{2})/.exec(value) : null;
  const date = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date();
  if (Number.isNaN(date.getTime())) return value || "—";
  date.setDate(date.getDate() + offset);
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function formatUpdated(iso?: string | null) {
  if (!iso) return "Last update time is not available";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Last update time is not available";
  const time = date.toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit" });
  const day = date.toLocaleDateString("en-PH", { month: "short", day: "numeric" });
  return date.toDateString() === new Date().toDateString() ? `Last updated ${time}` : `Last updated ${day}, ${time}`;
}

function riskLabel(riskClass: string) {
  if (riskClass === "insufficient_data") return "No data";
  return riskClass.replaceAll("_", " ");
}

async function api(path: string, token: string, init?: RequestInit) {
  const response = await fetch(`/backend${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail || "Request failed");
  }
  return response.json();
}

function RiskTag({ riskClass, label }: { riskClass: string; label: string }) {
  return (
    <span className="tag">
      <span className="swatch" style={{ background: COLORS[riskClass] || COLORS.insufficient_data }} aria-hidden="true" />
      {label}
    </span>
  );
}

export default function Dashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [username, setUsername] = useState("provincial");
  const [password, setPassword] = useState("nueva-ecija");
  const [loginError, setLoginError] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const [threats, setThreats] = useState<Threat[]>([]);
  const [threat, setThreat] = useState("rice_blast");
  const [season, setSeason] = useState("wet");
  const [day, setDay] = useState(0);
  const [priorityRows, setPriorityRows] = useState<PriorityRow[]>([]);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [algorithms, setAlgorithms] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState<{ dataset: string; state: string; detail: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [dataError, setDataError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [place, setPlace] = useState<Place | null>(null);
  const [placeError, setPlaceError] = useState("");
  const [placeLoading, setPlaceLoading] = useState(false);
  const [note, setNote] = useState("");
  const [noteState, setNoteState] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [chat, setChat] = useState<{ role: string; text: string }[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [layers, setLayers] = useState({ canal: false, river: false, road: false });
  const [basemap, setBasemap] = useState<(typeof BASEMAPS)[number]["id"]>("light");
  const [overlay, setOverlay] = useState("risk");
  const [opacity, setOpacity] = useState(0.82);
  const [intel, setIntel] = useState<MapIntel | null>(null);
  const [mapMode, setMapMode] = useState<"explore" | "command">("explore");
  const [commandFocus, setCommandFocus] = useState<CommandFocus>("field_validation");
  const [clusterSlugs, setClusterSlugs] = useState<string[] | null>(null);
  const [compareSlug, setCompareSlug] = useState<string | null>(null);
  const [recomputeState, setRecomputeState] = useState("");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [layerNote, setLayerNote] = useState("Each shape is a barangay. Rice blast stays Low without 6 humid hours.");
  const [layerCoverage, setLayerCoverage] = useState<Record<string, boolean>>({});
  const [pane, setPane] = useState<Pane>("command");
  const [command, setCommand] = useState<CommandRecord | null>(null);
  const [commandError, setCommandError] = useState("");
  const [layer, setLayer] = useState<SituationRecord | null>(null);
  const [layerError, setLayerError] = useState("");
  const [narration, setNarration] = useState<{ source: string; text: string } | null>(null);
  const [analyticsReport, setAnalyticsReport] = useState<AnalyticsReport | null>(null);
  const [analyticsError, setAnalyticsError] = useState("");
  const [analyticsNarration, setAnalyticsNarration] = useState<string | null>(null);
  const [allThreats, setAllThreats] = useState(false);
  const [riceReport, setRiceReport] = useState<RiceReport | null>(null);
  const [riceError, setRiceError] = useState("");
  const [riceNarration, setRiceNarration] = useState<string | null>(null);
  const [mapCollection, setMapCollection] = useState<maplibregl.GeoJSONSourceSpecification["data"] | null>(null);
  const [plan, setPlan] = useState<PlanItem[]>([]);
  const [fieldStops, setFieldStops] = useState<FieldStop[]>([]);
  const [decisions, setDecisions] = useState<Record<string, DecisionRecord>>(() => readDuty().decisions);
  const [watches, setWatches] = useState<WatchTrigger[]>(() => readDuty().watches);
  const [capacity, setCapacity] = useState<DutyCapacity>(() => readDuty().capacity);
  const [fieldSlug, setFieldSlug] = useState<string | null>(null);
  const [askOpen, setAskOpen] = useState(false);
  const [slidesOpen, setSlidesOpen] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [playMs, setPlayMs] = useState(1700);
  const [mapChapter, setMapChapter] = useState<MapChapter>("risk");
  const [weatherDays, setWeatherDays] = useState<WeatherDayPoint[]>([]);
  const [reportKind, setReportKind] = useState<ReportKind>("provincial");
  const [clock] = useState(() => new Date());
  const [lens, setLens] = useState<null | "priority" | "rising">(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("place");
  const mapRef = useRef<Map | null>(null);
  const framesRef = useRef(new globalThis.Map<number, maplibregl.GeoJSONSourceSpecification["data"]>());
  const dayRef = useRef(day);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const fittedRef = useRef(false);
  const tokenRef = useRef<string | null>(null);
  const placeRef = useRef<Place | null>(null);
  const selectionRef = useRef({ threat, season, day });
  const viewRef = useRef({ basemap, overlay, opacity, focusSlugs: [] as string[] });
  const chatLogRef = useRef<HTMLDivElement>(null);
  const placeRequest = useRef(0);
  const loginRef = useRef<HTMLElement>(null);
  const shellRef = useRef<HTMLElement>(null);
  const workspaceRef = useRef<HTMLElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const detailRef = useRef<HTMLElement>(null);
  const paneReady = useRef(false);
  const listKey = `${pane}|${threat}|${season}|${day}|${priorityRows.length}`;
  tokenRef.current = token;
  placeRef.current = place;
  selectionRef.current = { threat, season, day };
  const commandSlugs = intel?.command[commandFocus]?.slugs || [];
  const lensSlugs = useMemo(() => {
    if (!lens || !mapCollection || typeof mapCollection !== "object" || !("features" in mapCollection) || !Array.isArray(mapCollection.features)) return [];
    const seen = new globalThis.Map<string, { trend?: string; priority?: number }>();
    for (const feature of mapCollection.features) {
      const props = (feature.properties || {}) as Record<string, unknown>;
      const parent = String(props.parent_slug || props.slug || "");
      if (!parent || seen.has(parent)) continue;
      seen.set(parent, {
        trend: typeof props.trend_direction === "string" ? props.trend_direction : undefined,
        priority: typeof props.priority_points === "number" ? props.priority_points : undefined,
      });
    }
    if (lens === "rising") return [...seen].filter(([, row]) => row.trend === "rising").map(([slug]) => slug);
    const scores = [...seen.values()].map((row) => row.priority).filter((value): value is number => typeof value === "number");
    if (scores.length === 0) return [];
    const cutoff = Math.max(70, Math.max(...scores) - 5);
    return [...seen].filter(([, row]) => typeof row.priority === "number" && row.priority >= cutoff).map(([slug]) => slug);
  }, [lens, mapCollection]);
  const weatherPlaces = useMemo(() => {
    if (!mapCollection || typeof mapCollection !== "object" || !("features" in mapCollection) || !Array.isArray(mapCollection.features)) return [];
    const byName = new globalThis.Map<string, { rain: number[]; temp: number[]; rh: number[] }>();
    for (const feature of mapCollection.features) {
      const props = (feature.properties || {}) as Record<string, unknown>;
      const name = String(props.municipality || props.name || "");
      if (!name) continue;
      const bucket = byName.get(name) || { rain: [], temp: [], rh: [] };
      if (typeof props.rain_mm === "number") bucket.rain.push(props.rain_mm);
      if (typeof props.temp_c === "number") bucket.temp.push(props.temp_c);
      if (typeof props.rh_pct === "number") bucket.rh.push(props.rh_pct);
      byName.set(name, bucket);
    }
    const average = (values: number[]) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    return [...byName.entries()].map(([name, bucket]) => ({ name, rain: average(bucket.rain), temp: average(bucket.temp), rh: average(bucket.rh) }));
  }, [mapCollection]);
  const focusSlugs = lens ? lensSlugs : clusterSlugs?.length ? clusterSlugs : mapMode === "command" ? commandSlugs : [];
  viewRef.current = { basemap, overlay, opacity, focusSlugs };

  useMotion(loginRef, () => {
    const root = loginRef.current;
    if (!root) return;
    const tl = gsap.timeline({ defaults: { ease: "power2.out" } });
    tl.from(root.querySelector(".login-hero h1"), { y: 48, autoAlpha: 0, duration: 0.9, ease: "power3.out", clearProps: "transform,opacity,visibility" })
      .from(root.querySelectorAll(".login-hero p"), { y: 22, autoAlpha: 0, duration: 0.55, stagger: 0.08, clearProps: "transform,opacity,visibility" }, "-=0.55")
      .from(root.querySelector(".login-card"), { x: 36, autoAlpha: 0, duration: 0.75, ease: "power3.out", clearProps: "transform,opacity,visibility" }, "-=0.6");
  }, [user?.username]);

  useMotion(shellRef, () => {
    gsap.from(".topbar, .filterbar, .daybar", {
      y: 12,
      autoAlpha: 0,
      duration: 0.4,
      stagger: 0.07,
      ease: "power2.out",
      clearProps: "transform,opacity,visibility",
    });
  }, [user?.username]);

  useMotion(workspaceRef, () => {
    const root = workspaceRef.current;
    if (!root) return;
    if (!paneReady.current) {
      paneReady.current = true;
      return;
    }
    gsap.fromTo(root, { autoAlpha: 0.4 }, {
      autoAlpha: 1,
      duration: 0.28,
      ease: "power2.out",
      clearProps: "opacity,visibility",
    });
  }, [pane, user?.username]);

  useMotion(listRef, () => {
    if (pane !== "map" || priorityRows.length === 0) return;
    const rows = listRef.current?.querySelectorAll("button");
    if (!rows?.length) return;
    gsap.from(Array.from(rows).slice(0, 8), {
      y: 8,
      autoAlpha: 0,
      duration: 0.28,
      stagger: 0.03,
      ease: "power2.out",
      clearProps: "transform,opacity,visibility",
    });
  }, [listKey]);

  useMotion(detailRef, () => {
    if (!place || pane !== "map") return;
    gsap.from(".detail-head", {
      y: 8,
      autoAlpha: 0,
      duration: 0.28,
      ease: "power2.out",
      clearProps: "transform,opacity,visibility",
    });
  }, [place?.slug, pane]);

  useEffect(() => {
    const savedPlan = sessionStorage.getItem("cropwatch-plan");
    const savedField = sessionStorage.getItem("cropwatch-field");
    if (savedPlan) {
      try {
        const parsed = JSON.parse(savedPlan);
        if (Array.isArray(parsed)) setPlan(parsed);
      } catch {
        setPlan([]);
      }
    }
    if (savedField) {
      try {
        const parsed = JSON.parse(savedField);
        if (Array.isArray(parsed)) setFieldStops(parsed);
      } catch {
        setFieldStops([]);
      }
    }
  }, []);

  useEffect(() => {
    sessionStorage.setItem("cropwatch-plan", JSON.stringify(plan));
  }, [plan]);

  useEffect(() => {
    sessionStorage.setItem("cropwatch-field", JSON.stringify(fieldStops));
  }, [fieldStops]);

  useEffect(() => {
    sessionStorage.setItem("cropwatch-duty", JSON.stringify({ decisions, watches, capacity }));
  }, [decisions, watches, capacity]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setDay((current) => (current >= 6 ? 0 : current + 1));
    }, playMs);
    return () => window.clearInterval(timer);
  }, [playing, playMs]);

  dayRef.current = day;

  useEffect(() => {
    if (!token || !threat) return;
    let cancelled = false;
    framesRef.current = new globalThis.Map();
    setWeatherDays([]);
    for (const offset of [0, 1, 2, 3, 4, 5, 6]) {
      api(`/api/map?threat_id=${encodeURIComponent(threat)}&season=${season}&forecast_day=${offset}`, token)
        .then((collection) => {
          if (cancelled) return;
          framesRef.current.set(offset, collection);
          setWeatherDays((current) => [...current.filter((item) => item.day !== offset), weatherPoint(offset, collection)]);
          if (offset === dayRef.current && mapRef.current) draw(collection);
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [token, threat, season, reloadKey]);

  useEffect(() => {
    const cached = framesRef.current.get(day);
    if (cached) draw(cached);
  }, [day]);

  useEffect(() => {
    const saved = sessionStorage.getItem("cropwatch-token");
    const savedUser = sessionStorage.getItem("cropwatch-user");
    if (saved && savedUser) {
      setToken(saved);
      setUser(JSON.parse(savedUser));
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    api("/api/threats", token).then((rows: Threat[]) => {
      setThreats(rows);
      if (rows[0]) setThreat(rows.find((row) => row.id === "rice_blast")?.id || rows[0].id);
    }).catch((error: Error) => setDataError(error.message));
    api("/api/status", token).then(setStatus).catch(() => setStatus([]));
  }, [token]);

  useEffect(() => {
    if (!token || !threat) return;
    let cancelled = false;
    if (!framesRef.current.has(day)) setLoading(true);
    setDataError("");
    setCommandError("");
    setNarration(null);
    setClusterSlugs(null);
    const query = `threat_id=${threat}&season=${season}&forecast_day=${day}`;
    api(`/api/map/intel?${query}`, token)
      .then((payload: MapIntel) => {
        if (!cancelled) setIntel(payload);
      })
      .catch(() => {
        if (!cancelled) setIntel(null);
      });
    api(`/api/layer?${query}`, token)
      .then((payload: SituationRecord) => {
        if (!cancelled) {
          setLayer(payload);
          setLayerError("");
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setLayer(null);
          setLayerError(error.message || "The situation record could not be loaded.");
        }
      });
    api(`/api/command?${query}`, token)
      .then((payload: CommandRecord) => {
        if (!cancelled) setCommand(payload);
      })
      .catch((error: Error) => {
        if (!cancelled) setCommandError(error.message || "The command center could not be loaded.");
      });
    api("/api/command/narrate", token, {
      method: "POST",
      body: JSON.stringify({ threat_id: threat, season, forecast_day: day }),
    })
      .then((payload: { source: string; text: string }) => {
        if (!cancelled) setNarration(payload);
      })
      .catch(() => {
        if (!cancelled) setNarration(null);
      });
    Promise.all([
      api(`/api/priority?${query}`, token),
      api(`/api/briefing?${query}`, token),
      api(`/api/algorithms?${query}`, token),
      api(`/api/map?${query}`, token),
    ])
      .then(([rows, nextBriefing, nextAlgorithms, collection]) => {
        if (cancelled) return;
        setPriorityRows(rows);
        setBriefing(nextBriefing);
        setAlgorithms(nextAlgorithms);
        draw(collection);
      })
      .catch((error: Error) => {
        if (!cancelled) setDataError(error.message || "The briefing could not be loaded. Try again.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, threat, season, day, reloadKey]);

  useEffect(() => {
    if (!token || !threat) return;
    let cancelled = false;
    const threatId = allThreats ? "all" : threat;
    const query = `threat_id=${threatId}&season=${season}&forecast_day=${day}`;
    setAnalyticsError("");
    setAnalyticsNarration(null);
    api(`/api/analytics?${query}`, token)
      .then((payload: AnalyticsReport) => {
        if (!cancelled) setAnalyticsReport(payload);
      })
      .catch((error: Error) => {
        if (!cancelled) setAnalyticsError(error.message || "The analytics could not be loaded.");
      });
    api("/api/analytics/narrate", token, {
      method: "POST",
      body: JSON.stringify({ threat_id: threatId, season, forecast_day: day }),
    })
      .then((payload: { source: string; text: string }) => {
        if (!cancelled) setAnalyticsNarration(payload.source === "assistant" ? payload.text : null);
      })
      .catch(() => {
        if (!cancelled) setAnalyticsNarration(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token, threat, season, day, allThreats, reloadKey]);

  useEffect(() => {
    if (!token || !threat) return;
    let cancelled = false;
    const query = `threat_id=${threat}&season=${season}&forecast_day=${day}`;
    setRiceError("");
    setRiceNarration(null);
    api(`/api/rice?${query}`, token)
      .then((payload: RiceReport) => {
        if (!cancelled) setRiceReport(payload);
      })
      .catch((error: Error) => {
        if (!cancelled) setRiceError(error.message || "The rice context could not be loaded.");
      });
    api("/api/rice/narrate", token, {
      method: "POST",
      body: JSON.stringify({ threat_id: threat, season, forecast_day: day }),
    })
      .then((payload: { source: string; text: string }) => {
        if (!cancelled) setRiceNarration(payload.source === "assistant" ? payload.text : null);
      })
      .catch(() => {
        if (!cancelled) setRiceNarration(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token, threat, season, day, reloadKey]);

  useEffect(() => {
    const slug = placeRef.current?.slug;
    if (!token || !slug) return;
    void openPlace(slug);
  }, [token, threat, season, day, reloadKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer("risk-selected")) return;
    map.setFilter("risk-selected", ["==", ["get", "slug"], place?.slug || "__none__"]);
  }, [place]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => mapRef.current?.resize());
    return () => cancelAnimationFrame(frame);
  }, [pane, token, place]);

  useEffect(() => {
    const log = chatLogRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [chat, chatBusy]);

function featureBounds(data: maplibregl.GeoJSONSourceSpecification["data"]): [[number, number], [number, number]] | null {
  if (!data || typeof data !== "object" || !("features" in data) || !Array.isArray(data.features)) return null;
  let minX = 180;
  let minY = 90;
  let maxX = -180;
  let maxY = -90;
  const walk = (coords: unknown) => {
    if (!Array.isArray(coords)) return;
    if (typeof coords[0] === "number" && typeof coords[1] === "number") {
      minX = Math.min(minX, coords[0]);
      minY = Math.min(minY, coords[1]);
      maxX = Math.max(maxX, coords[0]);
      maxY = Math.max(maxY, coords[1]);
      return;
    }
    for (const child of coords) walk(child);
  };
  for (const feature of data.features) {
    const geometry = feature.geometry as { coordinates?: unknown } | undefined;
    walk(geometry?.coordinates);
  }
  if (minX > maxX || minY > maxY) return null;
  return [[minX, minY], [maxX, maxY]];
}

function applySelection(map: Map) {
    if (!map.getLayer("risk-selected")) return;
    map.setFilter("risk-selected", ["==", ["get", "slug"], placeRef.current?.slug || "__none__"]);
  }

  function applyView(map: Map) {
    const view = viewRef.current;
    for (const base of BASEMAPS) {
      const visible = view.basemap === base.id ? "visible" : "none";
      if (map.getLayer(`base-${base.id}`)) map.setLayoutProperty(`base-${base.id}`, "visibility", visible);
      if (map.getLayer(`labels-${base.id}`)) map.setLayoutProperty(`labels-${base.id}`, "visibility", visible);
    }
    if (map.getLayer("risk-fill")) {
      map.setPaintProperty("risk-fill", "fill-color", paintFor(view.overlay));
      map.setPaintProperty("risk-fill", "fill-opacity", fillOpacity(view.opacity, view.basemap, view.focusSlugs));
    }
    if (map.getLayer("risk-line")) {
      const weather = WEATHER_LAYERS.includes(view.overlay as (typeof WEATHER_LAYERS)[number]);
      const context = !weather && view.overlay !== "risk" && view.overlay !== "priority" && view.overlay !== "change";
      const line = boundaryPaint(view.basemap);
      map.setPaintProperty("risk-line", "line-color", weather ? "#1c3318" : context ? RISK_COLOR : line.color);
      map.setPaintProperty("risk-line", "line-width", ["interpolate", ["linear"], ["zoom"], 7, weather ? 0.35 : context ? 1.3 : 0.6, 11, weather ? 0.6 : context ? 1.8 : 1, 14, weather ? 0.8 : context ? 2.2 : 1.4]);
      map.setPaintProperty("risk-line", "line-opacity", weather ? 0.28 : context ? 0.9 : line.opacity);
    }
    if (map.getLayer("risk-focus")) {
      const slugs = view.focusSlugs;
      map.setFilter(
        "risk-focus",
        slugs.length ? ["in", ["get", "parent_slug"], ["literal", slugs]] : ["==", ["get", "slug"], "__none__"],
      );
    }
  }

  function draw(collection: maplibregl.GeoJSONSourceSpecification["data"]) {
    setMapCollection(collection);
    const features = collection && typeof collection === "object" && "features" in collection && Array.isArray(collection.features)
      ? collection.features
      : [];
    const coverage: Record<string, boolean> = {};
    for (const spec of OVERLAYS) {
      if (spec.id === "risk" || spec.id === "change" || spec.stops.length === 0) continue;
      coverage[spec.field] = features.some((feature) => typeof feature.properties?.[spec.field] === "number");
    }
    setLayerCoverage(coverage);
    const view = viewRef.current;
    const sources: maplibregl.StyleSpecification["sources"] = {
      risk: { type: "geojson", data: collection },
    };
    const rasterLayers: maplibregl.LayerSpecification[] = [];
    const labelLayers: maplibregl.LayerSpecification[] = [];
    for (const base of BASEMAPS) {
      const visible = view.basemap === base.id ? "visible" : "none";
      sources[`base-${base.id}`] = {
        type: "raster",
        tiles: [...base.tiles],
        tileSize: 256,
        attribution: base.attribution,
      };
      rasterLayers.push({
        id: `base-${base.id}`,
        type: "raster",
        source: `base-${base.id}`,
        layout: { visibility: visible },
      });
      sources[`labels-${base.id}`] = {
        type: "raster",
        tiles: [...base.labels],
        tileSize: 256,
      };
      labelLayers.push({
        id: `labels-${base.id}`,
        type: "raster",
        source: `labels-${base.id}`,
        layout: { visibility: visible },
      });
    }
    const style: maplibregl.StyleSpecification = {
      version: 8,
      sources,
      layers: [
        ...rasterLayers,
        {
          id: "risk-fill",
          type: "fill",
          source: "risk",
          paint: {
            "fill-color": paintFor(view.overlay),
            "fill-opacity": fillOpacity(view.opacity, view.basemap, view.focusSlugs),
            "fill-antialias": true,
          },
        },
        {
          id: "risk-line",
          type: "line",
          source: "risk",
          layout: { "line-join": "miter", "line-cap": "butt" },
          paint: {
            "line-color": boundaryPaint(view.basemap).color,
            "line-width": ["interpolate", ["linear"], ["zoom"], 7, 0.6, 11, 1, 14, 1.4],
            "line-offset": ["interpolate", ["linear"], ["zoom"], 7, -0.3, 11, -0.5, 14, -0.7],
            "line-opacity": boundaryPaint(view.basemap).opacity,
          },
        },
        {
          id: "risk-selected",
          type: "line",
          source: "risk",
          filter: ["==", ["get", "slug"], "__none__"],
          layout: { "line-join": "miter" },
          paint: {
            "line-color": "#111111",
            "line-width": 2.25,
            "line-offset": -1.1,
          },
        },
        {
          id: "risk-focus",
          type: "line",
          source: "risk",
          filter: ["==", ["get", "slug"], "__none__"],
          layout: { "line-join": "miter" },
          paint: {
            "line-color": "#111111",
            "line-width": 3,
            "line-opacity": 0.95,
          },
        },
        ...labelLayers,
      ],
    };
    if (!mapRef.current) {
      const map = new maplibregl.Map({ container: "map", style, center: [121.05, 15.6], zoom: 8 });
      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: "place-pop", maxWidth: "240px" });
      popupRef.current = popup;
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("mouseenter", "risk-fill", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mousemove", "risk-fill", (event) => {
        const properties = event.features?.[0]?.properties as Record<string, unknown> | undefined;
        if (!properties?.name) return;
        popup.setLngLat(event.lngLat).setHTML(hoverCard(properties, viewRef.current.overlay)).addTo(map);
      });
      map.on("mouseleave", "risk-fill", () => { map.getCanvas().style.cursor = ""; popup.remove(); });
      map.on("click", "risk-fill", (event) => {
        const slug = event.features?.[0]?.properties?.slug;
        if (!slug) return;
        map.easeTo({ center: event.lngLat, zoom: Math.max(map.getZoom(), 11) });
        void openPlace(String(slug));
      });
      map.on("load", () => {
        applyView(map);
        applySelection(map);
        const bounds = featureBounds(collection);
        if (bounds && !fittedRef.current) {
          fittedRef.current = true;
          map.fitBounds(bounds, { padding: 12, duration: 0 });
        }
      });
      mapRef.current = map;
      return;
    }
    const source = mapRef.current.getSource("risk") as maplibregl.GeoJSONSource | undefined;
    if (source) source.setData(collection);
    applyView(mapRef.current);
    applySelection(mapRef.current);
  }

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !map.getLayer("risk-fill")) return;
    applyView(map);
  }, [basemap, overlay, opacity, mapMode, commandFocus, clusterSlugs, intel, lens, lensSlugs]);

  useEffect(() => {
    if (!lens || lensSlugs.length === 0) return;
    const map = mapRef.current;
    if (!map || !mapCollection || typeof mapCollection !== "object" || !("features" in mapCollection) || !Array.isArray(mapCollection.features)) return;
    const subset = {
      type: "FeatureCollection" as const,
      features: mapCollection.features.filter((feature) => lensSlugs.includes(String((feature.properties as { parent_slug?: string } | null)?.parent_slug || ""))),
    };
    const bounds = featureBounds(subset);
    if (bounds) map.fitBounds(bounds, { padding: { top: 48, bottom: 64, left: 220, right: 48 }, duration: 720, maxZoom: 10.2 });
  }, [lens, lensSlugs, mapCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !token) return;
    for (const kind of ["canal", "river", "road"] as const) {
      const id = `line-${kind}`;
      if (!layers[kind]) {
        if (map.getLayer(id)) map.removeLayer(id);
        if (map.getLayer(`${id}-case`)) map.removeLayer(`${id}-case`);
        if (map.getSource(id)) map.removeSource(id);
        continue;
      }
      api(`/api/lines?kind=${kind}`, token).then((collection) => {
        if (!collection.loaded) {
          setLayerNote(`${kind[0].toUpperCase()}${kind.slice(1)} lines are not loaded. Run the OSM ingest.`);
          return;
        }
        if (map.getSource(id)) {
          (map.getSource(id) as maplibregl.GeoJSONSource).setData(collection);
        } else {
          map.addSource(id, { type: "geojson", data: collection });
          map.addLayer({
            id: `${id}-case`,
            type: "line",
            source: id,
            layout: { "line-join": "round", "line-cap": "round" },
            paint: {
              "line-color": "#f7f4ee",
              "line-width": ["interpolate", ["linear"], ["zoom"], 8, kind === "road" ? 2.4 : 2, 12, kind === "road" ? 5 : 3.5],
            },
          } as maplibregl.LayerSpecification);
          map.addLayer({
            id,
            type: "line",
            source: id,
            layout: { "line-join": "round", "line-cap": "round" },
            paint: {
              "line-color": kind === "road" ? "#2b3542" : "#1d5f8a",
              "line-width": ["interpolate", ["linear"], ["zoom"], 8, kind === "road" ? 1.3 : 1.1, 12, kind === "road" ? 3.2 : 2.2],
            },
          } as maplibregl.LayerSpecification);
        }
      }).catch((error: Error) => setLayerNote(error.message));
    }
  }, [layers, token]);

  async function signIn(nextUser = username, nextPassword = password) {
    setLoginError("");
    setSigningIn(true);
    try {
      const response = await fetch("/backend/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: nextUser, password: nextPassword }),
      });
      const payload = await response.json().catch(() => ({ detail: "Sign-in failed." }));
      if (!response.ok) {
        setLoginError(payload.detail || "Sign-in failed. Check the username and password, then try again.");
        return;
      }
      sessionStorage.setItem("cropwatch-token", payload.token);
      sessionStorage.setItem("cropwatch-user", JSON.stringify(payload.user));
      setToken(payload.token);
      setUser(payload.user);
      setUsername(nextUser);
      setPassword(nextPassword);
    } catch {
      setLoginError("Could not reach the risk service. Wait a moment and try again.");
    } finally {
      setSigningIn(false);
    }
  }

  function signOut() {
    sessionStorage.clear();
    setToken(null);
    setUser(null);
    setPlace(null);
    setChat([]);
    setNote("");
    setNoteState("");
    setPriorityRows([]);
    setBriefing(null);
    setAlgorithms(null);
    setPane("command");
    setCommand(null);
    setNarration(null);
    setPlan([]);
    setFieldStops([]);
    setDecisions({});
    setWatches([]);
    setCapacity({ teams: 2, stopsPerTeam: 3 });
    setMapCollection(null);
    setDetailTab("place");
    popupRef.current?.remove();
    fittedRef.current = false;
    mapRef.current?.remove();
    mapRef.current = null;
  }

  function showCluster(slugs: string[]) {
    setClusterSlugs(slugs);
    setMapMode("explore");
    const map = mapRef.current;
    const data = mapCollection;
    if (!map || !data || typeof data !== "object" || !("features" in data) || !Array.isArray(data.features)) return;
    const subset = {
      type: "FeatureCollection" as const,
      features: data.features.filter((feature) => slugs.includes(String(feature.properties?.parent_slug || ""))),
    };
    const bounds = featureBounds(subset);
    if (bounds) map.fitBounds(bounds, { padding: 48, duration: 600 });
  }

  async function recomputeScores() {
    if (!token || user?.role !== "provincial") return;
    setRecomputeState("Recomputing stored scores.");
    try {
      await api("/api/recompute", token, { method: "POST" });
      setRecomputeState("Scores recomputed.");
      setReloadKey((value) => value + 1);
    } catch (error) {
      setRecomputeState(error instanceof Error ? error.message : "The scores could not be recomputed.");
    }
  }

  function flyToSlug(slug: string) {
    const parent = slug.split("--")[0];
    const map = mapRef.current;
    const data = mapCollection;
    if (!map || !data || typeof data !== "object" || !("features" in data) || !Array.isArray(data.features)) return;
    const subset = {
      type: "FeatureCollection" as const,
      features: data.features.filter((feature) => {
        const props = (feature.properties || {}) as Record<string, unknown>;
        return props.parent_slug === parent || props.slug === parent || props.slug === slug;
      }),
    };
    const bounds = featureBounds(subset);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (bounds) map.fitBounds(bounds, { padding: { top: 56, bottom: 72, left: 220, right: 390 }, duration: reduce ? 0 : 680, maxZoom: 11.2 });
  }

  async function openPlace(slug: string, focusDetail = false) {
    const currentToken = tokenRef.current;
    if (!currentToken) return;
    flyToSlug(slug);
    const selected = selectionRef.current;
    const request = ++placeRequest.current;
    setPlaceLoading(true);
    setPlaceError("");
    if (focusDetail) {
      setPane("map");
      setDetailTab("place");
    }
    try {
      const detail = await api(
        `/api/places/${slug}?threat_id=${selected.threat}&season=${selected.season}&forecast_day=${selected.day}`,
        currentToken,
      );
      if (placeRequest.current !== request) return;
      setPlace(detail);
    } catch (error) {
      if (placeRequest.current !== request) return;
      setPlace(null);
      setPlaceError(error instanceof Error ? error.message : "Could not open this barangay.");
    } finally {
      if (placeRequest.current === request) setPlaceLoading(false);
    }
  }

  async function sendChat(event?: FormEvent, preset?: string) {
    event?.preventDefault();
    const message = (preset || chatInput).trim();
    if (!token || !message || chatBusy) return;
    setChat((items) => [...items, { role: "user", text: message }]);
    if (!preset) setChatInput("");
    setChatBusy(true);
    try {
      const context = `Officer context: workspace ${pane}, role ${user?.role || "unknown"}, threat ${threat}, place ${place?.name || "none"}, forecast offset ${day}.`;
      const payload = await api("/api/chat", token, {
        method: "POST",
        body: JSON.stringify({ message: `${context}\n${message}`, threat_id: threat, season, forecast_day: day }),
      });
      const reply = payload.reply?.trim() || "The briefing assistant returned an empty reply. Try another question.";
      setChat((items) => [...items, { role: "assistant", text: reply }]);
    } catch (error) {
      const text = error instanceof Error ? error.message : "The briefing assistant could not answer. Try again.";
      setChat((items) => [...items, { role: "assistant", text }]);
    } finally {
      setChatBusy(false);
    }
  }

  async function saveNote(event: FormEvent) {
    event.preventDefault();
    if (!token || !place || !note.trim()) return;
    setNoteState("saving");
    try {
      await api("/api/notes", token, { method: "POST", body: JSON.stringify({ place_slug: place.slug, body: note.trim() }) });
      setNote("");
      setNoteState("Note saved.");
      const detail = await api(`/api/places/${place.slug}?threat_id=${threat}&season=${season}&forecast_day=${day}`, token);
      setPlace(detail);
    } catch (error) {
      setNoteState(error instanceof Error ? error.message : "The note could not be saved. Try again.");
    }
  }

  function onTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const next = event.key === "ArrowRight"
      ? DETAIL_TABS[(index + 1) % DETAIL_TABS.length]
      : DETAIL_TABS[(index - 1 + DETAIL_TABS.length) % DETAIL_TABS.length];
    setDetailTab(next.id);
    document.getElementById(`tab-${next.id}`)?.focus();
  }

  function addInspection(item: PlanItem, reason = "Added from the current record.", threatLabel?: string, hazard: number | null = null, priority: number | null = null) {
    const label = threatLabel || threats.find((row) => row.id === threat)?.name || "Threat";
    setPlan((current) => current.some((row) => row.slug === item.slug) ? current : [...current, item]);
    setFieldStops((current) => current.some((row) => row.slug === item.slug) ? current : [
      ...current,
      { slug: item.slug, name: item.name, threat: label, reason, hazard, priority, status: "listed", note: "", observedAt: null, checks: [false, false, false, false, false] },
    ]);
    setFieldSlug(item.slug);
  }

  function decide(action: CommandAction, call: DecisionCall) {
    const previous = decisions[action.id]?.call;
    const next = previous === call ? null : call;
    setDecisions((current) => {
      const copy = { ...current };
      if (!next) delete copy[action.id];
      else copy[action.id] = { call: next, at: new Date().toISOString() };
      return copy;
    });
    if (!action.slug || !action.place) return;
    if (next === "go") {
      addInspection(
        { slug: action.slug, name: action.place },
        "Marked Go on the decision log.",
        action.threat,
        action.hazard_points,
        action.priority_points,
      );
      return;
    }
    if (previous === "go") {
      const stillGoing = command?.actions.some((item) => item.id !== action.id && item.slug === action.slug && decisions[item.id]?.call === "go");
      if (!stillGoing) {
        setPlan((current) => current.filter((item) => item.slug !== action.slug));
        setFieldStops((current) => current.filter((item) => item.slug !== action.slug));
      }
    }
  }

  function advanceStop(slug: string, status: FieldStop["status"]) {
    setFieldStops((current) => current.map((stop) => {
      if (stop.slug !== slug) {
        if (status === "routed" && (stop.status === "listed" || stop.status === "planned")) return { ...stop, status: "routed" };
        return stop;
      }
      return { ...stop, status, observedAt: status === "observed" ? new Date().toISOString() : stop.observedAt };
    }));
  }

  const loadedDatasets = status.filter((item) => item.state === "loaded").length;
  const freshness = status.length === 0 ? "Freshness unavailable" : `${loadedDatasets} of ${status.length} datasets loaded`;
  const horizonLabel = day === 0 ? "Now" : day <= 3 ? `+${day * 24}h` : `+${day}d`;
  const routeInfo = algorithms && typeof algorithms === "object" && "route" in algorithms ? algorithms.route as { stops?: string[]; distance_km?: number | null } : null;
  const basePrompts = command?.prompts || CHAT_PROMPTS.map((label, index) => ({ id: String(index), label, message: label }));
  const seenPrompts = new Set(basePrompts.map((item) => item.message));
  const askPrompts = [...basePrompts, ...(layer?.prompts || []).filter((item) => !seenPrompts.has(item.message))];

  if (!token || !user) {
    return (
      <main className="login-wrap" ref={loginRef}>
        <section className="login-hero">
          <div className="login-lockup">
            <Mark draw key={signingIn ? "signing" : "idle"} />
            <p className="login-brand">CROPWATCH</p>
          </div>
          <h1>See where the rice is at risk.</h1>
          <p>Favorable conditions, not a diagnosis. Nueva Ecija monitoring. The map does not say a pest is present.</p>
        </section>
        <section className="login-card">
          <h2>Demo accounts</h2>
          <div className="accounts">
            {ACCOUNTS.map((account) => (
              <button
                key={account.username}
                className="secondary"
                type="button"
                disabled={signingIn}
                onClick={() => signIn(account.username, account.password)}
              >
                Sign in as {account.label}
              </button>
            ))}
          </div>
          <form method="post" onSubmit={(event) => { event.preventDefault(); void signIn(); }} aria-describedby={loginError ? "login-error" : undefined}>
            <h2>Username and password</h2>
            <label>
              Username
              <input
                name="username"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            {loginError && <p className="error" id="login-error" role="alert">{loginError}</p>}
            <button className="primary" type="submit" disabled={signingIn}>
              {signingIn ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  const harvested = briefing?.ricelytics.find((row) => row.metric === "harvested_area");
  const yieldRow = briefing?.ricelytics.find((row) => row.metric === "yield");
  const production = briefing?.ricelytics.find((row) => row.metric === "production");
  const algo = algorithms as {
    graph?: string;
    canal_note?: string;
    clusters?: { names: string[]; size: number; zone: boolean }[];
    route?: { stops?: string[]; distance_km?: number | null; note?: string };
  } | null;
  const threatName = threats.find((item) => item.id === threat)?.name || "Threat";
  const usedFactors = place?.score?.factors_used ?? [];
  const leadFactor = usedFactors.reduce<(typeof usedFactors)[number] | null>((best, factor) => (
    !best || factor.partial > best.partial ? factor : best
  ), null);
  const assumedCount = usedFactors.filter((factor) => factor.assumed).length;
  const seasonModifies = (place?.score?.season_role || threats.find((item) => item.id === threat)?.season_role) === "modifier";
  const activeOverlay = overlayById(overlay);
  const overlayEmpty = activeOverlay.id !== "risk" && layerCoverage[activeOverlay.field] === false;
  const dockNote = overlayEmpty
    ? activeOverlay.empty
    : intel?.layer_notes[overlay] || (layerNote.startsWith("Risk classes") || layerNote.startsWith("Each shape")
      ? (briefing?.change_note || "Favorable conditions, not a diagnosis.")
      : layerNote);
  const selectedRead: SelectedRead | null = place ? {
    name: place.municipality ? `${place.name}, ${place.municipality}` : place.name,
    slug: place.slug,
    municipality: place.municipality,
    score_origin_note: place.score_origin_note,
    hazard_points: place.score?.score == null ? null : Math.round(place.score.score * 100),
    priority_points: place.insight?.priority.points ?? null,
    risk_label: place.score ? riskLabel(place.score.risk_class) : null,
    trend_arrow: place.insight?.trend.arrow || "",
    trend_direction: place.insight?.trend.direction || null,
    why_line: place.why_line,
    why_now: place.why_now,
    factor_rows: place.factor_rows,
    action: place.insight?.action || null,
    exposure: place.score?.exposure_ha == null ? "Not loaded" : "Available",
    confidence: place.score?.confidence || null,
  } : null;
  const planned = place ? plan.some((item) => item.slug === place.slug) : false;
  const forecastNow = place?.forecast.find((item) => item.day_offset === day) || place?.forecast[0] || null;
  const compareParent = place ? (place.slug.includes("--") ? place.slug.split("--")[0] : place.slug) : "";
  const renderControls = () => (
    <MapControls
      overlay={overlay}
      overlays={OVERLAYS.map((item) => ({ id: item.id, label: item.label }))}
      basemap={basemap}
      basemaps={BASEMAPS.map((item) => ({ id: item.id, label: item.label }))}
      layers={layers}
      opacity={opacity}
      mapMode={mapMode}
      commandFocus={commandFocus}
      intel={intel}
      plan={plan}
      layerMissing={overlayEmpty}
      layerNote={layerNote}
      recomputeState={recomputeState}
      onOverlay={setOverlay}
      onBasemap={(id) => setBasemap(id as (typeof BASEMAPS)[number]["id"])}
      onLayer={(id) => setLayers((current) => ({ ...current, [id]: !current[id as "canal"] }))}
      onOpacity={setOpacity}
      onMode={(mode) => {
        setMapMode(mode);
        if (mode === "command") setClusterSlugs(null);
      }}
      onFocus={setCommandFocus}
      onOpen={(slug) => void openPlace(slug)}
      onCluster={showCluster}
      onRemovePlan={(slug) => setPlan((current) => current.filter((item) => item.slug !== slug))}
      onRecompute={() => void recomputeScores()}
    />
  );

  return (
    <>
      <a className="skip" href="#workspace">Skip to workspace</a>
      <main className="shell ops" ref={shellRef}>
        <nav className="ops-nav" aria-label="Sections">
          <p className="ops-brand"><Mark /><span>CROPWATCH</span></p>
          {([
            ["Monitor", [["command", "Command", "command"], ["map", "Map", "map"], ["weather", "Weather", "weather"], ["rice", "Rice", "rice"]]],
            ["Analyze", [["risk", "Risk", "risk"], ["analytics", "Analytics", "analytics"]]],
            ["Act", [["operations", "Operations", "operations"], ["alerts", "Alerts", "alerts"], ["reports", "Reports", "reports"], ["administration", "Administration", "admin"]]],
          ] as const).map(([group, items]) => (
            <div className="nav-group" key={group} role="group" aria-label={group}>
              <span className="nav-label">{group}</span>
              {items.map(([id, label, icon]) => (
                <button key={id} type="button" aria-pressed={pane === id} onClick={() => setPane(id)}><Icon name={icon} size={18} />{label}</button>
              ))}
            </div>
          ))}
          <div className="nav-group" role="group" aria-label="Assistant">
            <span className="nav-label">Assist</span>
            <button type="button" className="nav-ai" aria-pressed={askOpen} onClick={() => setAskOpen(true)}><Icon name="spark" size={18} />Ask CROPWATCH</button>
            <button type="button" aria-pressed={slidesOpen} onClick={() => setSlidesOpen(true)}><Icon name="slides" size={18} />Briefing slides</button>
          </div>
          <div className="ops-who">
            <span>{user.role === "provincial" ? "Provincial" : user.role === "municipal" ? "Municipality" : "Guest"}</span>
            <strong>{user.display_name}</strong>
          </div>
          <button className="secondary" type="button" onClick={signOut}>Sign out</button>
        </nav>
        <header className="ops-bar">
          <label className="ops-control">
            <span>Threat</span>
            <select value={threats.length ? threat : ""} onChange={(event) => setThreat(event.target.value)} disabled={threats.length === 0} aria-label="Threat">
              {threats.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <div className="ops-control">
            <span>Season</span>
            <div className="ops-segment" role="radiogroup" aria-label="Season">
              <button type="button" aria-pressed={season === "wet"} onClick={() => setSeason("wet")}>Wet</button>
              <button type="button" aria-pressed={season === "dry"} onClick={() => setSeason("dry")}>Dry</button>
            </div>
          </div>
          <div className="ops-control">
            <span>Date</span>
            <strong>{command?.forecast_date ? formatPeriod(command.forecast_date) : formatPeriod(null, day)}</strong>
          </div>
          <div className="ops-control ops-play">
            <span>Horizon</span>
            <div className="ops-player">
              <button type="button" className="play-toggle" aria-pressed={playing} onClick={() => setPlaying((current) => !current)}>
                <Icon name={playing ? "pause" : "play"} size={15} />{playing ? "Pause" : "Play"}
              </button>
              <button type="button" className="secondary icon-btn" aria-label="Previous forecast day" onClick={() => { setPlaying(false); setDay((current) => Math.max(0, current - 1)); }}><Icon name="prev" size={16} /></button>
              <button type="button" className="secondary icon-btn" aria-label="Next forecast day" onClick={() => { setPlaying(false); setDay((current) => Math.min(6, current + 1)); }}><Icon name="next" size={16} /></button>
              <label className="play-speed">Speed
                <select aria-label="Playback speed" value={playMs} onChange={(event) => setPlayMs(Number(event.target.value))}>
                  <option value={2400}>Slow</option>
                  <option value={1700}>Normal</option>
                  <option value={900}>Fast</option>
                </select>
              </label>
              <div className="ops-segment" role="radiogroup" aria-label="Forecast horizon">
                {[0, 1, 2, 3, 4, 5, 6].map((offset) => (
                  <button key={offset} type="button" aria-pressed={day === offset} onClick={() => { setPlaying(false); setDay(offset); }}>
                    {offset === 0 ? "Now" : offset <= 3 ? `+${offset * 24}h` : `+${offset}d`}
                  </button>
                ))}
              </div>
              <span className="play-track" aria-hidden="true"><i key={`${playing}-${day}`} className={playing ? "is-playing" : ""} style={{ width: `${(day / 6) * 100}%` }} /></span>
            </div>
          </div>
          <p className="ops-updated" title="Scores use the latest stored run. Weather is an Open-Meteo model field, not a live sensor.">
            {command?.scope.label || "Nueva Ecija"} · Updated {formatUpdated(command?.updated_at)} · {freshness}
          </p>
          <button type="button" className="ask-btn" onClick={() => setAskOpen(true)}><Icon name="spark" size={16} />Ask CROPWATCH</button>
          {dataError && <button className="secondary" type="button" onClick={() => setReloadKey((value) => value + 1)}>Retry</button>}
        </header>
        <header className="topbar" hidden>
          <div className="brand">
            <Mark />
            <div className="brand-copy">
              <h1>CROPWATCH</h1>
              <p>Nueva Ecija Agricultural Intelligence</p>
            </div>
          </div>
          <div className="top-meta">
            <p>{clock.toLocaleDateString("en-PH", { weekday: "short", month: "short", day: "numeric", year: "numeric" })}</p>
            <p>{formatUpdated(command?.updated_at)}</p>
            <p>{command?.system_status || (loading ? "Loading scores" : "Scores unavailable")}</p>
            <p>{user.display_name}</p>
          </div>
          <button className="ghost" type="button" onClick={signOut}>Sign out</button>
        </header>
        <section className="filterbar" aria-label="Map filters" data-view={pane}>
          <div className="view-switch" role="group" aria-label="Section">
            <button type="button" aria-pressed={pane === "command"} onClick={() => setPane("command")}>Command</button>
            <button type="button" aria-pressed={pane === "map"} onClick={() => setPane("map")}>Map</button>
            <button type="button" aria-pressed={pane === "analytics"} onClick={() => setPane("analytics")}>Analytics</button>
            <button type="button" aria-pressed={pane === "rice"} onClick={() => setPane("rice")}>Rice</button>
          </div>
          <label className="field">
            Threat
            <select value={threats.length ? threat : ""} onChange={(event) => setThreat(event.target.value)} disabled={threats.length === 0}>
              {threats.length === 0 && <option value="">Unavailable</option>}
              {threats.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.confidence === "low" ? `${item.name} (low confidence)` : item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Season
            <select value={season} onChange={(event) => setSeason(event.target.value)}>
              <option value="wet">Wet</option>
              <option value="dry">Dry</option>
            </select>
          </label>
          <ul className="legend" aria-label="Risk classes and barangay counts">
            {RISK_ORDER.map((key) => (
              <li key={key}>
                <span className="swatch" style={{ background: COLORS[key] }} aria-hidden="true" />
                <span className="legend-name">{LEGEND_NAMES[key]}</span>
                <span className="legend-count">{briefing ? (briefing.risk_counts[key] ?? 0) : "—"}</span>
              </li>
            ))}
          </ul>
          {loading && <p className="status" role="status">Updating the map.</p>}
          {dataError && (
            <p className="error" role="alert">
              {dataError}{" "}
              {dataError.toLowerCase().includes("sign in") ? (
                <button className="secondary" type="button" onClick={signOut}>Sign in</button>
              ) : (
                <button className="secondary" type="button" onClick={() => setReloadKey((value) => value + 1)}>Try again</button>
              )}
            </p>
          )}
        </section>
        <div className="daybar" hidden={pane === "map"}>
          <p className="daybar-label" id="forecast-day-label">Forecast day</p>
          <div className="days" role="radiogroup" aria-labelledby="forecast-day-label">
            {[0, 1, 2, 3, 4, 5, 6].map((offset) => (
              <label key={offset}>
                <input
                  type="radio"
                  name="forecast-day"
                  value={offset}
                  checked={day === offset}
                  aria-label={offset === 0 ? "Today" : `Day ${offset}`}
                  onChange={() => setDay(offset)}
                />
                {offset}
              </label>
            ))}
          </div>
          {briefing?.forecast_date && <p className="day-date">{briefing.forecast_date}</p>}
        </div>
        <section className="workspace" id="workspace" data-pane={pane} data-selected={place ? "true" : "false"} ref={workspaceRef}>
          {pane === "command" && (
            <>
            <CommandBoard
              command={command}
              layer={layer}
              analytics={analyticsReport}
              weatherDays={weatherDays}
              narration={narration}
              day={day}
              userName={user.display_name}
              canPlan={user.role !== "guest"}
              planSlugs={plan.map((item) => item.slug)}
              onDay={(next) => { setPlaying(false); setDay(next); }}
              onOpenMap={() => setPane("map")}
              onOpenWeather={() => { setMapChapter("weather"); setOverlay("rain"); setPane("weather"); }}
              onOpenRisk={() => setPane("risk")}
              onOpenPlace={(slug) => void openPlace(slug, true)}
              onAddPlan={(item) => item.slug && addInspection({ slug: item.slug, name: item.place || item.slug }, item.recommendation, item.threat, item.hazard_points, item.priority_points)}
              onAsk={(message) => { setAskOpen(true); void sendChat(undefined, message); }}
              onPresent={() => setSlidesOpen(true)}
            />
            <details className="cb-duty">
              <summary><Icon name="calendar" size={16} />Duty planner, watches, and decision log</summary>
            <CommandCenter
              hideLead
              command={command}
              loading={loading}
              error={commandError}
              narration={narration}
              plan={plan}
              mapCollection={mapCollection}
              chat={chat}
              chatBusy={chatBusy}
              onOpenPlace={(slug) => void openPlace(slug, true)}
              onOpenMap={() => setPane("map")}
              onAddPlan={(item) => addInspection(item)}
              onBuildPlan={(items) => items.forEach((item) => addInspection(item, "Built from field-validation recommendations."))}
              onRemovePlan={(slug) => {
                setPlan((current) => current.filter((item) => item.slug !== slug));
                setFieldStops((current) => current.filter((item) => item.slug !== slug));
              }}
              onAsk={(message) => { setAskOpen(true); void sendChat(undefined, message); }}
              onRetry={() => setReloadKey((value) => value + 1)}
              decisions={decisions}
              watches={watches}
              capacity={capacity}
              onDecide={decide}
              onAddWatch={(watch) => setWatches((current) => current.some((item) => item.id === watch.id) ? current : [...current, watch])}
              onRemoveWatch={(id) => setWatches((current) => current.filter((item) => item.id !== id))}
              onCapacity={setCapacity}
            />
            </details>
            </>
          )}
          {pane === "weather" && (
            <WeatherBoard
              command={command}
              layer={layer}
              series={weatherDays}
              places={weatherPlaces}
              day={day}
              onOpenMap={() => { setMapChapter("weather"); setOverlay("rain"); setPane("map"); setPlaying(true); }}
            />
          )}
          {(pane === "risk" || pane === "analytics") && (
            <RiskBoard
              mode={pane === "risk" ? "risk" : "patterns"}
              report={allThreats ? null : analyticsReport}
              threats={threats}
              threat={threat}
              loading={loading}
              error={analyticsError}
              canPlan={user.role !== "guest"}
              onThreat={(id) => { setAllThreats(false); setThreat(id); }}
              onOpenPlace={(slug) => void openPlace(slug, true)}
              onOpenMap={() => { setMapChapter("risk"); setOverlay("risk"); setPane("map"); }}
              onAddPlan={(item) => {
                const row = analyticsReport?.ranking.find((placeRow) => placeRow.slug === item.slug);
                addInspection(item, "Added from risk.", analyticsReport?.threat?.name, row?.hazard_points ?? null, row?.priority_points ?? null);
              }}
              onRetry={() => setReloadKey((value) => value + 1)}
            />
          )}
          {pane === "rice" && (
            <RiceView
              report={riceReport}
              loading={loading}
              error={riceError}
              narration={riceNarration}
              onOpenPlace={(slug) => void openPlace(slug, true)}
              onAddPlan={(item) => {
                const row = riceReport?.actions.find((action) => action.slug === item.slug);
                addInspection(item, "Added from rice intelligence.", riceReport?.threat.name, row?.hazard_points ?? null, row?.priority_points ?? null);
              }}
              onRetry={() => setReloadKey((value) => value + 1)}
            />
          )}
          {pane === "administration" && (
            <AdminBoard
              layer={layer}
              command={command}
              onOpenOperations={() => setPane("operations")}
            />
          )}
          {pane === "operations" && (
            <FieldOperations
              command={command}
              stops={fieldStops}
              canPlan={user.role !== "guest"}
              route={routeInfo}
              active={fieldSlug}
              onOpen={(slug) => void openPlace(slug, true)}
              onAdd={(stop) => addInspection({ slug: stop.slug, name: stop.name }, stop.reason, stop.threat, stop.hazard, stop.priority)}
              onAdvance={advanceStop}
              onNote={(slug, noteBody) => setFieldStops((current) => current.map((stop) => stop.slug === slug ? { ...stop, note: noteBody } : stop))}
              onCheck={(slug, index) => setFieldStops((current) => current.map((stop) => {
                if (stop.slug !== slug) return stop;
                const checks = [...stop.checks];
                checks[index] = !checks[index];
                return { ...stop, checks };
              }))}
              onSelect={setFieldSlug}
              onShowMap={() => {
                const slugs = fieldStops.map((stop) => stop.slug);
                setClusterSlugs(slugs.length ? slugs : null);
                setMapMode("explore");
                const slug = fieldSlug || slugs[0];
                if (slug) void openPlace(slug, true);
                else setPane("map");
              }}
              onReadNote={(body) => api("/api/notes/read", token, { method: "POST", body: JSON.stringify({ body }) })}
              onReviewImage={async (file) => {
                const media = file.type === "image/png" || file.type === "image/webp" ? file.type : "image/jpeg";
                return api("/api/field-image", token, {
                  method: "POST",
                  body: JSON.stringify({ media_type: media, data_base64: await fileToBase64(file) }),
                });
              }}
              routeReading={layer?.route}
            />
          )}
          {pane === "alerts" && (
            <AlertsInbox
              command={command}
              analytics={analyticsReport}
              stops={fieldStops}
              onOpen={(slug) => void openPlace(slug, true)}
              onOpenOperations={() => setPane("operations")}
            />
          )}
          {pane === "reports" && (
            <ReportsDesk
              kind={reportKind}
              onKind={setReportKind}
              command={command}
              analytics={analyticsReport}
              rice={riceReport}
              stops={fieldStops}
              onOpenMap={() => setPane("map")}
              onOpenPlace={(slug) => void openPlace(slug, true)}
            />
          )}
          <aside className="rail" aria-label="Map controls">
            <div className="rail-scroll">{renderControls()}</div>
            <div className="rail-legacy" hidden>
            <div className="priority-block">
              <h2>Inspection priority</h2>
              {loading && priorityRows.length === 0 ? (
                <div aria-hidden="true">
                  {Array.from({ length: 8 }, (_, index) => <div className="skeleton" key={index} />)}
                </div>
              ) : dataError ? (
                <p className="missing">Priority appears after the briefing loads.</p>
              ) : priorityRows.length === 0 ? (
                <p className="empty">No places for this threat and day.</p>
              ) : (
                <div className="stack-list" ref={listRef}>
                  {priorityRows.map((row) => {
                    const tint = Math.round(24 + Math.max(0, Math.min(1, row.score ?? 0)) * 56);
                    const color = COLORS[row.risk_class] || COLORS.insufficient_data;
                    return (
                      <button
                        key={row.slug}
                        type="button"
                        data-risk={row.risk_class}
                        title={`${row.name}, ${row.risk_label}${row.score != null ? `, hazard ${row.score.toFixed(2)}` : ""}${row.trend_sentence ? `. ${row.trend_sentence}` : ""}${row.priority_points != null ? ` Inspection priority ${row.priority_points}.` : ""}`}
                        aria-label={`${row.rank}. ${row.name}, ${row.risk_label}${row.score != null ? `, hazard ${row.score.toFixed(2)}` : ""}${row.trend_direction ? `, ${row.trend_direction}` : ""}${row.priority_points != null ? `, inspection priority ${row.priority_points}` : ""}`}
                        aria-current={place?.slug === row.slug ? "true" : undefined}
                        onClick={() => void openPlace(row.slug, true)}
                      >
                        <span className="place-name">{row.rank}. {row.name}</span>
                        <span
                          className="score-pill"
                          style={{ background: `color-mix(in srgb, ${color} ${tint}%, var(--surface))` }}
                        >
                          {row.trend_arrow && <span className={`trend trend-${row.trend_direction || "flat"}`}>{row.trend_arrow} </span>}
                          {row.priority_points != null ? row.priority_points : row.score != null ? row.score.toFixed(2) : "—"}
                        </span>
                        <span className="priority-track" aria-hidden="true">
                          <span style={{ width: `${Math.round(Math.max(0, Math.min(100, row.priority_points ?? (row.score ?? 0) * 100)))}%`, background: color }} />
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="rail-foot">
              <dl className="facts" aria-label="Provincial briefing">
                <div><dt>Harvested</dt><dd>{harvested ? `${harvested.value.toLocaleString()} ha` : "—"}</dd></div>
                <div><dt>Yield</dt><dd>{yieldRow ? `${yieldRow.value} t/ha` : "—"}</dd></div>
                <div><dt>Production</dt><dd>{production ? `${production.value.toLocaleString()} t` : "—"}</dd></div>
                <div><dt title="Barangays rated high or very high">High+</dt><dd>{briefing?.high_or_above ?? "—"}</dd></div>
                <div><dt title={briefing?.fastest_rising?.sentence}>Fastest rise</dt><dd>{briefing?.fastest_rising?.name ?? "—"}</dd></div>
                <div><dt>Exposure</dt><dd title={briefing?.exposure.note}>{briefing ? (briefing.exposure.available ? "Yes" : "No") : "—"}</dd></div>
                <div><dt>ENSO</dt><dd title={briefing ? `${briefing.enso.label} ${briefing.enso.season}` : undefined}>{briefing ? `${briefing.enso.label} ${briefing.enso.anomaly_c}` : "—"}</dd></div>
              </dl>
              <details className="disclosure">
                <summary>Loaded data</summary>
                {status.length === 0 && <p className="missing">Dataset status is not available yet.</p>}
                {status.map((item) => (
                  <p key={item.dataset} className="missing"><b>{item.dataset}</b> — {item.state}. {item.detail}</p>
                ))}
              </details>
            </div>
            </div>
          </aside>
          <div className="map-wrap">
            <div id="map" role="region" aria-label="Intelligence map. Select an area to see its hazard, inspection priority, and why it is scored that way." />
            <div className="weather-player">
              <div className="weather-layers" role="radiogroup" aria-label="Map mode">
                {MAP_CHAPTERS.map((chapter) => (
                  <button
                    key={chapter.id}
                    type="button"
                    aria-pressed={mapChapter === chapter.id}
                    onClick={() => {
                      setMapChapter(chapter.id);
                      setOverlay(chapter.layers[0]);
                    }}
                  >
                    {chapter.label}
                  </button>
                ))}
              </div>
              <div className="weather-layers" role="radiogroup" aria-label="Map layer">
                {(MAP_CHAPTERS.find((chapter) => chapter.id === mapChapter)?.layers || []).map((id) => (
                  <button key={id} type="button" aria-pressed={overlay === id} onClick={() => setOverlay(id)}>
                    {overlayById(id).label}
                  </button>
                ))}
              </div>
              <div className="weather-play">
                <button
                  type="button"
                  className="play-toggle"
                  aria-pressed={playing}
                  onClick={() => {
                    if (playing) {
                      setPlaying(false);
                      return;
                    }
                    setMapChapter("weather");
                    if (!WEATHER_LAYERS.includes(overlay as (typeof WEATHER_LAYERS)[number])) setOverlay("rain");
                    setPlaying(true);
                  }}
                >
                  {playing ? "Pause" : "Play weather"}
                </button>
                <div className="ops-segment" role="radiogroup" aria-label="Forecast playback">
                  {[0, 1, 2, 3, 4, 5, 6].map((offset) => (
                    <button key={offset} type="button" aria-pressed={day === offset} onClick={() => { setPlaying(false); setDay(offset); }}>
                      {offset === 0 ? "Now" : offset <= 3 ? `+${offset * 24}h` : `+${offset}d`}
                    </button>
                  ))}
                </div>
              </div>
              <p>
                <strong>{overlayById(overlay).label}</strong>
                <span>{command?.forecast_date ? formatPeriod(command.forecast_date) : formatPeriod(null, day)}</span>
                <span>{readingSummary(mapCollection, overlay) || "Stored Open-Meteo forecast for this day."}</span>
              </p>
              <span className="play-track" aria-hidden="true"><i key={`${playing}-${day}`} className={playing ? "is-playing" : ""} style={{ width: `${(day / 6) * 100}%` }} /></span>
            </div>
            <div className="map-tools">{renderControls()}</div>
            {activeOverlay.stops.length > 0 && (
              <div className="map-scale map-scale-float">
                <p>{activeOverlay.label}{activeOverlay.unit ? ` (${activeOverlay.unit})` : ""}</p>
                <div className="bar" style={{ background: `linear-gradient(90deg, ${activeOverlay.stops.map((stop) => stop[1]).join(", ")})` }} />
              </div>
            )}
            <ul className="map-legend" aria-label="Risk severity">
              {RISK_ORDER.map((key) => (
                <li key={key}>
                  <span className="swatch" style={{ background: COLORS[key] }} aria-hidden="true" />
                  <span>{LEGEND_NAMES[key]}</span>
                  <b>{briefing ? (briefing.risk_counts[key] ?? 0) : "—"}</b>
                </li>
              ))}
            </ul>
            {overlay !== "risk" && (
              <p className="map-status" title={dockNote}>{activeOverlay.label}. {dockNote}</p>
            )}
          </div>
          <aside className="panel right drawer" aria-label="Selected municipality" ref={detailRef}>
            <header className="drawer-head">
              <div>
                <p className="drawer-kicker">{threatName}</p>
                <h2>{selectedRead ? selectedRead.name : "Select a municipality"}</h2>
                <p className="drawer-meta">{place?.municipality || command?.scope.label || "Nueva Ecija"}</p>
              </div>
              {place && (
                <button type="button" className="drawer-close" onClick={() => { setPlace(null); setPlaceError(""); }}>Close</button>
              )}
            </header>
            <div className="drawer-body">
              {placeError && <p className="error" role="alert">{placeError}</p>}
              {placeLoading && <p className="status" role="status">Opening this municipality.</p>}
              {!place && !placeLoading && <p className="empty">Select a municipality on the map.</p>}
              {place && (
                <>
                  <div className="sheet-tabs" role="tablist" aria-label="Place details">
                    {([
                      ["place", "Now"],
                      ["forecast", "Forecast"],
                      ["notes", "Inspect"],
                    ] as const).map(([id, label]) => (
                      <button key={id} type="button" role="tab" aria-selected={detailTab === id} onClick={() => setDetailTab(id)}>{label}</button>
                    ))}
                  </div>

                  <div className="sheet-score" data-risk={place.score?.risk_class || "none"}>
                    <div>
                      <span>Hazard</span>
                      <strong>{selectedRead?.hazard_points ?? "—"}</strong>
                      {place.score ? <RiskTag riskClass={place.score.risk_class} label={riskLabel(place.score.risk_class)} /> : <b>No score</b>}
                    </div>
                    <div>
                      <span>Priority</span>
                      <strong>{place.insight?.priority.points ?? "—"}</strong>
                      <em className={`trend trend-${place.insight?.trend.direction || "flat"}`}>
                        {place.insight?.trend.arrow ? `${place.insight.trend.arrow} ` : ""}
                        {place.insight?.trend.direction || "No trend"}
                      </em>
                    </div>
                  </div>

                  {detailTab === "place" && (
                    <section className="sheet-block">
                      <h3>Why this score</h3>
                      <p>{place.why_line || place.insight?.driver_sentence || "No stored explanation for this place."}</p>
                      {place.insight?.drivers && place.insight.drivers.length > 0 && (
                        <ul className="factor-chips">
                          {place.insight.drivers.slice(0, 4).map((factor) => (
                            <li key={factor.label} data-sign={factor.points > 0 ? "up" : factor.points < 0 ? "down" : "flat"}>
                              <b>{factor.points > 0 ? `+${factor.points}` : factor.points}</b>
                              {factor.label}
                            </li>
                          ))}
                        </ul>
                      )}
                      <h3>This horizon</h3>
                      {forecastNow ? (
                        <dl className="sheet-metrics">
                          <div><dt>Temp</dt><dd>{forecastNow.temp_c}°</dd></div>
                          <div><dt>Humidity</dt><dd>{forecastNow.rh_pct}%</dd></div>
                          <div><dt>Rain</dt><dd>{forecastNow.rain_mm}</dd></div>
                          <div><dt>Wind</dt><dd>{forecastNow.wind_speed_kmh ?? "—"}</dd></div>
                        </dl>
                      ) : <p className="drawer-note">Weather for this horizon is not loaded.</p>}
                      <p className="drawer-note">Rice area {place.score?.exposure_ha == null ? "not loaded" : `${place.score.exposure_ha} ha`}. Elevation {place.terrain ? `${Math.round(place.terrain.elevation_m)} m` : "not loaded"}.</p>
                    </section>
                  )}

                  {detailTab === "forecast" && (
                    <section className="sheet-block">
                      <h3>Stored forecast</h3>
                      {place.forecast.length === 0 ? <p className="drawer-note">No forecast is stored for this place.</p> : (
                        <ol className="forecast-pips">
                          {place.forecast.map((item) => (
                            <li key={item.day_offset} data-current={item.day_offset === day ? "true" : "false"}>
                              <b>{item.day_offset === 0 ? "Now" : `+${item.day_offset}d`}</b>
                              <span>{item.temp_c}°</span>
                              <span>{item.rh_pct}%</span>
                              <span>{item.rain_mm} mm</span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </section>
                  )}

                  {detailTab === "notes" && (
                    <section className="sheet-block">
                      <h3>What to do</h3>
                      <p className="drawer-action">{place.insight?.action || "No recommended action is stored."}</p>
                      {user.role !== "guest" && selectedRead && (
                        <button
                          type="button"
                          className="inspect-go"
                          disabled={planned}
                          onClick={() => addInspection(
                            { slug: place.slug, name: selectedRead.name },
                            place.insight?.action || "Added from the map.",
                            threatName,
                            selectedRead.hazard_points,
                            place.insight?.priority.points ?? null,
                          )}
                        >
                          {planned ? "On the inspection list" : "Add to inspections"}
                        </button>
                      )}
                      <button type="button" className="secondary" onClick={() => setPane("operations")}>Open inspections</button>
                      <h3>Field note</h3>
                      {user.role === "guest" ? <p className="drawer-note">This account cannot add field notes.</p> : (
                        <form onSubmit={saveNote}>
                          <textarea value={note} onChange={(event) => { setNote(event.target.value); setNoteState(""); }} rows={3} aria-label="Field note" />
                          <button className="inspect-go" type="submit" disabled={noteState === "saving" || !note.trim()}>
                            {noteState === "saving" ? "Saving…" : "Save note"}
                          </button>
                          {noteState && noteState !== "saving" && <p className={noteState === "Note saved." ? "status" : "error"} role="status">{noteState}</p>}
                        </form>
                      )}
                      {place.notes.length > 0 && (
                        <ul className="note-list">
                          {place.notes.map((item, index) => <li key={index}><span>{item.display_name}</span>{item.body}</li>)}
                        </ul>
                      )}
                      <ObservationAssist
                        note={note}
                        placeName={selectedRead?.name}
                        disabled={user.role === "guest"}
                        onRead={(body) => api("/api/notes/read", token, { method: "POST", body: JSON.stringify({ body }) })}
                        onReviewImage={async (file) => {
                          const media = file.type === "image/png" || file.type === "image/webp" ? file.type : "image/jpeg";
                          return api("/api/field-image", token, {
                            method: "POST",
                            body: JSON.stringify({ media_type: media, data_base64: await fileToBase64(file) }),
                          });
                        }}
                      />
                    </section>
                  )}
                </>
              )}
            </div>
          </aside>
        </section>
        <BriefingSlides
          open={slidesOpen}
          command={command}
          layer={layer}
          analytics={analyticsReport}
          weatherDays={weatherDays}
          narration={narration}
          day={day}
          onClose={() => setSlidesOpen(false)}
          onOpenPlace={(slug) => { setPane("command"); void openPlace(slug, true); }}
        />
        <AskCropwatch
          open={askOpen}
          workspace={pane === "map" ? "Map" : pane === "weather" ? "Weather" : pane === "risk" ? "Risk" : pane === "analytics" ? "Analytics" : pane === "rice" ? "Rice" : pane === "operations" ? "Operations" : pane === "administration" ? "Administration" : pane === "alerts" ? "Alerts" : pane === "reports" ? "Reports" : "Command"}
          role={user.role}
          threat={threatName}
          place={place?.name || "None selected"}
          time={horizonLabel}
          prompts={askPrompts}
          chat={chat}
          busy={chatBusy}
          input={chatInput}
          places={(command?.priorities || []).map((row) => ({ slug: row.slug, name: row.name }))}
          onInput={setChatInput}
          onAsk={(message) => void sendChat(undefined, message)}
          onClose={() => setAskOpen(false)}
          onOpenWorkspace={(id) => { setAskOpen(false); setPane(id); }}
          onOpenPlace={(slug) => { setAskOpen(false); void openPlace(slug, true); }}
        />
      </main>
    </>
  );
}
