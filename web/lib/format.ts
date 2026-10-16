// Display helpers for dates and identifiers only. Money is never formatted here.

const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});
const DATE_ONLY = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : `${DATE_TIME.format(date)} UTC`;
}

export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return "-";
  const date = new Date(`${isoDate}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? isoDate : DATE_ONLY.format(date);
}

export function shortHash(hash: string | null | undefined, keep = 10): string {
  if (!hash) return "-";
  const bare = hash.replace(/^sha256:/, "");
  return bare.length > keep * 2 ? `${bare.slice(0, keep)}...${bare.slice(-4)}` : bare;
}

export function shortId(id: string): string {
  return id.length > 14 ? `${id.slice(0, 8)}...${id.slice(-4)}` : id;
}

export function secondsUntil(iso: string, nowMs: number): number {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - nowMs) / 1000));
}

export function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function addDaysIso(days: number, from: Date = new Date()): string {
  const d = new Date(Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate() + days));
  return d.toISOString().slice(0, 10);
}
