import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "command" | "map" | "weather" | "rice" | "risk" | "analytics" | "operations" | "admin" | "alerts" | "reports" | "assistant"
  | "rain" | "heavyRain" | "temp" | "humidity" | "wind" | "soil" | "leafWet" | "sun" | "cloud" | "forecast"
  | "blast" | "planthopper" | "blackbug" | "blight"
  | "inspect" | "farmer" | "field" | "hall" | "rising" | "falling" | "target" | "calendar" | "play" | "pause" | "next" | "prev"
  | "spark" | "send" | "plus" | "check" | "slides" | "close" | "arrow" | "layers" | "route" | "shield";

const PATHS: Record<IconName, ReactNode> = {
  command: <><path d="M4 20V10l8-6 8 6v10" /><path d="M9 20v-6h6v6" /><path d="M12 4V2" /></>,
  map: <><path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z" /><path d="M9 4v14M15 6v14" /></>,
  weather: <><path d="M7 17h10a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 17z" /><path d="M9 20l-1 2M13 20l-1 2M17 20l-1 2" /></>,
  rice: <><path d="M12 22V9" /><path d="M12 9c-2-1-3-3-3-5 2 0 3 2 3 5zM12 9c2-1 3-3 3-5-2 0-3 2-3 5z" /><path d="M12 14c-2.5-.5-4-2.5-4-4.5 2.5 0 4 2 4 4.5zM12 14c2.5-.5 4-2.5 4-4.5-2.5 0-4 2-4 4.5z" /><path d="M12 19c-3-.5-5-2.5-5-4.5 3 0 5 2 5 4.5zM12 19c3-.5 5-2.5 5-4.5-3 0-5 2-5 4.5z" /></>,
  risk: <><path d="M5 21c3-8 9-14 15-17-1 7-5 13-15 17z" /><path d="M5 21L14 11" /><path d="M10 9l2 1-1 2M15 14l-2 0" /></>,
  analytics: <><path d="M4 20h16" /><path d="M6 16v-4M10 16V8M14 16v-6M18 16V5" /></>,
  operations: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" /><path d="M11 8v3l2 1.5" /></>,
  admin: <><path d="M3 21h18" /><path d="M5 21V10h14v11" /><path d="M12 3l8 5H4z" /><path d="M9 21v-5h6v5" /><path d="M8 13h.01M16 13h.01" /></>,
  alerts: <><path d="M6 17V11a6 6 0 0 1 12 0v6l2 2H4z" /><path d="M10 21h4" /></>,
  reports: <><path d="M6 3h9l4 4v14H6z" /><path d="M15 3v4h4" /><path d="M9 12h7M9 16h7M9 8h3" /></>,
  assistant: <><path d="M4 5h16v11H9l-5 4z" /><path d="M12 8l.8 1.7 1.7.8-1.7.8L12 13l-.8-1.7-1.7-.8 1.7-.8z" /></>,
  rain: <><path d="M7 14h10a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 14z" /><path d="M8 18v2M12 17v3M16 18v2" /></>,
  heavyRain: <><path d="M7 13h10a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 13z" /><path d="M7 16l-1 2M10 16l-1 2M13 16l-1 2M16 16l-1 2M9 19.5l-1 2M12 19.5l-1 2M15 19.5l-1 2" /></>,
  temp: <><path d="M10 14V5a2 2 0 0 1 4 0v9a4 4 0 1 1-4 0z" /><path d="M12 17v-6" /><path d="M17 5h2M17 8h2M17 11h2" /></>,
  humidity: <><path d="M12 3c3 4 6 7.5 6 11a6 6 0 0 1-12 0c0-3.5 3-7 6-11z" /><path d="M9 15a3 3 0 0 0 3 3" /></>,
  wind: <><path d="M3 9h11a3 3 0 1 0-3-3" /><path d="M3 13h15a3 3 0 1 1-3 3" /><path d="M3 17h7" /></>,
  soil: <><path d="M3 9h18" /><path d="M12 9v12M12 13l-4 4M12 15l4 4M8 13l-3 2M16 12l3 2" /><path d="M7 5l.5 1M12 4v1.5M17 5l-.5 1" /></>,
  leafWet: <><path d="M4 20C4 10 10 4 20 4c0 10-6 16-16 16z" /><path d="M4 20L14 10" /><path d="M15 14c.8 1.1 1.5 2 1.5 2.8a1.5 1.5 0 0 1-3 0c0-.8.7-1.7 1.5-2.8z" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  cloud: <><path d="M7 18h10a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 18z" /></>,
  forecast: <><rect x="3" y="5" width="18" height="15" rx="1.5" /><path d="M3 10h18M8 3v4M16 3v4" /><path d="M7 14h2M11 14h2M15 14h2M7 17h2M11 17h2" /></>,
  blast: <><path d="M4 21C6 12 12 5 21 3c-1 9-8 15-17 18z" /><path d="M4 21L19 5" /><path d="M10 10l2 .5-.5 2zM14 13l2 .3-.8 1.6z" /></>,
  planthopper: <><path d="M6 13c0-3 4-6 13-6-1 4-4 7-9 7" /><circle cx="6.5" cy="12" r="2.5" /><path d="M8 15l-2 4M11 15l-1 4M14 14l1 4" /></>,
  blackbug: <><path d="M5 13c2-4 8-5 14-3-1 3-6 5-12 4z" /><circle cx="18.5" cy="11" r="1.6" /><path d="M20 10l2-3M20 11.5l2.5-1" /><path d="M8 14l-2 4M11 14.5l-1 4M14 14l1 4" /></>,
  blight: <><path d="M4 21C6 12 12 5 21 3c-1 9-8 15-17 18z" /><path d="M4 21L19 5" /><path d="M12 13l2.5-.5 1 1.5-2 1.5" /></>,
  inspect: <><circle cx="10" cy="10" r="6" /><path d="M20 20l-5.5-5.5" /><path d="M7 10h6M10 7v6" /></>,
  farmer: <><path d="M5 9h14" /><path d="M8 9c0-3 1.5-5 4-5s4 2 4 5" /><path d="M8.5 10.5a3.5 3.5 0 0 0 7 0" /><path d="M4 21c1-4 4-6 8-6s7 2 8 6" /></>,
  field: <><path d="M3 20h18" /><path d="M12 20L9 9M12 20l3-11M12 20L5 11M12 20l7-9" /><path d="M3 9h18" /></>,
  hall: <><path d="M4 21V10l8-5 8 5v11" /><path d="M10 21v-5h4v5" /><path d="M12 5V2l3 1-3 1" /><circle cx="12" cy="11" r="1.5" /></>,
  rising: <><path d="M4 17l6-6 4 4 6-8" /><path d="M15 7h5v5" /></>,
  falling: <><path d="M4 7l6 6 4-4 6 8" /><path d="M15 17h5v-5" /></>,
  target: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="1.5" /><path d="M3 10h18M8 3v4M16 3v4" /></>,
  play: <path d="M8 5v14l11-7z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  next: <path d="M9 6l6 6-6 6" />,
  prev: <path d="M15 6l-6 6 6 6" />,
  spark: <path d="M12 3l1.8 4.6L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.9zM18 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />,
  send: <><path d="M4 12l16-8-6 16-2-7z" /><path d="M12 13l8-9" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  check: <path d="M5 12l5 5 9-10" />,
  slides: <><rect x="3" y="4" width="18" height="12" rx="1.5" /><path d="M12 16v4M8 20h8" /></>,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  layers: <><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></>,
  route: <><circle cx="6" cy="18" r="2" /><circle cx="18" cy="6" r="2" /><path d="M8 18h6a4 4 0 0 0 0-8h-4a4 4 0 0 1 0-8h6" /></>,
  shield: <><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M9 12l2 2 4-4" /></>,
};

export function Icon({ name, size = 18, ...rest }: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}

export const THREAT_ICON: Record<string, IconName> = {
  rice_blast: "blast",
  brown_planthopper: "planthopper",
  rice_black_bug: "blackbug",
  bacterial_leaf_blight: "blight",
};

export function threatIcon(idOrName: string): IconName {
  const key = idOrName.toLowerCase().replace(/\s+/g, "_");
  return THREAT_ICON[key] || "risk";
}
