import type { ChecklistItem } from "@/lib/api/types";

// Counting and filtering the checklist the API sent. What is on the list, and whether it is verified,
// is the server's rule; this only says how many are ready and which to show.

export type ChecklistTab = "all" | "missing" | "ready";

export const CHECKLIST_TABS: readonly ChecklistTab[] = ["all", "missing", "ready"];

export interface Readiness {
  ready: number;
  total: number;
  /** A whole number from 0 to 100. */
  percent: number;
}

export function readiness(items: readonly ChecklistItem[]): Readiness {
  const ready = items.filter((item) => item.provided).length;
  const total = items.length;
  return { ready, total, percent: total === 0 ? 0 : Math.round((ready * 100) / total) };
}

export function checklistCounts(items: readonly ChecklistItem[]): Record<ChecklistTab, number> {
  const ready = items.filter((item) => item.provided).length;
  return { all: items.length, missing: items.length - ready, ready };
}

export function filterChecklist(
  items: readonly ChecklistItem[],
  tab: ChecklistTab,
): ChecklistItem[] {
  if (tab === "all") return [...items];
  return items.filter((item) => item.provided === (tab === "ready"));
}

/** "source_of_funds" as words, for a chip. */
export function documentKindLabel(kind: string): string {
  return kind.replaceAll("_", " ");
}

/** The file name the form suggests for a document type, always mock text. */
export function sampleFilename(kind: string): string {
  return `${kind.replaceAll("_", "-")}-mock.txt`;
}

/** "1 file" or "0 files". */
export function fileCount(count: number): string {
  return `${count} ${count === 1 ? "file" : "files"}`;
}
