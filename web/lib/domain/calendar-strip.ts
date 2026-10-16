import { addDays, format, parseISO } from "date-fns";

/**
 * Layout only: which days the deadline planner's strip shows and which markers sit on them. The
 * dates themselves (earliest, recommended, latest, due) come from the engine through the API; this
 * file never works out a send date.
 */
export type Marker = "today" | "earliest" | "recommended" | "latest" | "due";

export interface StripDay {
  iso: string;
  weekday: string;
  day: number;
  markers: Marker[];
}

export interface StripDates {
  today: string;
  earliest: string;
  recommended: string;
  latest: string;
  due: string;
}

export const STRIP_LENGTH = 15;

function iso(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

/** The strip ends on the due date when it is far away, and starts today when it is near. */
export function stripStart(today: string, due: string, length = STRIP_LENGTH): string {
  const todayDate = parseISO(today);
  const dueDate = parseISO(due);
  const lastStart = addDays(dueDate, -(length - 1));
  return iso(lastStart > todayDate ? lastStart : todayDate);
}

export function buildStrip(dates: StripDates, length = STRIP_LENGTH): StripDay[] {
  const start = parseISO(stripStart(dates.today, dates.due, length));
  const marks: [Marker, string][] = [
    ["today", dates.today],
    ["earliest", dates.earliest],
    ["recommended", dates.recommended],
    ["latest", dates.latest],
    ["due", dates.due],
  ];
  return Array.from({ length }, (_, offset) => {
    const date = addDays(start, offset);
    const key = iso(date);
    return {
      iso: key,
      weekday: format(date, "EEEEE"),
      day: date.getDate(),
      markers: marks.filter(([, value]) => value === key).map(([marker]) => marker),
    };
  });
}

export const MARKER_LABEL: Record<Marker, string> = {
  today: "Today",
  earliest: "Earliest if sent now",
  recommended: "Recommended",
  latest: "Latest send",
  due: "Due",
};

/** The day's accessible name, e.g. "Wed 21 Oct: Recommended, Latest send". */
export function describeDay(day: StripDay): string {
  const date = format(parseISO(day.iso), "EEE d MMM");
  return day.markers.length
    ? `${date}: ${day.markers.map((m) => MARKER_LABEL[m]).join(", ")}`
    : date;
}
