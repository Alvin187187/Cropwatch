"use client";

import { useState } from "react";

export type EvidenceCard = { sentence: string; evidence: string[] };

export type AttentionItem = EvidenceCard & {
  rank: number;
  slug: string;
  name: string;
  threat: string;
  signal: string;
  action: string;
  urgency: string;
  field: string;
};

export type NoteReading = {
  observations: string[];
  missing: string[];
  suggested: string[];
  boundary: string;
  source: string;
};

export type ImageReading = {
  configured: boolean;
  sentence: string;
  indicators: string[];
  questions: string[];
  source: string;
};

export type SituationRecord = {
  source: string;
  scope: string;
  threat: { name: string };
  as_of: string | null;
  completeness: EvidenceCard;
  empty: string | null;
  attention: AttentionItem[];
  emerging: { label: string; slugs: string[]; names: string[]; sentence: string; evidence: string[] }[];
  patterns: { id: string; title: string; sentence: string; evidence: string[]; names: string[] }[];
  forecast: { slug: string; name: string; sentence: string; evidence: string[] }[];
  convergence: { slug: string; name: string; sentence: string; evidence: string[] }[];
  rice: EvidenceCard | null;
  weather: EvidenceCard | null;
  inspections: { slug: string; name: string; sentence: string; field: string; action: string; urgency: string; evidence: string[] }[];
  brief: Record<"weather" | "emerging" | "priorities" | "forecast" | "actions", EvidenceCard>;
  admin: Record<"workload" | "overdue" | "assignment" | "notes", EvidenceCard>;
  route: (EvidenceCard & { stops?: { name: string; slug: string | null }[] }) | null;
  timeline: { slug: string; name: string; sentence: string; events: { when: string | null; label: string; detail: string }[] }[];
  prompts: { id: string; label: string; message: string }[];
  rainfall?: EvidenceCard | null;
};

const BRIEF = [
  ["weather", "Weather situation"],
  ["emerging", "Emerging monitoring conditions"],
  ["priorities", "Highest-priority locations"],
  ["forecast", "Forecast changes"],
  ["actions", "Recommended actions"],
] as const;

const ADMIN = [
  ["workload", "Workload"],
  ["overdue", "No recent field note"],
  ["assignment", "Assignment"],
  ["notes", "Field notes on record"],
] as const;

function Lines({ items }: { items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <ul className="sit-evidence">
      {items.map((item) => <li key={item}>{item}</li>)}
    </ul>
  );
}

function Block({
  title,
  card,
  action,
  urgency,
  field,
  slug,
  onOpen,
}: {
  title?: string;
  card: EvidenceCard | null | undefined;
  action?: string;
  urgency?: string;
  field?: string;
  slug?: string | null;
  onOpen?: (slug: string) => void;
}) {
  if (!card) return null;
  return (
    <article className="sit-card">
      {title && <h3>{title}</h3>}
      {field && <p className="sit-field">{field}</p>}
      <p>{card.sentence}</p>
      <Lines items={card.evidence} />
      {action && <p className="sit-action">{action}{urgency ? ` Urgency ${urgency}.` : ""}</p>}
      {slug && onOpen && <button type="button" className="secondary" onClick={() => onOpen(slug)}>Open on the map</button>}
    </article>
  );
}

export function SituationView({
  record,
  loading,
  error,
  onOpenPlace,
  onAsk,
  onRetry,
}: {
  record: SituationRecord | null;
  loading: boolean;
  error: string;
  onOpenPlace: (slug: string) => void;
  onAsk: (message: string) => void;
  onRetry: () => void;
}) {
  return (
    <div className="analytics" id="situation">
      <header className="an-lead">
        <p className="an-kicker">Situation record</p>
        <h2>{record ? `${record.scope} · ${record.threat.name}` : "Nueva Ecija"}</h2>
        <p className="an-note">{record?.completeness.sentence || "The situation record is loading."}</p>
        <p className="an-note">{record?.source || "From the situation record."}</p>
      </header>
      {loading && !record && <p className="status">Loading the situation record.</p>}
      {error && <p className="error" role="alert">{error} <button type="button" className="secondary" onClick={onRetry}>Try again</button></p>}
      {record && (
        <>
          <section aria-label="Daily brief">
            <h3>Daily brief</h3>
            {BRIEF.map(([id, title]) => <Block key={id} title={title} card={record.brief[id]} />)}
          </section>
          <section aria-label="Attention">
            <h3>Attention</h3>
            {record.attention.length === 0 && <p>{record.empty}</p>}
            {record.attention.map((item) => (
              <Block
                key={item.slug}
                title={`${item.rank}. ${item.name} · ${item.signal}`}
                card={item}
                action={item.action}
                urgency={item.urgency}
                slug={item.slug}
                onOpen={onOpenPlace}
              />
            ))}
          </section>
          <section aria-label="Emerging monitoring areas">
            <h3>Emerging monitoring areas</h3>
            {record.emerging.length === 0 && <p>No emerging monitoring area is stored for this threat.</p>}
            {record.emerging.map((item) => (
              <Block key={item.names.join("|")} title={item.label} card={item} slug={item.slugs[0]} onOpen={onOpenPlace} />
            ))}
          </section>
          <section aria-label="Patterns">
            <h3>Patterns</h3>
            {record.patterns.map((item) => <Block key={item.id} title={item.title} card={item} />)}
          </section>
          <section aria-label="Forecast">
            <h3>Forecast</h3>
            {record.forecast.length === 0 && <p>No municipality is projected to become more favorable to the configured model on the stored forecast.</p>}
            {record.forecast.map((item) => <Block key={item.slug + item.sentence} title={item.name} card={item} slug={item.slug} onOpen={onOpenPlace} />)}
          </section>
          <section aria-label="Threat models">
            <h3>Threat models</h3>
            {record.convergence.length === 0 && <p>No municipality has two elevated threat models on the stored record.</p>}
            {record.convergence.map((item) => (
              <article key={item.slug} className="sit-card">
                <h3>{item.name}</h3>
                <Lines items={item.evidence} />
                <p>{item.sentence}</p>
                <button type="button" className="secondary" onClick={() => onOpenPlace(item.slug)}>Open on the map</button>
              </article>
            ))}
          </section>
          <section aria-label="Rice">
            <h3>Rice</h3>
            {record.rice ? <Block card={record.rice} /> : <p>No mapped rice area is stored for the high-monitoring municipalities.</p>}
          </section>
          <section aria-label="Weather">
            <h3>Weather</h3>
            {record.weather ? <Block card={record.weather} /> : <p>No weather reading is stored for this day.</p>}
          </section>
          <section aria-label="Field validation">
            <h3>Field validation</h3>
            {record.inspections.length === 0 && <p>{record.empty}</p>}
            {record.inspections.map((item) => (
              <Block key={item.slug} title={item.name} card={item} field={item.field} action={item.action} urgency={item.urgency} slug={item.slug} onOpen={onOpenPlace} />
            ))}
          </section>
          <section aria-label="Stored route">
            <h3>Stored route</h3>
            {record.route ? <Block card={record.route} /> : <p>No inspection route is stored for this threat and day.</p>}
          </section>
          <section aria-label="Office">
            <h3>Office</h3>
            {ADMIN.map(([id, title]) => <Block key={id} title={title} card={record.admin[id]} />)}
          </section>
          <section aria-label="Monitoring record">
            <h3>Monitoring record</h3>
            {record.timeline.length === 0 && <p>No stored change is on the monitoring record for the attention list.</p>}
            {record.timeline.map((place) => (
              <article key={place.slug} className="sit-card">
                <h3>{place.name}</h3>
                <p>{place.sentence}</p>
                <ul className="sit-evidence">
                  {place.events.map((event) => (
                    <li key={`${event.when}-${event.label}-${event.detail}`}>{event.when ? `${event.when}. ` : ""}{event.label}. {event.detail}</li>
                  ))}
                </ul>
                <button type="button" className="secondary" onClick={() => onOpenPlace(place.slug)}>Open on the map</button>
              </article>
            ))}
          </section>
          <section aria-label="Ask from the record">
            <h3>Ask from the record</h3>
            <div className="prompts">
              {record.prompts.map((prompt) => (
                <button key={prompt.id} type="button" className="secondary" onClick={() => onAsk(prompt.message)}>{prompt.label}</button>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

export function ObservationAssist({
  note,
  placeName,
  disabled,
  onRead,
  onReviewImage,
}: {
  note: string;
  placeName?: string;
  disabled?: boolean;
  onRead: (body: string) => Promise<NoteReading>;
  onReviewImage: (file: File) => Promise<ImageReading>;
}) {
  const [reading, setReading] = useState<NoteReading | null>(null);
  const [image, setImage] = useState<ImageReading | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function readNote() {
    setError("");
    setBusy("Reading the note.");
    try {
      setReading(await onRead(note));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The note could not be read.");
    } finally {
      setBusy("");
    }
  }

  async function review(file: File | undefined) {
    if (!file) return;
    setError("");
    setBusy("Checking the photo.");
    try {
      setImage(await onReviewImage(file));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The photo could not be checked.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="sit-assist">
      <h4>Note reading{placeName ? ` for ${placeName}` : ""}</h4>
      <p className="an-note">The reading restates the note. It is not a model result.</p>
      <button type="button" className="secondary" disabled={disabled || busy !== "" || note.trim().length < 3} onClick={() => void readNote()}>
        Read this note
      </button>
      {reading && (
        <>
          <p>{reading.boundary}</p>
          <Lines items={reading.observations} />
          {reading.missing.length > 0 && <p>Missing: {reading.missing.join(", ")}.</p>}
          <Lines items={reading.suggested} />
        </>
      )}
      <h4>Field photo</h4>
      <label>
        Photo
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          disabled={disabled || busy !== ""}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            void review(file);
          }}
        />
      </label>
      {image && (
        <>
          <p>{image.sentence}</p>
          <Lines items={image.indicators} />
          <Lines items={image.questions} />
          <p className="an-note">{image.source}</p>
        </>
      )}
      {busy && <p className="status" role="status">{busy}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}

export async function fileToBase64(file: File) {
  const data = await file.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(data);
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
  }
  return btoa(binary);
}
