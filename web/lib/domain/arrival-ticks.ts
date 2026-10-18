// Which arrival steps a person has ticked off. Saved in this browser only, per country, because a tick
// is a personal reminder and not data the app needs. Storage can be missing, full or blocked (private
// windows, strict settings): then ticks simply last until the page is closed, and nothing fails.

const PREFIX = "studyroute.arrival.";

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function browserStore(): Store | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** The ticked step keys for a country, or none if nothing is saved or the saved text is not a list of keys. */
export function readTicks(country: string, store: Store | null = browserStore()): string[] {
  try {
    const raw = store?.getItem(PREFIX + country);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((key): key is string => typeof key === "string" && key.length <= 60)
      : [];
  } catch {
    return [];
  }
}

export function writeTicks(
  country: string,
  keys: readonly string[],
  store: Store | null = browserStore(),
): void {
  try {
    if (keys.length === 0) store?.removeItem(PREFIX + country);
    else store?.setItem(PREFIX + country, JSON.stringify([...new Set(keys)]));
  } catch {
    // The tick still shows for this visit; it just will not be remembered.
  }
}

/** Ticked keys that are still steps of the current guide, so an old tick can never inflate the count. */
export function doneCount(ticks: readonly string[], stepKeys: readonly string[]): number {
  const known = new Set(stepKeys);
  return new Set(ticks.filter((key) => known.has(key))).size;
}
