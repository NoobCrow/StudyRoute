// Recomputes the hash the API puts on a compliance report, in the browser, with no server call.
// The API hashes the report as JSON with sorted keys, no whitespace and UTF-8 (SHA-256).

export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const record = value as Record<string, unknown>;
  const parts = Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`);
  return `{${parts.join(",")}}`;
}

export async function sha256Ref(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  const hex = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  return `sha256:${hex}`;
}

/** True when `report_hash` matches the rest of the report. False means the copy was changed. */
export async function reportIsIntact(
  report: { report_hash: string } & Record<string, unknown>,
): Promise<boolean> {
  const { report_hash: claimed, ...body } = report;
  return (await sha256Ref(canonicalJson(body))) === claimed;
}
